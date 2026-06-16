from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models.domain import User, UserMemory
from backend.models.schemas import LLMRequest, LLMResponse
from backend.routers.auth import get_current_user_token
from backend.services.rag_chain import rag_chat, save_receipt, CHAINS
# 🚀 새로 추가한 analyze_cocktail_feedback 가져오기
from backend.services.analytics_service import extract_memory_from_chat, analyze_cocktail_feedback

router = APIRouter()

_user_session_data: dict[int, dict] = {}
_user_cocktail_done: set[int] = set()
_user_turn_counter: dict[int, int] = {}
_user_session_start: dict[int, datetime] = {}  # 현재 세션 시작 시각

# ---------------------------------------------------------
# [기존] 백그라운드에서 조용히 실행될 기억 저장 일꾼
# ---------------------------------------------------------
async def save_memory_task(user_id: int, chat_history: str):
    try:
        extracted = await extract_memory_from_chat(chat_history)
        
        if extracted.get("issue") and extracted.get("issue") != "없음":
            async for db in get_db():
                try:
                    new_memory = UserMemory(
                        user_id=user_id,
                        memory_text=chat_history, 
                        issue=extracted["issue"],
                        sub_category=extracted["emotion"], 
                        source_type="chat_auto_extract"
                    )
                    db.add(new_memory)
                    await db.commit()
                except Exception as db_error:
                    print(f"DB 저장 중 에러 발생: {db_error}")
                    await db.rollback() 
                break 
    except Exception as e:
        print(f"백그라운드 기억 저장 중 오류 발생: {e}")

# ---------------------------------------------------------
# 🚀 [새로 추가됨] 사용자의 대답이 칵테일 피드백인지 확인하고 완료 처리하는 일꾼
# ---------------------------------------------------------
async def check_and_update_feedback_task(user_id: int, user_text: str):
    try:
        async for db in get_db():
            try:
                # 1. 리뷰를 기다리고 있는 최신 PENDING 칵테일 처방 찾기
                pending_stmt = select(UserMemory).where(
                    UserMemory.user_id == user_id,
                    UserMemory.status == "PENDING",
                    UserMemory.prescribed_cocktail != None
                ).order_by(UserMemory.created_at.desc()).limit(1)
                
                pending_res = await db.execute(pending_stmt)
                pending_m = pending_res.scalar_one_or_none()
                
                if pending_m:
                    # 2. LLM에게 피드백인지 물어보기
                    feedback_result = await analyze_cocktail_feedback(
                        user_input=user_text, 
                        cocktail_name=pending_m.prescribed_cocktail, 
                        issue=pending_m.issue
                    )
                    
                    # 3. 피드백이 맞다면 상태를 COMPLETED로 변경!
                    if feedback_result.get("is_feedback") is True:
                        pending_m.status = "COMPLETED"
                        pending_m.taste_rating = feedback_result.get("taste_rating", 3)
                        pending_m.user_review = feedback_result.get("user_review", user_text)
                        await db.commit()
                        print(f"🍹 [피드백 자동 감지 완료] 칵테일: {pending_m.prescribed_cocktail}, 평점: {pending_m.taste_rating}")
            except Exception as db_error:
                print(f"피드백 감지 DB 에러: {db_error}")
                await db.rollback()
            break
    except Exception as e:
        print(f"피드백 백그라운드 태스크 오류: {e}")

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
    background_tasks: BackgroundTasks, 
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

        if cocktail_line and not cocktail_done:
            _user_cocktail_done.add(user_id)
            _user_session_data[user_id] = {"emotion": emotion, "cocktail": cocktail_line}

        # ---------------------------------------------------------
        # 🚀 [핵심] 백그라운드 일꾼 2명 동시 파견!
        # 1. 새 사건을 감지해서 저장하는 일꾼
        # 2. 바텐더의 질문에 피드백을 남겼는지 검사해서 PENDING을 닫는 일꾼
        # ---------------------------------------------------------
        current_chat_turn = f"사용자: {user_text}\n바텐더: {reply}"
        background_tasks.add_task(save_memory_task, user_id, current_chat_turn)
        background_tasks.add_task(check_and_update_feedback_task, user_id, user_text)

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