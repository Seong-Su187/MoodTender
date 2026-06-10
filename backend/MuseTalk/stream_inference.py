# coding: utf-8
"""
스트리밍 추론: MuseTalk 프레임을 생성하면서 실시간으로 FFmpeg에 파이프,
fMP4 청크를 yield해 HTTP 스트리밍에 사용.
"""

import os, queue, threading, subprocess, ctypes
from pathlib import Path
import numpy as np
import cv2
import torch


def _win_short_path(path: str) -> str:
    """Windows 한글 경로 → 8.3 단축 경로 변환 (ffmpeg 인자용). 파일이 없으면 원본 반환."""
    try:
        buf = ctypes.create_unicode_buffer(512)
        if ctypes.windll.kernel32.GetShortPathNameW(path, buf, 512):
            return buf.value
    except Exception:
        pass
    return path


def _win_short_path_new(path: str) -> str:
    """아직 존재하지 않는 파일 경로의 단축 경로: 부모 디렉토리를 변환 후 파일명 결합."""
    p = Path(os.path.abspath(path))
    short_parent = _win_short_path(str(p.parent))
    return str(Path(short_parent) / p.name)

_BAR_BG_PATH = Path(__file__).resolve().parent.parent.parent / "frontend" / "assets" / "bar-background.jpeg"

from musetalk.utils.blending import get_image_blending
from musetalk.utils.utils import datagen


def _load_webm_alpha(video_path: str, W: int, H: int, ffmpeg_bin: str):
    """VP9 webm에서 알파 채널을 프레임 리스트로 추출. 실패 시 None 반환."""
    try:
        ffmpeg_exe = os.path.join(ffmpeg_bin, 'ffmpeg.exe')
        safe_path = _win_short_path(video_path)
        cmd = [ffmpeg_exe, '-y', '-v', 'quiet', '-i', safe_path,
               '-vf', f'format=yuva420p,alphaextract,scale={W}:{H}',
               '-f', 'rawvideo', '-pix_fmt', 'gray', 'pipe:1']
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        raw, _ = proc.communicate()
        frame_size = W * H
        n = len(raw) // frame_size
        if n == 0:
            print(f"[COMPOSITING] 알파 채널 없음: {video_path}", flush=True)
            return None
        frames = [np.frombuffer(raw[i*frame_size:(i+1)*frame_size], dtype=np.uint8).reshape(H, W)
                  for i in range(n)]
        # 알파가 전부 255이면 투명도 정보 없음 (black-bg 영상) → None 반환
        sample = np.concatenate([f.ravel() for f in frames[:min(3, n)]])
        if sample.mean() > 250:
            print(f"[COMPOSITING] 알파 전부 불투명 (black-bg 원본) → chroma-key 사용", flush=True)
            return None
        print(f"[COMPOSITING] webm 알파 {n}프레임 추출 완료", flush=True)
        return frames
    except Exception as e:
        print(f"[COMPOSITING] 알파 추출 실패: {e}", flush=True)
        return None


def _black_bg_alpha(frame: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """검정 배경 아바타에서 캐릭터 알파 마스크 생성 (RGB max-value 임계값 방식)."""
    max_rgb = frame.max(axis=2)                              # (H, W) 각 픽셀의 최대 채널값
    a = np.where(max_rgb > 12, np.uint8(255), np.uint8(0))  # 검정 배경(≤12) = 투명
    a = cv2.morphologyEx(a, cv2.MORPH_CLOSE, kernel, iterations=2)  # 옷 안의 작은 구멍 메우기 (윤곽선 위치는 유지)
    a = cv2.erode(a, kernel, iterations=1)                  # 가장자리 흰 fringe 1px 제거
    a = cv2.GaussianBlur(a, (7, 7), 0)                      # 엣지 부드럽게
    return a


def inference_stream(
    avatar, audio_path, fps, ffmpeg_bin,
    pe, unet, vae, timesteps,
    whisper_model, audio_processor, weight_dtype, device,
    audio_pad_left=2, audio_pad_right=2,
    taesd=None,
):
    """
    MuseTalk 추론 결과를 프레임 단위로 FFmpeg에 파이프하고
    fMP4 바이너리 청크를 yield하는 제너레이터.

    첫 청크 도달 시간:
      TTS(0.5초) + Whisper(0.04초) + 첫 3배치(~2.7초) + FFmpeg버퍼(~0.5초) ≈ 3~4초
    """
    ffmpeg_exe = os.path.join(ffmpeg_bin, 'ffmpeg.exe')

    # ── 1. 오디오 특징 추출 (빠름: ~40ms) ──────────────────────
    whisper_features, librosa_length = audio_processor.get_audio_feature(
        audio_path, weight_dtype=weight_dtype
    )
    whisper_chunks = audio_processor.get_whisper_chunk(
        whisper_features, device, weight_dtype, whisper_model, librosa_length,
        fps=fps,
        audio_padding_length_left=audio_pad_left,
        audio_padding_length_right=audio_pad_right,
    )
    video_num = len(whisper_chunks)

    # ── 2. 아바타 프레임 크기 확인 + 바 배경 + 알파 로드 ─────────
    H, W = avatar.frame_list_cycle[0].shape[:2]
    # cv2.imread는 Windows 한글 경로 미지원 → np.fromfile 우회
    _raw_buf = np.fromfile(str(_BAR_BG_PATH), dtype=np.uint8)
    _raw_bg  = cv2.imdecode(_raw_buf, cv2.IMREAD_COLOR) if len(_raw_buf) > 0 else None
    if _raw_bg is None:
        print(f"[COMPOSITING] 배경 이미지 로드 실패: {_BAR_BG_PATH}", flush=True)
    else:
        print(f"[COMPOSITING] 배경 이미지 로드 성공 → {W}x{H}로 리사이즈", flush=True)
    bar_bg    = cv2.resize(_raw_bg, (W, H)) if _raw_bg is not None else None
    bar_bg_u16 = bar_bg.astype(np.uint16) if bar_bg is not None else None

    # VP9 webm이면 원본 알파 채널 사용 (루마 키보다 정확)
    alpha_cycle   = None
    _erode_kernel = np.ones((3, 3), np.uint8)
    if bar_bg is not None:
        vp = getattr(avatar, 'video_path', '')
        if str(vp).lower().endswith('.webm'):
            alpha_cycle = _load_webm_alpha(str(vp), W, H, ffmpeg_bin)

    # ── 3. FFmpeg 프로세스 시작 ─────────────────────────────────
    cmd = [
        ffmpeg_exe, '-y', '-v', 'quiet',
        '-fflags', '+genpts',
        '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{W}x{H}', '-r', str(fps),
        '-thread_queue_size', '512',
        '-i', 'pipe:0',
        '-thread_queue_size', '512',
        '-i', _win_short_path(audio_path),
        '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency', '-crf', '23',
        '-vf', 'format=yuv420p',
        '-g', '12', '-sc_threshold', '0',  # 키프레임 0.48초마다 (12프레임)
        '-c:a', 'aac', '-b:a', '128k',
        '-movflags', 'frag_keyframe+empty_moov+default_base_moof',
        '-shortest', '-f', 'mp4', 'pipe:1',
    ]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )

    # ── 4. FFmpeg stdout → asyncio Queue 브릿지 스레드 ─────────
    output_q: queue.Queue = queue.Queue()

    def _read_stdout():
        try:
            while True:
                chunk = proc.stdout.read(8192)
                if not chunk:
                    break
                output_q.put(chunk)
        finally:
            output_q.put(None)

    reader = threading.Thread(target=_read_stdout, daemon=True)
    reader.start()

    # ── 5. GPU 추론과 CPU 블렌딩을 분리해 병렬 실행 ────────────
    # GPU가 다음 배치를 처리하는 동안 CPU는 이전 배치 블렌딩
    blend_q: queue.Queue = queue.Queue(maxsize=64)

    def _decode_fast(pred):
        """VAE 디코딩: 홀수 프레임만 디코딩 후 짝수 프레임은 선형 보간
        - VAE 연산 절반으로 줄임 (~3.5초 단축 예상)
        - 인접 프레임 평균이라 립싱크 품질 영향 최소
        """
        latents = (1 / vae.scaling_factor) * pred
        dtype   = vae.vae.dtype
        n       = latents.shape[0]

        if n >= 4:
            # 키프레임(짝수 인덱스)만 VAE 디코딩
            key_latents = latents[::2]
            key_decoded = vae.vae.decode(key_latents.to(dtype)).sample  # n//2 프레임

            # 벡터화 보간: 인접 키프레임의 평균
            interp = (key_decoded[:-1] + key_decoded[1:]) / 2  # [k-1, C, H, W]

            # 키프레임 + 보간 프레임 인터리브
            k = key_decoded.shape[0]
            pairs = min(k - 1, interp.shape[0])
            merged = torch.stack([key_decoded[:pairs], interp[:pairs]], dim=1)
            merged = merged.reshape(pairs * 2, *key_decoded.shape[1:])
            # 마지막 키프레임 추가 후 정확한 n개로 자름
            image = torch.cat([merged, key_decoded[pairs:]], dim=0)[:n]
        else:
            image = vae.vae.decode(latents.to(dtype)).sample

        image = (image / 2 + 0.5).clamp(0, 1)
        image = (image * 255).round().to(torch.uint8)
        image = image[:, [2, 1, 0], :, :]
        image = image.permute(0, 2, 3, 1)
        return image.cpu().numpy()

    def _gpu_loop():
        """GPU 전용: 배치 추론 → raw 프레임을 blend_q에 적재"""
        import time as _t
        gen = datagen(whisper_chunks, avatar.input_latent_list_cycle, avatar.batch_size)
        batch_idx = 0
        try:
            for whisper_batch, latent_batch in gen:
                b = whisper_batch.shape[0]
                t0 = _t.perf_counter()
                with torch.inference_mode():
                    af   = pe(whisper_batch.to(device))
                    lb   = latent_batch.to(dtype=unet.model.dtype)
                    pred = unet.model(lb, timesteps, encoder_hidden_states=af).sample
                t1 = _t.perf_counter()
                with torch.inference_mode():
                    recon = _decode_fast(pred)
                t2 = _t.perf_counter()
                print(f"  [배치{batch_idx:02d}] B={b:2d}  UNet={( t1-t0)*1000:5.0f}ms  VAE={(t2-t1)*1000:5.0f}ms  합={(t2-t0)*1000:5.0f}ms", flush=True)
                batch_idx += 1
                for raw in recon:
                    blend_q.put(raw)
        except Exception as e:
            print(f"[stream] GPU 루프 오류: {e}")
        finally:
            blend_q.put(None)

    def _cpu_blend_write():
        """CPU 전용: blend_q에서 raw 프레임 꺼내 블렌딩 → FFmpeg stdin"""
        idx = 0
        try:
            while True:
                raw = blend_q.get()
                if raw is None or idx >= video_num:
                    break
                bbox  = avatar.coord_list_cycle[idx % len(avatar.coord_list_cycle)]
                ori   = avatar.frame_list_cycle[idx % len(avatar.frame_list_cycle)].copy()
                if bbox is None:
                    proc.stdin.write(ori.tobytes())
                    idx += 1
                    continue
                x1, y1, x2, y2 = bbox
                rf    = cv2.resize(raw.astype(np.uint8), (x2 - x1, y2 - y1))
                mask  = avatar.mask_list_cycle[idx % len(avatar.mask_list_cycle)]
                mc    = avatar.mask_coords_list_cycle[idx % len(avatar.mask_coords_list_cycle)]
                frame = get_image_blending(ori, rf, bbox, mask, mc)
                if bar_bg_u16 is not None:
                    if alpha_cycle is not None:
                        a_u8 = alpha_cycle[idx % len(alpha_cycle)]
                    else:
                        a_u8 = _black_bg_alpha(ori, _erode_kernel)
                    a = a_u8[:, :, np.newaxis].astype(np.uint16)
                    frame = ((frame.astype(np.uint16) * a + bar_bg_u16 * (255 - a)) >> 8).astype(np.uint8)
                proc.stdin.write(frame.tobytes())
                idx += 1
        except Exception as e:
            print(f"[stream] CPU 블렌딩 오류: {e}")
        finally:
            try:
                proc.stdin.close()
            except Exception:
                pass

    gpu_thread = threading.Thread(target=_gpu_loop, daemon=True)
    writer     = threading.Thread(target=_cpu_blend_write, daemon=True)
    gpu_thread.start()
    writer.start()

    # ── 6. FFmpeg 출력 청크 yield ───────────────────────────────
    while True:
        chunk = output_q.get()
        if chunk is None:
            break
        yield chunk

    writer.join(timeout=5)
    proc.wait(timeout=5)


def inference_webm(
    avatar, audio_path, fps, ffmpeg_bin,
    pe, unet, vae, timesteps,
    whisper_model, audio_processor, weight_dtype, device,
    output_path,
    audio_pad_left=2, audio_pad_right=2,
):
    """
    MuseTalk 추론 → VP9 WebM (알파 채널 포함) 파일 저장.
    output_path에 저장 완료될 때까지 블록.
    브라우저에서 CSS bar-background 투과 재생 (루프와 동일 방식).
    """
    ffmpeg_exe = os.path.join(ffmpeg_bin, 'ffmpeg.exe')

    # 1. 오디오 특징
    whisper_features, librosa_length = audio_processor.get_audio_feature(
        audio_path, weight_dtype=weight_dtype
    )
    whisper_chunks = audio_processor.get_whisper_chunk(
        whisper_features, device, weight_dtype, whisper_model, librosa_length,
        fps=fps, audio_padding_length_left=audio_pad_left,
        audio_padding_length_right=audio_pad_right,
    )
    video_num = len(whisper_chunks)

    # 2. 프레임 크기 + VP9 알파 추출
    H, W = avatar.frame_list_cycle[0].shape[:2]
    alpha_cycle   = None
    _erode_kernel = np.ones((3, 3), np.uint8)
    vp = getattr(avatar, 'video_path', '')
    if str(vp).lower().endswith('.webm'):
        alpha_cycle = _load_webm_alpha(str(vp), W, H, ffmpeg_bin)

    # 3. FFmpeg: BGRA → VP9 WebM with alpha (파일 출력)
    safe_audio  = _win_short_path(audio_path)
    safe_output = _win_short_path_new(str(output_path))
    cmd = [
        ffmpeg_exe, '-y', '-v', 'quiet',
        '-f', 'rawvideo', '-pix_fmt', 'bgra', '-s', f'{W}x{H}', '-r', str(fps),
        '-thread_queue_size', '512',
        '-i', 'pipe:0',
        '-thread_queue_size', '512',
        '-i', safe_audio,
        '-c:v', 'libvpx-vp9', '-pix_fmt', 'yuva420p',
        '-b:v', '0', '-crf', '33',
        '-cpu-used', '8', '-deadline', 'realtime',
        '-auto-alt-ref', '0', '-lag-in-frames', '0',
        '-row-mt', '1',
        '-c:a', 'libopus', '-b:a', '96k',
        '-shortest', safe_output,
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)

    blend_q: queue.Queue = queue.Queue(maxsize=64)

    def _gpu_loop_w():
        gen = datagen(whisper_chunks, avatar.input_latent_list_cycle, avatar.batch_size)
        try:
            for whisper_batch, latent_batch in gen:
                with torch.inference_mode():
                    af   = pe(whisper_batch.to(device))
                    lb   = latent_batch.to(dtype=unet.model.dtype)
                    pred = unet.model(lb, timesteps, encoder_hidden_states=af).sample
                with torch.inference_mode():
                    latents = (1 / vae.scaling_factor) * pred
                    dtype   = vae.vae.dtype
                    n       = latents.shape[0]
                    if n >= 4:
                        kl = latents[::2]
                        kd = vae.vae.decode(kl.to(dtype)).sample
                        ip = (kd[:-1] + kd[1:]) / 2
                        k  = kd.shape[0]
                        p  = min(k - 1, ip.shape[0])
                        mg = torch.stack([kd[:p], ip[:p]], dim=1).reshape(p * 2, *kd.shape[1:])
                        img = torch.cat([mg, kd[p:]], dim=0)[:n]
                    else:
                        img = vae.vae.decode(latents.to(dtype)).sample
                    img = (img / 2 + 0.5).clamp(0, 1)
                    img = (img * 255).round().to(torch.uint8)
                    img = img[:, [2, 1, 0], :, :].permute(0, 2, 3, 1).cpu().numpy()
                for raw in img:
                    blend_q.put(raw)
        except Exception as e:
            print(f"[webm] GPU 오류: {e}")
        finally:
            blend_q.put(None)

    def _cpu_blend_write_w():
        idx = 0
        try:
            while True:
                raw = blend_q.get()
                if raw is None or idx >= video_num:
                    break
                bbox = avatar.coord_list_cycle[idx % len(avatar.coord_list_cycle)]
                ori  = avatar.frame_list_cycle[idx % len(avatar.frame_list_cycle)].copy()
                if bbox is None:
                    frame = ori
                else:
                    x1, y1, x2, y2 = bbox
                    rf    = cv2.resize(raw.astype(np.uint8), (x2 - x1, y2 - y1))
                    mask  = avatar.mask_list_cycle[idx % len(avatar.mask_list_cycle)]
                    mc    = avatar.mask_coords_list_cycle[idx % len(avatar.mask_coords_list_cycle)]
                    frame = get_image_blending(ori, rf, bbox, mask, mc)
                # 알파 채널 결정 (원본 배경 프레임 기준으로 black-bg 키 적용)
                if alpha_cycle is not None:
                    a = alpha_cycle[idx % len(alpha_cycle)]
                else:
                    a = _black_bg_alpha(ori, _erode_kernel)
                bgra = np.dstack([frame, a])
                proc.stdin.write(bgra.tobytes())
                idx += 1
        except Exception as e:
            print(f"[webm] CPU 블렌딩 오류: {e}")
        finally:
            try:
                proc.stdin.close()
            except Exception:
                pass

    gpu_thread = threading.Thread(target=_gpu_loop_w, daemon=True)
    writer     = threading.Thread(target=_cpu_blend_write_w, daemon=True)
    gpu_thread.start()
    writer.start()
    gpu_thread.join()
    writer.join()
    proc.wait()
