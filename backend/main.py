# coding: utf-8
import sys
from pathlib import Path
_here = Path(__file__).resolve().parent   # backend/
_root = _here.parent                      # 프로젝트 루트
# 프로젝트 루트 → from backend.xxx 동작
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
# backend/ → scripts/, musetalk/ 등 ML 라이브러리 동작
if str(_here) not in sys.path:
    sys.path.insert(1, str(_here))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.config import FRONTEND_DIR, VIDEO_DIR
from backend.database import engine, Base
# 🚀 수정 부분 1: health 라우터 import 추가
from backend.routers import auth, generation, llm, model_status, stt, health 

# ─── FastAPI 앱 ───────────────────────────────────────────────
app = FastAPI(title="MoodTender API")

# 비동기 DB 테이블 초기화 (서버 시작 시 실행)
@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# ─── 미들웨어 ────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── 정적 파일 ───────────────────────────────────────────────
app.mount("/static/video", StaticFiles(directory=str(VIDEO_DIR)), name="video")
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

# ─── 라우터 ───────────────────────────────────────────────────
app.include_router(auth.router,         prefix="/api", tags=["Auth"])
app.include_router(model_status.router, prefix="/api", tags=["Model"])
app.include_router(generation.router,   prefix="/api", tags=["Generation"])
app.include_router(llm.router,          prefix="/api", tags=["LLM"])
app.include_router(stt.router,          prefix="/api", tags=["STT"])

# 🚀 수정 부분 2: 모바일 건강 데이터 라우터 등록
# (health.py 내부에 이미 prefix="/api/mobile"이 설정되어 있습니다)
app.include_router(health.router)

# ─── 프론트엔드 ───────────────────────────────────────────────
@app.get("/")
async def index():
    return FileResponse(FRONTEND_DIR / "index.html")

@app.get("/login")
async def login_page():
    return FileResponse(FRONTEND_DIR / "login.html")

@app.get("/loading")
async def loading_page():
    return FileResponse(FRONTEND_DIR / "loading.html")

@app.get("/dashboard")
async def dashboard_page():
    return FileResponse(FRONTEND_DIR / "dashboard.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=7862, reload=False)
