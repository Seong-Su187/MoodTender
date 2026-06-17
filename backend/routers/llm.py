from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from backend.database import get_db
from backend.models.domain import User, UserMemory
from backend.models.schemas import LLMRequest, LLMResponse, ReviewRequest
from backend.routers.auth import get_current_user_token
from backend.services.rag_chain import rag_chat, save_receipt, CHAINS, _make_llm

router = APIRouter()

_user_session_data: dict[int, dict] = {}
_user_cocktail_done: set[int] = set()
_user_turn_counter: dict[int, int] = {}
_user_session_start: dict[int, datetime] = {}

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

@router.get("/llm/greeting")
async def get_initial_greeting(
    token_payload: dict = Depends(get_current_user_token),
    db: AsyncSession = Depends(get_db)
):
    try:
        user_id = await get_current_user_id(token_payload, db)

        pending_stmt = select(UserMemory).where(
            UserMemory.user_id == user_id,
            UserMemory.status == "PENDING",
            UserMemory.prescribed_cocktail != None
        ).order_by(UserMemory.created_at.desc()).limit(1)

        pending_res = await db.execute(pending_stmt)
        pending_m = pending_res.scalar_one_or_none()

        if pending_m:
            greeting_prompt = ChatPromptTemplate.from_messages([
                ("system", """당신은 따뜻한 AI 바텐더 MoodTender입니다.
                손님이 이전에 '{issue}' 문제로 '{cocktail}' 칵테일과 행동 지침을 추천받았습니다.
                오늘 다시 방문한 손님에게 "어서 오세요"로 시작해서, 지난번의 고민(issue)은 좀 어떠신지, 추천받은 행동은 도움이 되었는지 다정하게 묻는 첫 인사를 1~2문장으로 작성하세요.""")
            ]) | _make_llm(0.7) | StrOutputParser()

            dynamic_greeting = await greeting_prompt.ainvoke({
                "issue": pending_m.issue,
                "cocktail": pending_m.prescribed_cocktail
            })
            return {
                "reply": dynamic_greeting,
                "emotion": "평온",
                "pending_issue_id": pending_m.id,
                "pending_cocktail": pending_m.prescribed_cocktail,
            }
        else:
            return {"reply": "어서오세요. 오늘 마음은 어떤 잔에 담아드릴까요?", "emotion": "평온", "pending_issue_id": None, "pending_cocktail": None}

    except Exception:
        return {"reply": "어서오세요. 오늘 마음은 어떤 잔에 담아드릴까요?", "emotion": "평온", "pending_issue_id": None, "pending_cocktail": None}

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
            pending_stmt = select(UserMemory).where(
                UserMemory.user_id == user_id,
                UserMemory.status == "PENDING",
                UserMemory.prescribed_cocktail != None
            ).order_by(UserMemory.created_at.desc()).limit(1)

            pending_res = await db.execute(pending_stmt)
            pending_m = pending_res.scalar_one_or_none()

            if pending_m:
                greeting_prompt = ChatPromptTemplate.from_messages([
                    ("system", """당신은 따뜻한 AI 바텐더 MoodTender입니다.
                    손님이 이전에 '{issue}' 문제로 '{cocktail}' 칵테일과 행동 지침을 추천받았습니다.
                    오늘 다시 방문한 손님에게 "어서 오세요"로 시작해서, 지난번의 고민(issue)은 좀 어떠신지, 추천받은 행동은 도움이 되었는지 다정하게 묻는 첫 인사를 1~2문장으로 작성하세요.""")
                ]) | _make_llm(0.7) | StrOutputParser()

                dynamic_greeting = await greeting_prompt.ainvoke({
                    "issue": pending_m.issue,
                    "cocktail": pending_m.prescribed_cocktail
                })
                return LLMResponse(reply=dynamic_greeting, emotion="평온")
            else:
                return LLMResponse(reply="어서 와요. 오늘은 어떤 기분으로 오셨어요?", emotion="평온")

        session_id = payload.session_id
        cocktail_done = user_id in _user_cocktail_done

        _user_turn_counter[user_id] = _user_turn_counter.get(user_id, 0) + 1
        turn_count = _user_turn_counter[user_id]

        if user_id not in _user_session_start:
            _user_session_start[user_id] = datetime.now(timezone.utc).replace(tzinfo=None)

        reply, emotion, cocktail_line = await rag_chat(
            db=db,
            user_id=user_id,
            user_text=user_text,
            speed=speed,
            session_id=session_id,
            session_start=_user_session_start[user_id],
            cocktail_done=cocktail_done,
            user_turn_count=turn_count,
        )

        if cocktail_line:
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

        (_, _, _, _, receipt_chain, _, _, _) = CHAINS

        result = await db.execute(
            text("""
                SELECT role, content FROM chat_messages
                WHERE user_id = :user_id
                  AND created_at >= (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Seoul')::date
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
        _user_session_start[user_id] = datetime.now(timezone.utc).replace(tzinfo=None)

        return {"status": "ok"}

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"영수증 생성 오류: {e}")


@router.post("/llm/chat-review")
async def submit_chat_review(
    request: ReviewRequest,
    token_payload: dict = Depends(get_current_user_token),
    db: AsyncSession = Depends(get_db),
):
    try:
        user_id = await get_current_user_id(token_payload, db)

        result = await db.execute(
            select(UserMemory).where(UserMemory.id == request.issue_id, UserMemory.user_id == user_id)
        )
        memory = result.scalar_one_or_none()
        if not memory:
            raise HTTPException(status_code=404, detail="해당 기록을 찾을 수 없습니다.")

        memory.taste_rating = request.taste_rating
        memory.user_review = request.user_review or "채팅에서 평가함"
        memory.status = "COMPLETED"
        await db.commit()

        if request.taste_rating <= 2:
            _user_cocktail_done.discard(user_id)

        return {"status": "ok", "low_rating": request.taste_rating <= 2}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"리뷰 저장 오류: {e}")
