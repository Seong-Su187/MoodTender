import os
import re
import json
import torch
import traceback
from argparse import Namespace
from pathlib import Path

import scripts.realtime_inference as rt
from scripts.realtime_inference import Avatar
from musetalk.utils.utils import load_all_model
from musetalk.utils.audio_processor import AudioProcessor
from musetalk.utils.face_parsing import FaceParsing
from transformers import WhisperModel

args = Namespace(
    version="v15", extra_margin=15, parsing_mode="jaw",
    left_cheek_width=40, right_cheek_width=40, batch_size=16, fps=25,
    audio_padding_length_left=1, audio_padding_length_right=6,
    skip_save_images=False, result_dir="./results",
)
rt.args = args

device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
print(f"[서버] 디바이스: {device}")

# ─── 모델 전역 상태 ───────────────────────────────────────────
vae = unet = pe = timesteps = whisper = audio_processor = weight_dtype = fp = None
custom_avatar = None
video_avatars: dict = {}   # { filename: Avatar } — backend/video/ 사전 로드
taesd_decoder = None  # TAESD 경량 VAE 디코더
CUSTOM_AVATAR_CACHE = f"./results/{args.version}/avatars/custom_avatar"

models_ready        = False
loading_status      = "모델 미로드"
loading_error       = None
loading_in_progress = False

def load_models(full_decode=False):
    global vae, unet, pe, timesteps, whisper, audio_processor, weight_dtype, fp
    global video_avatars, models_ready, loading_status, loading_error, loading_in_progress
    try:
        loading_status = "MuseTalk 모델 로딩 중..."
        vae, unet, pe = load_all_model(
            unet_model_path="./models/musetalkV15/unet.pth",
            vae_type="sd-vae",
            unet_config="./models/musetalkV15/musetalk.json",
            device=device,
        )
        timesteps = torch.tensor([0], device=device)
        pe = pe.half().to(device)
        vae.vae = vae.vae.half().to(device)
        unet.model = unet.model.half().to(device)
        weight_dtype = unet.model.dtype

        try:
            torch.backends.cuda.enable_flash_sdp(True)
            torch.backends.cuda.enable_mem_efficient_sdp(True)
            print("[서버] SDPA (Flash Attention) 활성화")
        except Exception as se:
            print(f"[서버] SDPA 스킵: {se}")


        audio_processor = AudioProcessor(feature_extractor_path="./models/whisper")
        whisper = WhisperModel.from_pretrained("./models/whisper")
        whisper = whisper.to(device=device, dtype=weight_dtype).eval()
        whisper.requires_grad_(False)

        fp = FaceParsing(left_cheek_width=40, right_cheek_width=40)

        rt.vae = vae; rt.unet = unet; rt.pe = pe; rt.timesteps = timesteps
        rt.whisper = whisper; rt.audio_processor = audio_processor
        rt.weight_dtype = weight_dtype; rt.device = device; rt.fp = fp

        loading_status = "아바타 준비 중..."
        _load_video_avatars()
        _try_load_custom_avatar_from_cache()

        # GPU 웜업: CUDA 커널 사전 로딩으로 첫 추론 콜드 스타트 제거
        _warmup_gpu(full_decode)

        models_ready   = True
        loading_status = "준비 완료"
        print("[서버] 모델 준비 완료")
    except Exception as e:
        loading_error  = str(e)
        loading_status = f"로딩 실패: {e}"
        print(f"[서버] 로딩 실패: {e}")
        traceback.print_exc()
    finally:
        loading_in_progress = False

def _smooth_avatar_coords(av, alpha: float = 0.35):
    """coord_list_cycle을 EMA(지수 이동 평균)로 스무딩해 bbox 지터 제거.
    alpha: 최신 프레임 가중치 (낮을수록 강한 스무딩, 높을수록 빠른 추적)."""
    coords = av.coord_list_cycle
    n = len(coords)
    if n == 0:
        return

    init = next((c for c in reversed(coords) if c is not None), None)
    if init is None:
        return

    def run_ema(sequence, init_val):
        result = []
        prev = init_val
        for c in sequence:
            if c is None:
                result.append(None)
                continue
            ema = tuple(int(alpha * c[k] + (1 - alpha) * prev[k]) for k in range(4))
            result.append(ema)
            prev = ema
        return result, prev

    # 루프 영상 경계 처리: 1차 패스로 워밍업 후 2차 패스로 실제 적용
    _, warm_state = run_ema(coords, init)
    smoothed, _ = run_ema(coords, warm_state)
    av.coord_list_cycle = smoothed

def _erode_avatar_masks(av, erode_px: int = 3, blur_ksize: int = 15):
    """마스크 침식 후 재블러링.
    경계를 배경 텍스처에서 얼굴 안쪽으로 이동시켜 shimmer 완화.
    erode_px: 침식 픽셀 수 / blur_ksize: 재블러 커널 크기"""
    import cv2, numpy as np
    masks = av.mask_list_cycle
    if not masks:
        return
    kernel = np.ones((erode_px * 2 + 1, erode_px * 2 + 1), np.uint8)
    bk = blur_ksize if blur_ksize % 2 == 1 else blur_ksize + 1
    result = []
    for m in masks:
        binary = (m > 20).astype(np.uint8) * 255   # 이진화
        eroded = cv2.erode(binary, kernel, iterations=1)  # 침식
        blurred = cv2.GaussianBlur(eroded, (bk, bk), 0)   # 재블러
        result.append(blurred)
    av.mask_list_cycle = result
    print(f"[서버] mask erode+blur 적용 (erode={erode_px}px, blur={bk}x{bk})")

def _smooth_avatar_masks(av, window: int = 7):
    """mask_list_cycle을 이동 평균으로 스무딩해 마스크 경계 흔들림 제거.
    bbox 좌표 평활화(_smooth_avatar_coords)와 동일한 원리를 마스크에 적용."""
    import numpy as np
    masks = av.mask_list_cycle
    n = len(masks)
    if n == 0:
        return
    half = window // 2
    smoothed = []
    for i in range(n):
        neighbors = [masks[(i + j) % n].astype(np.float32)
                     for j in range(-half, half + 1)]
        smoothed.append(np.mean(neighbors, axis=0).astype(np.uint8))
    av.mask_list_cycle = smoothed

def _load_video_avatars():
    """backend/video/ 폴더의 MP4를 모두 Avatar로 로드해 video_avatars에 저장."""
    from backend.config import VIDEO_DIR
    global video_avatars
    if not VIDEO_DIR.exists():
        return
    files = sorted(VIDEO_DIR.glob("*.mp4"))
    if not files:
        return
    loading_status_ref = "video/ 아바타 로딩 중..."
    print(f"[서버] backend/video/ 영상 {len(files)}개 로딩 시작")
    for f in files:
        stem = f.stem
        avatar_id = "video_" + re.sub(r"[^\w]", "_", stem)[:40]
        cache_info = Path(f"./results/{args.version}/avatars/{avatar_id}/avator_info.json")
        preparation = not cache_info.exists()
        try:
            av = Avatar(
                avatar_id=avatar_id,
                video_path=str(f),
                bbox_shift=0,
                batch_size=args.batch_size,
                preparation=preparation,
            )
            av.input_latent_list_cycle = [t.to(device) for t in av.input_latent_list_cycle]
            _smooth_avatar_coords(av)
            video_avatars[f.name] = av
            print(f"[서버] 로드 완료: {f.name} (preparation={preparation})")
        except Exception as e:
            print(f"[서버] 로드 실패: {f.name} — {e}")
    print(f"[서버] video/ 아바타 로딩 완료 ({len(video_avatars)}/{len(files)}개)")

def _try_load_custom_avatar_from_cache():
    global custom_avatar
    info_path = os.path.join(CUSTOM_AVATAR_CACHE, "avator_info.json")
    if not os.path.exists(info_path):
        return
    try:
        with open(info_path) as f:
            info = json.load(f)
        custom_avatar = Avatar(
            avatar_id="custom_avatar",
            video_path=info.get("video_path", ""),
            bbox_shift=info.get("bbox_shift", 0),
            batch_size=args.batch_size,
            preparation=False,
        )
        custom_avatar.input_latent_list_cycle = [t.to(device) for t in custom_avatar.input_latent_list_cycle]
    except Exception as e:
        print(f"[캐시] 커스텀 아바타 로드 실패: {e}")

def _warmup_gpu(full_decode=False):
    """UNet+VAE CUDA 커널 사전 컴파일.
    batch=16(정상 배치) + 소배치 1~15(마지막 배치 후보)를 모두 실행해
    실제 추론 시 알고리즘 탐색 없이 바로 캐시된 커널을 사용하게 함.

    decode100(보간 없는 전체 디코딩) shape 워밍업은 8GB VRAM에서 decode50
    shape 캐시와 동시에 상주할 때 메모리 압박으로 오히려 5~18배 느려지는 것이
    eval로 확인되어(model_test.md 참고) 비활성화. full_decode 인자는 현재
    무시되고 항상 decode50 shape만 워밍업한다."""
    print("[서버] GPU 웜업 중...")
    try:
        with torch.inference_mode():
            # batch=16 정상 경로 (frame interpolation과 동일하게 out[::2] 사용)
            _w16 = torch.zeros(16, 5, 384, dtype=weight_dtype, device=device)
            _l16 = torch.zeros(16, 8, 32, 32, dtype=weight_dtype, device=device)
            _o16 = unet.model(_l16, timesteps, encoder_hidden_states=pe(_w16)).sample
            # if full_decode:
            #     vae.vae.decode(_o16.to(vae.vae.dtype))
            # else:
            vae.vae.decode(_o16[::2].to(vae.vae.dtype))
            torch.cuda.synchronize()
            print("[서버] 웜업 batch=16 완료")

            # 소배치 1~15: 마지막 배치 크기가 어떤 값이든 CUDA 커널 탐색 없이 즉시 실행
            for b in range(1, 16):
                _w = torch.zeros(b, 5, 384, dtype=weight_dtype, device=device)
                _l = torch.zeros(b, 8, 32, 32, dtype=weight_dtype, device=device)
                _o = unet.model(_l, timesteps, encoder_hidden_states=pe(_w)).sample
                # if full_decode:
                #     vae.vae.decode(_o.to(vae.vae.dtype))
                # else:
                key = _o[::2]
                if key.shape[0] >= 1:
                    vae.vae.decode(key.to(vae.vae.dtype))
                torch.cuda.synchronize()
            print("[서버] 웜업 batch=1~15 완료")

        print("[서버] GPU 웜업 완료")
    except Exception as e:
        print(f"[서버] GPU 웜업 스킵: {e}")
