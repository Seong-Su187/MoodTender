from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.database import get_db
from backend.models import domain
from datetime import datetime

router = APIRouter(tags=["Chat"])

@router.get("/api/chat/history/{user_id}")
async def get_chat_history(user_id: int, db: AsyncSession = Depends(get_db)):
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
            # datetime 객체인 경우 날짜 문자열(YYYY-MM-DD) 추출
            date_str = r.created_at.strftime("%Y-%m-%d")
        else:
            # 임시 가상 데이터용: 테이블에 날짜가 없다면 오늘 날짜로 묶음
            date_str = datetime.now().strftime("%Y-%m-%d")
            
        if date_str not in grouped_history:
            grouped_history[date_str] = []
            
        grouped_history[date_str].append({
            "role": r.role,
            "content": r.content,
            "time": r.created_at.strftime("%H:%M") if (hasattr(r, 'created_at') and r.created_at) else ""
        })
        
    return {"history": grouped_history}