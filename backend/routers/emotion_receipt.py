from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from datetime import date

from backend.database import get_db
from backend.models import domain
from backend.routers.auth import get_current_user_token
from backend.routers.llm import get_current_user_id

router = APIRouter(tags=["EmotionReceipt"])


# -------------------------------------------------------
# GET: 유저의 감정 영수증 전체 조회
# -------------------------------------------------------
@router.get("/api/emotion/receipts")
async def get_emotion_receipts(
    token_payload: dict = Depends(get_current_user_token),
    db: AsyncSession = Depends(get_db),
):
    user_id = await get_current_user_id(token_payload, db)

    result = await db.execute(
        select(domain.EmotionReceipt)
        .where(domain.EmotionReceipt.user_id == user_id)
        .order_by(domain.EmotionReceipt.receipt_date.asc())
    )
    records = result.scalars().all()

    return {
        "receipts": [
            {
                "receipt_date": str(r.receipt_date),
                "dominant_sub_category": r.dominant_sub_category,
                "weather": r.weather,
                "recommended_cocktail": r.recommended_cocktail,
                "summary_note": r.summary_note,
            }
            for r in records
        ]
    }


# -------------------------------------------------------
# POST: 칵테일 직접 선택 → 오늘 영수증 생성 (다중 발급 가능)
# emotion_dictionary에서 해당 감정의 sub_category를 가져와 차곡차곡 추가 저장
# -------------------------------------------------------
class CocktailSelectRequest(BaseModel):
    emotion: str        # 기쁨 | 우울 | 불안 | 분노 | 지침 | 외로움 | 평온
    cocktail_name: str  # 주황 칵테일 | 파랑 칵테일 | ...


@router.post("/api/emotion/receipts/select-cocktail")
async def select_cocktail_receipt(
    body: CocktailSelectRequest,
    token_payload: dict = Depends(get_current_user_token),
    db: AsyncSession = Depends(get_db),
):
    user_id = await get_current_user_id(token_payload, db)

    # emotion_dictionary에서 해당 감정의 sub_category 랜덤 1개 조회
    result = await db.execute(
        select(domain.EmotionDictionary)
        .where(domain.EmotionDictionary.main_category == body.emotion)
        .order_by(func.random())
        .limit(1)
    )
    entry = result.scalars().first()
    sub_category = entry.sub_category if entry else body.emotion
    cocktail_direction = entry.cocktail_direction if entry else body.cocktail_name

    # 🚀 수정: 덮어쓰기(on_conflict_do_update)를 제거하고 데이터가 매번 쌓이도록 db.add 구조로 변경
    new_receipt = domain.EmotionReceipt(
        user_id=user_id,
        receipt_date=date.today(),
        dominant_sub_category=sub_category,
        recommended_cocktail=cocktail_direction,
        summary_note=f"오늘은 {body.cocktail_name}을 직접 선택하셨어요.",
    )
    
    db.add(new_receipt)
    await db.commit()

    return {"status": "ok", "sub_category": sub_category, "cocktail": cocktail_direction}