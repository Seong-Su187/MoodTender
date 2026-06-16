"""
backend/routers/cocktail.py
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.database import get_db
from backend.models.domain import User, UserMemory
from backend.models.schemas import (
    IssueResponse, SuggestionRequest, SuggestionResponse,
    CraftCocktailRequest, CraftCocktailResponse, ReviewRequest
)
from backend.routers.auth import get_current_user_token
from backend.services.analytics_service import (
    generate_cocktail_prescription, generate_cocktail_result, calculate_mood_metrics 
)
from backend.services.rag_chain import generate_dashboard_rag_report
from backend.services.db_client import get_recent_health_metrics 

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard Cocktail"])

async def get_current_user_id(token_payload: dict, db: AsyncSession) -> int:
    username = token_payload.get("sub")
    if not username: raise HTTPException(status_code=401, detail="토큰 오류")
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user: raise HTTPException(status_code=404, detail="유저 찾기 실패")
    return user.id

@router.get("/issues", response_model=list[IssueResponse])
async def get_pending_issues(token_payload: dict = Depends(get_current_user_token), db: AsyncSession = Depends(get_db)):
    user_id = await get_current_user_id(token_payload, db)
    result = await db.execute(
        select(UserMemory)
        .where(UserMemory.user_id == user_id)
        .where(UserMemory.issue != None)
        .order_by(UserMemory.created_at.desc())
    )
    return [IssueResponse(id=m.id, issue=m.issue, emotion=m.sub_category or "평온", record_date=m.created_at.date(), prescribed_cocktail=m.prescribed_cocktail) for m in result.scalars().all()]

@router.post("/analyze-and-suggest", response_model=SuggestionResponse)
async def analyze_and_suggest(request: SuggestionRequest, token_payload: dict = Depends(get_current_user_token), db: AsyncSession = Depends(get_db)):
    user_id = await get_current_user_id(token_payload, db)
    result = await db.execute(select(UserMemory).where(UserMemory.id == request.issue_id, UserMemory.user_id == user_id))
    memory = result.scalar_one_or_none()
    if not memory: raise HTTPException(status_code=404, detail="기억 없음")
    llm_res = await generate_cocktail_prescription(memory.issue, memory.sub_category or "평온")
    return SuggestionResponse(emotion_analysis=llm_res["emotion_analysis"], checklist=llm_res["checklist"])

@router.post("/craft-cocktail", response_model=CraftCocktailResponse)
async def craft_cocktail(request: CraftCocktailRequest, token_payload: dict = Depends(get_current_user_token), db: AsyncSession = Depends(get_db)):
    user_id = await get_current_user_id(token_payload, db)
    result = await db.execute(select(UserMemory).where(UserMemory.id == request.issue_id, UserMemory.user_id == user_id))
    memory = result.scalar_one_or_none()
    if not memory: raise HTTPException(status_code=404, detail="기억 없음")
    llm_res = await generate_cocktail_result(request.selected_actions)
    memory.prescribed_cocktail = llm_res["cocktail_name"]
    await db.commit()
    return CraftCocktailResponse(expected_effect=llm_res["expected_effect"], cocktail_name=llm_res["cocktail_name"], message=llm_res["message"])

@router.post("/review")
async def submit_dashboard_review(request: ReviewRequest, token_payload: dict = Depends(get_current_user_token), db: AsyncSession = Depends(get_db)):
    user_id = await get_current_user_id(token_payload, db)
    result = await db.execute(select(UserMemory).where(UserMemory.id == request.issue_id, UserMemory.user_id == user_id))
    memory = result.scalar_one_or_none()
    if not memory: raise HTTPException(status_code=404, detail="기록 없음")
    memory.taste_rating = request.taste_rating
    memory.user_review = request.user_review
    memory.status = "COMPLETED" 
    await db.commit()
    return {"status": "success"}