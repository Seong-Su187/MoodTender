"""
llm.py
/llm/respond 엔드포인트
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.domain import User
from backend.models.schemas import LLMRequest, LLMResponse
from backend.routers.auth import get_current_user_token
from backend.services.rag_chain import rag_chat, save_receipt, CHAINS
from sqlalchemy import text

router = APIRouter()

_user_session_data: dict[int, dict] = {}
_user_cocktail_done: set[int] = set()
_user_turn_counter: dict[int, int] = {}

async def get_current_user_id(
    token_payload: dict,
    db: AsyncSession,
) -> int:
    username = token_payload.get("sub")

    if not username:
        raise HTTPException(status_code=401, detail="토큰에 사용자 정보가 없습니다.")

    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    return user.id


@router.post("/llm/respond", response_model=LLMResponse)
async def respond(
    payload: LLMRequest,
    token_payload: dict = Depends(get_current_user_token),
    db: AsyncSession = Depends(get_db),
):
    try:
        user_id = await get_current_user_id(token_payload, db)

        user_text = payload.text.strip()
        speed = getattr(payload, "speed", 1.0)

        if not user_text:
            raise HTTPException(status_code=400, detail="메시지가 비어 있습니다.")

        if user_text.lower() in {"안녕", "안녕하세요", "하이", "ㅎㅇ", "hi", "hello"}:
            return LLMResponse(
                reply="어서 와요. 오늘은 어떤 기분으로 오셨어요?",
                emotion="평온",
            )
        
        session_id = payload.session_id
        cocktail_done = user_id in _user_cocktail_done

        _user_turn_counter[user_id] = _user_turn_counter.get(user_id, 0) + 1
        turn_count = _user_turn_counter[user_id]

        reply, emotion, cocktail_line = await rag_chat(
            db=db,
            user_id=user_id,
            user_text=user_text,
            speed=speed,
            session_id=session_id,
            cocktail_done=cocktail_done,
            user_turn_count=turn_count,
        )

        if cocktail_line and not cocktail_done:
            _user_cocktail_done.add(user_id)
            _user_session_data[user_id] = {"emotion": emotion, "cocktail": cocktail_line}

        return LLMResponse(reply=reply, emotion=emotion)

    except HTTPException:
        raise

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"LLM 처리 중 오류가 발생했습니다: {e}",
        )
    
@router.post("/llm/receipt")
async def create_receipt(
    token_payload: dict = Depends(get_current_user_token),
    db: AsyncSession = Depends(get_db),
):
    try:
        user_id = await get_current_user_id(token_payload, db)
        
        (_, _, _, _, receipt_chain, _) = CHAINS

        # 오늘 대화 조회
        result = await db.execute(
            text("""
                SELECT role, content FROM chat_messages
                WHERE user_id = :user_id
                  AND created_at >= CURRENT_DATE
                ORDER BY created_at ASC
            """),
            {"user_id": user_id},
        )
        rows = result.fetchall()
        conversation_text = "\n".join(
            f"{'사용자' if r[0] == 'user' else '바텐더'}: {r[1]}"
            for r in rows
        )

        session_data = _user_session_data.get(user_id, {})
        emotion = session_data.get("emotion", "")
        cocktail = session_data.get("cocktail", "")

        await save_receipt(
            db=db,
            user_id=user_id,
            emotion=emotion,       
            sub_emotion=emotion,
            cocktail=cocktail,
            conversation_text=conversation_text,
            receipt_chain=receipt_chain,
        )

        _user_cocktail_done.discard(user_id)
        _user_session_data.pop(user_id, None)
        _user_turn_counter.pop(user_id, None)

        return {"status": "ok"}

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"영수증 생성 오류: {e}")