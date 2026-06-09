import asyncio
import threading
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from backend.services import ml_manager

router = APIRouter()

def sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

@router.get("/status")
async def get_status():
    return {
        "ready":   ml_manager.models_ready,
        "status":  ml_manager.loading_status,
        "error":   ml_manager.loading_error,
        "loading": ml_manager.loading_in_progress,
    }

@router.post("/load_model")
async def load_model():
    if ml_manager.models_ready:
        return {"message": "already_loaded"}
    if ml_manager.loading_in_progress:
        return {"message": "in_progress"}
    ml_manager.loading_in_progress = True
    threading.Thread(target=ml_manager.load_models, daemon=True).start()
    return {"message": "started"}

@router.get("/load_model/stream")
async def load_model_stream():
    async def gen():
        while not ml_manager.models_ready and not ml_manager.loading_error:
            yield sse({"status": ml_manager.loading_status, "ready": False, "loading": True})
            await asyncio.sleep(0.8)
        yield sse({"status": ml_manager.loading_status, "ready": ml_manager.models_ready, "error": ml_manager.loading_error, "loading": False})
    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
