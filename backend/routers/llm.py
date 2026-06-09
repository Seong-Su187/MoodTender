from fastapi import APIRouter, HTTPException, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from jose import jwt, JWTError

from backend.database import get_db
from backend.models.domain import User
from backend.models.schemas import LLMResponse
from backend.services.openai_llm import OpenAIError, generate_bartender_reply
from backend.config import SECRET_KEY, ALGORITHM

router = APIRouter()

async def _get_user_id(authorization: str = Header(None), db: AsyncSession = Depends(get_db)) -> int:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="토큰이 없습니다.")
    try:
        payload = jwt.decode(authorization.split(" ")[1], SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    return user.id

@router.post("/llm/respond", response_model=LLMResponse)
async def respond(
    payload: dict,
    user_id: int = Depends(_get_user_id),
    db: AsyncSession = Depends(get_db)
):
    text = payload.get("text", "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="텍스트가 비어 있습니다.")
    try:
        reply, emotion = await generate_bartender_reply(user_id, text, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except OpenAIError as exc:
        raise HTTPException(status_code=502, detail=f"OpenAI API error: {exc}")
    return LLMResponse(reply=reply, emotion=emotion)
