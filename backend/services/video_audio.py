import os
import time
import subprocess
import json
import httpx
from backend.config import FFMPEG_PATH, OPENAI_API_KEY

def tts(text: str, path: str, voice: str, speed: float = 1.0):
    last_exc = None
    for attempt in range(3):
        try:
            with httpx.Client(timeout=60) as client:
                response = client.post(
                    "https://api.openai.com/v1/audio/speech",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    json={"model": "tts-1", "voice": voice, "input": text, "response_format": "wav", "speed": speed},
                )
                response.raise_for_status()
                raw = path + ".raw.wav"
                with open(raw, "wb") as f:
                    f.write(response.content)
            break
        except (httpx.TimeoutException, httpx.NetworkError) as e:
            last_exc = e
            print(f"[TTS] 재시도 {attempt + 1}/3: {e}")
            if attempt < 2:
                time.sleep(2 ** attempt)
    else:
        raise last_exc
    # 끝 음절 잘림 방지: 0.5초 무음 추가
    ffmpeg = os.path.join(FFMPEG_PATH, "ffmpeg.exe")
    subprocess.run(
        [ffmpeg, "-y", "-i", raw, "-af", "apad=pad_dur=0.5", path],
        capture_output=True,
    )
    os.remove(raw)

def get_audio_duration(audio_path: str) -> float:
    r = subprocess.run(
        [os.path.join(FFMPEG_PATH, "ffprobe.exe"), "-v", "quiet", "-print_format", "json", "-show_format", audio_path],
        capture_output=True, text=True,
    )
    return float(json.loads(r.stdout)["format"]["duration"])

def trim_video(src: str, duration: float, dst: str):
    subprocess.run(
        [os.path.join(FFMPEG_PATH, "ffmpeg.exe"), "-y", "-i", src, "-t", str(duration),
         "-c:v", "libx264", "-c:a", "aac", "-movflags", "+faststart", dst],
        capture_output=True,
    )
