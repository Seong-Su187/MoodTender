from __future__ import annotations

import os
import re
import time
import json
import tempfile
import shutil
import threading
import asyncio
from pathlib import Path
from fastapi import APIRouter, Form, UploadFile, File
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse

from backend.config import VOICES, VIDEO_DIR
from backend.services import ml_manager
from backend.services.video_audio import tts, get_audio_duration, trim_video
from scripts.realtime_inference import Avatar

router = APIRouter()
_avatar_load_lock = threading.Lock()


def _get_video_avatar(avatar_name: str) -> Avatar:
    """video_avatars 딕셔너리에서 반환. 없으면 lazy load로 폴백."""
    av = ml_manager.video_avatars.get(avatar_name)
    if av is not None:
        return av

    # startup 로드가 안 된 경우 폴백 (스레드 안전)
    with _avatar_load_lock:
        av = ml_manager.video_avatars.get(avatar_name)
        if av is not None:
            return av

        video_path = str(VIDEO_DIR / avatar_name)
        stem = Path(avatar_name).stem
        avatar_id = "video_" + re.sub(r"[^\w]", "_", stem)[:40]

        cache_info = Path(f"./results/{ml_manager.args.version}/avatars/{avatar_id}/avator_info.json")
        preparation = not cache_info.exists()

        av = Avatar(
            avatar_id=avatar_id,
            video_path=video_path,
            bbox_shift=0,
            batch_size=ml_manager.args.batch_size,
            preparation=preparation,
        )
        av.input_latent_list_cycle = [t.to(ml_manager.device) for t in av.input_latent_list_cycle]
        ml_manager.video_avatars[avatar_name] = av
        return av


def _get_default_avatar() -> Avatar | None:
    """avatar_name이 없을 때 사용할 기본 아바타. (backend/video/에 영상이 하나뿐이라는 전제)"""
    if ml_manager.custom_avatar is not None:
        return ml_manager.custom_avatar
    if ml_manager.video_avatars:
        return next(iter(ml_manager.video_avatars.values()))
    return None

def sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

@router.get("/voices")
async def get_voices():
    return [{"id": k, "name": v} for k, v in VOICES.items()]

@router.get("/avatars")
async def list_avatars():
    if not VIDEO_DIR.exists():
        return []
    result = []
    for f in sorted(VIDEO_DIR.glob("*.mp4")) + sorted(VIDEO_DIR.glob("*.webm")):
        label = f.stem.replace("_", " ")
        label = re.sub(r"^\d+\s*", "", label)
        label = re.sub(r"\s+\d{10,}$", "", label).strip()
        result.append({"name": f.name, "label": label, "type": f.suffix.lstrip(".")})
    return result

@router.post("/prepare_avatar")
async def prepare_avatar(avatar_name: str = Form(...)):
    """드롭다운 선택 시 미리 아바타 준비 (preparation=True → 캐시 저장)."""
    if not ml_manager.models_ready:
        return JSONResponse({"error": "모델이 로드되지 않았습니다."}, status_code=400)

    loop = asyncio.get_event_loop()
    q: asyncio.Queue = asyncio.Queue()

    def push(data):
        loop.call_soon_threadsafe(q.put_nowait, data)

    def run():
        try:
            push({"status": "아바타 준비 중..."})
            _get_video_avatar(avatar_name)
            push({"status": "준비 완료!", "done": True})
        except Exception as e:
            push({"error": str(e), "done": True})

    threading.Thread(target=run, daemon=True).start()

    async def stream():
        while True:
            item = await asyncio.wait_for(q.get(), timeout=300)
            yield sse(item)
            if item.get("done") or item.get("error"):
                break

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

@router.post("/generate")
async def generate(text: str = Form(...), voice: str = Form("onyx"), avatar_name: str = Form(None), speed: float = Form(1.0)):
    if not ml_manager.models_ready:
        return JSONResponse({"error": "모델이 로드되지 않았습니다."}, status_code=400)

    loop = asyncio.get_event_loop()
    q: asyncio.Queue = asyncio.Queue()

    def push(data):
        loop.call_soon_threadsafe(q.put_nowait, data)

    def run():
        tmp_dir = tempfile.mkdtemp()
        t_total = time.time()
        try:
            push({"status": "TTS 변환 중..."})
            audio_path = os.path.join(tmp_dir, "tts.wav")
            out_name   = f"output_{int(time.time())}"

            t0 = time.time()
            tts(text, audio_path, voice, speed)
            duration = get_audio_duration(audio_path)
            print(f"[시간] TTS:      {time.time()-t0:.1f}초 (음성 {duration:.1f}초)")

            av = _get_video_avatar(avatar_name) if avatar_name else _get_default_avatar()
            if av is None:
                push({"error": "아바타를 선택해주세요.", "done": True})
                return
            push({"status": f"영상 생성 중... (음성 {duration:.1f}초)"})
            t0 = time.time()
            av.inference(audio_path=audio_path, out_vid_name=out_name, fps=ml_manager.args.fps, skip_save_images=False)
            print(f"[시간] MuseTalk: {time.time()-t0:.1f}초")

            out_vid = os.path.join(av.video_out_path, out_name + ".mp4")
            trimmed = os.path.join(av.video_out_path, out_name + "_trimmed.mp4")
            if os.path.exists(out_vid):
                t0 = time.time()
                trim_video(out_vid, duration, trimmed)
                print(f"[시간] FFmpeg:   {time.time()-t0:.1f}초")
                print(f"[시간] 합계:     {time.time()-t_total:.1f}초")
                final = trimmed if os.path.exists(trimmed) else out_vid
                push({"status": "완료!", "done": True, "video_path": final})
            else:
                push({"error": "영상 생성 실패", "done": True})
        except Exception as e:
            push({"error": str(e), "done": True})
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    threading.Thread(target=run, daemon=True).start()

    async def stream():
        while True:
            item = await asyncio.wait_for(q.get(), timeout=300)
            yield sse(item)
            if item.get("done") or item.get("error"):
                break

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

@router.post("/init_avatar_video")
async def init_avatar_video(
    file: UploadFile = File(...),
    bbox_shift: int = Form(0),
):
    """영상 직접 업로드 → LivePortrait 없이 바로 MuseTalk 아바타 생성"""
    if not ml_manager.models_ready:
        return JSONResponse({"error": "모델이 로드되지 않았습니다."}, status_code=400)

    loop = asyncio.get_event_loop()
    q: asyncio.Queue = asyncio.Queue()

    def push(data):
        loop.call_soon_threadsafe(q.put_nowait, data)

    tmp_dir     = tempfile.mkdtemp()
    video_path  = os.path.join(tmp_dir, file.filename)
    contents    = await file.read()
    with open(video_path, "wb") as f:
        f.write(contents)

    def run():
        t0 = time.time()
        try:
            push({"status": "아바타 준비 중..."})
            if os.path.exists(ml_manager.CUSTOM_AVATAR_CACHE):
                shutil.rmtree(ml_manager.CUSTOM_AVATAR_CACHE)

            ml_manager.custom_avatar = Avatar(
                avatar_id="custom_avatar", video_path=video_path,
                bbox_shift=bbox_shift, batch_size=ml_manager.args.batch_size, preparation=True,
            )
            ml_manager.custom_avatar.input_latent_list_cycle = [
                t.to(ml_manager.device) for t in ml_manager.custom_avatar.input_latent_list_cycle
            ]
            print(f"[시간] 영상 아바타 준비: {time.time()-t0:.1f}초")
            push({"status": "아바타 준비 완료!", "done": True})
        except Exception as e:
            push({"error": str(e), "done": True})

    threading.Thread(target=run, daemon=True).start()

    async def stream():
        while True:
            item = await asyncio.wait_for(q.get(), timeout=300)
            yield sse(item)
            if item.get("done") or item.get("error"):
                break

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

@router.get("/video")
async def serve_video(path: str):
    if not os.path.exists(path):
        return JSONResponse({"error": "파일 없음"}, status_code=404)
    mime = "video/webm" if path.lower().endswith(".webm") else "video/mp4"
    return FileResponse(path, media_type=mime)

@router.post("/generate_stream")
async def generate_stream(text: str = Form(...), voice: str = Form("onyx"), avatar_name: str = Form(None), speed: float = Form(1.0)):
    if not ml_manager.models_ready:
        return JSONResponse({"error": "모델이 로드되지 않았습니다."}, status_code=400)

    if not avatar_name and _get_default_avatar() is None:
        return JSONResponse({"error": "아바타를 선택해주세요."}, status_code=400)

    from stream_inference import inference_stream as _infer_stream
    from config import FFMPEG_PATH

    loop    = asyncio.get_event_loop()
    async_q: asyncio.Queue = asyncio.Queue()

    def push(data):
        loop.call_soon_threadsafe(async_q.put_nowait, data)

    def run():
        tmp_dir = tempfile.mkdtemp()
        t0 = time.time()
        try:
            # TTS와 병렬로 GPU 웜업 (콜드 스타트 흡수)
            import torch as _torch
            audio_path = os.path.join(tmp_dir, "tts.wav")
            tts(text, audio_path, voice, speed)
            print(f"[Stream] TTS: {time.time()-t0:.1f}초")

            av = _get_video_avatar(avatar_name) if avatar_name else _get_default_avatar()
            first = True
            for chunk in _infer_stream(
                av, audio_path, ml_manager.args.fps, FFMPEG_PATH,
                ml_manager.pe, ml_manager.unet, ml_manager.vae, ml_manager.timesteps,
                ml_manager.whisper, ml_manager.audio_processor,
                ml_manager.weight_dtype, ml_manager.device,
                ml_manager.args.audio_padding_length_left,
                ml_manager.args.audio_padding_length_right,
                taesd=ml_manager.taesd_decoder,
            ):
                if first:
                    print(f"[Stream] 첫 청크: {time.time()-t0:.1f}초")
                    first = False
                push(chunk)
            print(f"[Stream] 완료: {time.time()-t0:.1f}초")
        except Exception as e:
            print(f"[Stream] 오류: {e}")
        finally:
            push(None)
            shutil.rmtree(tmp_dir, ignore_errors=True)

    threading.Thread(target=run, daemon=True).start()

    async def stream():
        while True:
            chunk = await asyncio.wait_for(async_q.get(), timeout=300)
            if chunk is None:
                break
            yield chunk

    return StreamingResponse(
        stream(),
        media_type="video/mp4",
        headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"},
    )
