from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.domain import User
from backend.models.schemas import LLMRequest, LLMResponse
from backend.routers.auth import get_current_user_token
from backend.services.openai_llm import OpenAIError, generate_bartender_reply
from backend.services.rag_chain import (
    build_chains,
    new_session_id,
    run_first_turn,
    run_free_chat,
    finalize_memory,
)

router = APIRouter()


def is_casual_greeting(text: str) -> bool:
    text = text.strip().lower()
    return text in {
        "안녕","안녕하세요","하이", "ㅎㅇ","hi","hello","어","응",
        "네","넵","ㅇㅇ","아","음","흠",
    }


def is_meaningful_emotion_input(text: str) -> bool:
    text = text.strip()

    if not text:
        return False

    emotion_or_context_keywords = [
        "오늘", "하루", "아침", "점심", "저녁", "밤",
        "회사", "학교", "수업", "과제", "시험", "발표", "면접",
        "친구", "가족", "엄마", "아빠", "동료", "상사", "팀원",
        "힘들", "지쳤", "피곤", "우울", "슬퍼", "속상", "외로",
        "불안", "긴장", "걱정", "무서", "막막", "답답",
        "화나", "짜증", "억울", "서운", "부담",
        "좋았", "행복", "기뻐", "설렜", "뿌듯", "편안",
    ]

    if any(keyword in text for keyword in emotion_or_context_keywords):
        return True

    if len(text) < 8:
        return False

    return False


try:
    emotion_chain, summary_chain, receipt_chain, free_chat_chain = build_chains()
except Exception as exc:
    emotion_chain = None
    summary_chain = None
    receipt_chain = None
    free_chat_chain = None
    print(f"[LLM] RAG chain init failed: {exc}")


async def get_current_user_id(
    token_payload: dict,
    db: AsyncSession,
) -> int:
    username = token_payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="토큰에 사용자 정보가 없습니다.")

    result = await db.execute(select(User).where(User.username == username))
    db_user = result.scalar_one_or_none()

    if not db_user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    return db_user.id


@router.post("/llm/respond", response_model=LLMResponse)
async def respond_with_rag(
    payload: LLMRequest,
    token_payload: dict = Depends(get_current_user_token),
    db: AsyncSession = Depends(get_db),
):
    user_id = await get_current_user_id(token_payload, db)

    if is_casual_greeting(payload.text):
        return LLMResponse(reply="어서 와요. 오늘은 어떤 기분으로 오셨어요?")

    if not is_meaningful_emotion_input(payload.text):
        if not free_chat_chain:
            raise HTTPException(status_code=500, detail="Free chat chain is not initialized.")

        try:
            reply = await run_free_chat(
                free_chat_chain=free_chat_chain,
                user_id=user_id,
                user_text=payload.text,
                history=[],
            )
            return LLMResponse(reply=reply)
        except OpenAIError as exc:
            raise HTTPException(status_code=502, detail=f"OpenAI API error: {exc}")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Free chat error: {exc}")

    if not all([emotion_chain, summary_chain, receipt_chain]):
        raise HTTPException(status_code=500, detail="RAG chain is not initialized.")

    session_id = new_session_id()

    try:
        bartender_result, emotion, cocktail = await run_first_turn(
            emotion_chain=emotion_chain,
            summary_chain=summary_chain,
            receipt_chain=receipt_chain,
            user_id=user_id,
            session_id=session_id,
            user_text=payload.text,
            db=db,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"RAG error: {exc}")

    reply = " ".join(
        part
        for part in [
            bartender_result.get("bartender_reply"),
            bartender_result.get("cocktail_line"),
        ]
        if part
    ).strip()

    conversation_text = f"""
    사용자: {payload.text}
    바텐더: {reply}
    """

    await finalize_memory(
        summary_chain=summary_chain,
        user_id=user_id,
        session_id=session_id,
        emotion=emotion,
        cocktail=cocktail,
        bartender_result=bartender_result,
        conversation_text=conversation_text,
)

    return LLMResponse(reply=reply)


@router.post("/llm/simple", response_model=LLMResponse)
async def respond_simple(
    payload: LLMRequest,
    token_payload: dict = Depends(get_current_user_token),
    db: AsyncSession = Depends(get_db),
):
    user_id = await get_current_user_id(token_payload, db)

    try:
        result = await generate_bartender_reply(user_id, payload.text, db)

        if isinstance(result, tuple):
            reply, emotion = result
        else:
            reply = result
            emotion = ""

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except OpenAIError as exc:
        raise HTTPException(status_code=502, detail=f"OpenAI API error: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"LLM error: {exc}")

    return LLMResponse(reply=reply, emotion=emotion)