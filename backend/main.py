# coding: utf-8
import sys
from pathlib import Path
_here = Path(__file__).resolve().parent    # backend/
_root = _here.parent                       # 프로젝트 루트

# 프로젝트 루트 → from backend.xxx 동작
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
# backend/ → routers/, models/ 등 동작
if str(_here) not in sys.path:
    sys.path.insert(1, str(_here))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.config import FRONTEND_DIR, VIDEO_DIR
from backend.database import engine, Base
# 🚀 1. 라우터 import (auth, chat, health 등 모두 포함)
from backend.routers import auth, chat, generation, llm, model_status, stt, health, pairing

# ─── FastAPI 앱 ───────────────────────────────────────────────
app = FastAPI(title="MoodTender API")

# 비동기 DB 테이블 초기화
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
app.mount("/video", StaticFiles(directory=str(VIDEO_DIR)), name="video")

# ─── 라우터 ───────────────────────────────────────────────────
app.include_router(auth.router,          prefix="/api", tags=["Auth"])
app.include_router(model_status.router,  prefix="/api", tags=["Model"])
app.include_router(generation.router,    prefix="/api", tags=["Generation"])
app.include_router(llm.router,           prefix="/api", tags=["LLM"])
app.include_router(stt.router,           prefix="/api", tags=["STT"])
app.include_router(pairing.router)
app.include_router(chat.router) 
# 🚀 2. 헬스 데이터 라우터 포함
app.include_router(health.router)

# ─── 프론트엔드 ───────────────────────────────────────────────
@app.get("/")
async def index():
    return FileResponse(FRONTEND_DIR / "index.html")

app.mount("/", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=7862, reload=False)