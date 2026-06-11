from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.database import get_db
from backend.models import domain
from backend.routers.auth import get_current_user_token
from backend.routers.llm import get_current_user_id
from datetime import datetime, timedelta

KST_OFFSET = timedelta(hours=9)

router = APIRouter(tags=["Chat"])

@router.get("/api/chat/history")
async def get_chat_history(
    token_payload: dict = Depends(get_current_user_token),
    db: AsyncSession = Depends(get_db),
):
    user_id = await get_current_user_id(token_payload, db)

    # 1. 해당 유저의 대화 기록을 과거순으로 정렬해서 가져옵니다.
    result = await db.execute(
        select(domain.ChatMessage)
        .where(domain.ChatMessage.user_id == user_id)
        .order_by(domain.ChatMessage.id.asc()) 
    )
    records = result.scalars().all()
    
    # 2. 날짜별로 데이터를 묶어줍니다.
    # 결과 형태: {"2026-06-10": [{"role": "user", "content": "..."}, ...], "2026-06-09": [...]}
    grouped_history = {}
    
    for r in records:
        # ChatMessage 테이블에 정형화된 날짜 필드(예: created_at)가 있다면 그것을 사용하고,
        # 없을 경우 안전하게 오늘 날짜로 처리하도록 방어 코드를 작성합니다.
        if hasattr(r, 'created_at') and r.created_at:
            # DB에는 UTC로 저장되어 있으므로 한국 시간(KST, UTC+9)으로 변환
            local_dt = r.created_at + KST_OFFSET
            date_str = local_dt.strftime("%Y-%m-%d")
        else:
            local_dt = None
            # 임시 가상 데이터용: 테이블에 날짜가 없다면 오늘 날짜로 묶음
            date_str = datetime.now().strftime("%Y-%m-%d")

        if date_str not in grouped_history:
            grouped_history[date_str] = []

        grouped_history[date_str].append({
            "role": r.role,
            "content": r.content,
            "time": local_dt.strftime("%H:%M") if local_dt else ""
        })
        
    return {"history": grouped_history}