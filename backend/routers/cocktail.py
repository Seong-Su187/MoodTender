"""
backend/routers/cocktail.py - 대시보드 및 칵테일 처방 로직 (완벽 해결본)
"""
from datetime import datetime
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
    generate_cocktail_prescription, 
    generate_cocktail_result,
    calculate_mood_metrics 
)
from backend.services.rag_chain import generate_dashboard_rag_report
from backend.services.db_client import get_recent_health_metrics 

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard Cocktail"])

async def get_current_user_id(token_payload: dict, db: AsyncSession) -> int:
    username = token_payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="토큰 오류")
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="유저를 찾을 수 없습니다.")
    return user.id

# 🚀 프론트엔드 자바스크립트가 Null 때문에 터지는 것을 방지하는 무적의 코드
@router.get("/issues")
async def get_pending_issues(
    token_payload: dict = Depends(get_current_user_token),
    db: AsyncSession = Depends(get_db)
):
    user_id = await get_current_user_id(token_payload, db)
    
    result = await db.execute(
        select(UserMemory)
        .where(UserMemory.user_id == user_id)
        .where(UserMemory.status == "PENDING")
        .where(UserMemory.issue != None)
        .where(UserMemory.issue != "없음")
        .order_by(UserMemory.created_at.desc())
    )
    memories = result.scalars().all()
    
    issues_list = []
    for m in memories:
        # 날짜 포맷 안전하게 변환
        date_str = m.created_at.strftime("%Y-%m-%d") if m.created_at else "2026-06-16"
            
        issues_list.append({
            "id": m.id,
            "issue": m.issue or "일상적인 고민",
            "emotion": m.sub_category or "평온", 
            "record_date": date_str,
            # 🔥 핵심: 프론트엔드 에러 방지를 위해 None 대신 무조건 빈 문자열("") 반환
            "prescribed_cocktail": m.prescribed_cocktail or "" 
        })
    return issues_list

@router.post("/analyze-and-suggest", response_model=SuggestionResponse)
async def analyze_and_suggest(
    request: SuggestionRequest,
    token_payload: dict = Depends(get_current_user_token),
    db: AsyncSession = Depends(get_db)
):
    user_id = await get_current_user_id(token_payload, db)
    
    result = await db.execute(
        select(UserMemory).where(UserMemory.id == request.issue_id, UserMemory.user_id == user_id)
    )
    memory = result.scalar_one_or_none()
    
    if not memory:
        raise HTTPException(status_code=404, detail="해당 기억을 찾을 수 없습니다.")

    # 🚀 [품질 개선] 상황과 고민을 명확하게 LLM에 주입하여 엉뚱한 행동을 추천하지 않도록 유도합니다.
    context_issue = f"[핵심 고민]: {memory.issue}\n[상세 상황]: {memory.memory_text}\n위 상황을 부드럽게 해결하고 마음을 편안하게 할 수 있는 실질적인 행동을 제안해주세요."

    llm_response = await generate_cocktail_prescription(
        issue=context_issue, 
        emotion=memory.sub_category or "평온"
    )

    return SuggestionResponse(
        emotion_analysis=llm_response["emotion_analysis"], 
        checklist=llm_response["checklist"]
    )

@router.post("/craft-cocktail", response_model=CraftCocktailResponse)
async def craft_cocktail(
    request: CraftCocktailRequest,
    token_payload: dict = Depends(get_current_user_token),
    db: AsyncSession = Depends(get_db)
):
    user_id = await get_current_user_id(token_payload, db)
    
    result = await db.execute(
        select(UserMemory).where(UserMemory.id == request.issue_id, UserMemory.user_id == user_id)
    )
    memory = result.scalar_one_or_none()
    
    if not memory:
        raise HTTPException(status_code=404, detail="해당 기억을 찾을 수 없습니다.")

    llm_response = await generate_cocktail_result(request.selected_actions)

    memory.prescribed_cocktail = llm_response["cocktail_name"]
    await db.commit()

    return CraftCocktailResponse(
        expected_effect=llm_response["expected_effect"],
        cocktail_name=llm_response["cocktail_name"],
        message=llm_response["message"]
    )

@router.post("/review")
async def submit_dashboard_review(
    request: ReviewRequest,
    token_payload: dict = Depends(get_current_user_token),
    db: AsyncSession = Depends(get_db)
):
    user_id = await get_current_user_id(token_payload, db)
    
    result = await db.execute(
        select(UserMemory).where(UserMemory.id == request.issue_id, UserMemory.user_id == user_id)
    )
    memory = result.scalar_one_or_none()
    
    if not memory:
        raise HTTPException(status_code=404, detail="해당 기록을 찾을 수 없습니다.")
        
    memory.taste_rating = request.taste_rating
    memory.user_review = request.user_review
    memory.status = "COMPLETED" 
    
    await db.commit()
    return {"status": "success", "message": "리뷰가 성공적으로 반영되었습니다."}

@router.get("/chart-data")
async def get_chart_data(
    token_payload: dict = Depends(get_current_user_token),
    db: AsyncSession = Depends(get_db)
):
    user_id = await get_current_user_id(token_payload, db)
    
    result = await db.execute(
        select(UserMemory)
        .where(UserMemory.user_id == user_id)
        .where(UserMemory.status == "COMPLETED")
        .where(UserMemory.taste_rating != None)
        .order_by(UserMemory.created_at.asc())
        .limit(10)
    )
    memories = result.scalars().all()
    
    return [
        {
            "date": m.created_at.strftime("%m/%d") if m.created_at else "",
            "rating": m.taste_rating,
            "cocktail_name": m.prescribed_cocktail or "알 수 없음",
            "issue": m.issue or "일상"
        } for m in memories
    ]

@router.get("/report")
async def get_weekly_ai_report(
    token_payload: dict = Depends(get_current_user_token),
    db: AsyncSession = Depends(get_db)
):
    user_id = await get_current_user_id(token_payload, db)
    
    health_rows = await get_recent_health_metrics(db, user_id, days=7)
    metrics_result = calculate_mood_metrics(health_rows, period_days=1)
    
    html_report = await generate_dashboard_rag_report(db, user_id, metrics_result)
    
    return {"report": html_report}