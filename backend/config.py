import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ─── 경로 설정 ────────────────────────────────────────────────
BACKEND_DIR  = Path(__file__).resolve().parent
MUSETALK_DIR = BACKEND_DIR / "MuseTalk"
FRONTEND_DIR = BACKEND_DIR.parent / "frontend"
VIDEO_DIR    = BACKEND_DIR / "video"

sys.path.insert(0, str(MUSETALK_DIR))

if MUSETALK_DIR.exists():
    os.chdir(MUSETALK_DIR)

try:
    import importlib.util
    _spec = importlib.util.spec_from_file_location("musetalk_config", MUSETALK_DIR / "config.py")
    _mc   = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mc)
    FFMPEG_PATH = _mc.FFMPEG_PATH
except Exception:
    FFMPEG_PATH = os.environ.get("FFMPEG_PATH", "")

os.environ["PATH"] = FFMPEG_PATH + ";" + os.environ.get("PATH", "")

# ─── API & 인증 설정 ───────────────────────────────────────────
ANTHROPIC_API_KEY          = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY             = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL               = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini")
SECRET_KEY                 = os.environ.get("SECRET_KEY", "change-me-in-production")
ALGORITHM                  = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

if SECRET_KEY == "change-me-in-production":
    print("[경고] SECRET_KEY 환경변수를 설정하세요.")

# ─── 상수 ─────────────────────────────────────────────────────
VOICES = {
    "onyx":   "Onyx (중후한 남성)",
    "echo":   "Echo (남성)",
    "fable":  "Fable (표현력 남성)",
    "alloy":  "Alloy (중성)",
}
