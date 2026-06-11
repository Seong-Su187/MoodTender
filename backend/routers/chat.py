from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.database import get_db
from backend.models import domain
from backend.routers.auth import get_current_user_token
from backend.routers.llm import get_current_user_id
from datetime import datetime, timedelta

# 한국 시간 오프셋
KST_OFFSET = timedelta(hours=9)

router = APIRouter(tags=["Chat"])

@router.get("/api/chat/history")
async def get_chat_history(
    token_payload: dict = Depends(get_current_user_token),
    db: AsyncSession = Depends(get_db),
):
    # 1. 토큰에서 유저 ID 추출 (이미 구현된 get_current_user_id 사용)
    user_id = await get_current_user_id(token_payload, db)

    # 2. 해당 유저의 대화 기록을 과거순으로 정렬해서 가져오기
    result = await db.execute(
        select(domain.ChatMessage)
        .where(domain.ChatMessage.user_id == user_id)
        .order_by(domain.ChatMessage.id.asc()) 
    )
    records = result.scalars().all()
    
    # 3. 날짜별로 데이터 그룹화
    grouped_history = {}
    
    for r in records:
        # DB의 created_at을 한국 시간으로 변환
        if hasattr(r, 'created_at') and r.created_at:
            local_dt = r.created_at + KST_OFFSET
            date_str = local_dt.strftime("%Y-%m-%d")
            time_str = local_dt.strftime("%H:%M")
        else:
            # 기록이 없는 경우 현재 시간 사용
            date_str = datetime.now().strftime("%Y-%m-%d")
            time_str = ""

        if date_str not in grouped_history:
            grouped_history[date_str] = []

        grouped_history[date_str].append({
            "role": r.role,
            "content": r.content,
            "time": time_str
        })
        
    return {"history": grouped_history}