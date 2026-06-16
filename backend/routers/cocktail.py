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
    calculate_mood_metrics # 🚀 주간 통계 계산을 위해 임포트
)
# 🚀 rag_chain에 이미 만들어져 있는 리포트 생성 파이프라인 및 헬스 데이터 조회기 가져오기
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

@router.get("/issues", response_model=list[IssueResponse])
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
    
    return [
        IssueResponse(
            id=m.id,
            issue=m.issue,
            emotion=m.sub_category or "평온", 
            record_date=m.created_at.date()
        ) for m in memories
    ]

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

    llm_response = await generate_cocktail_prescription(
        issue=memory.issue, 
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

# 🚀 [새로 추가됨] 5. AI 바텐더의 주간 맞춤형 감정 리포트 조회 API
@router.get("/report")
async def get_weekly_ai_report(
    token_payload: dict = Depends(get_current_user_token),
    db: AsyncSession = Depends(get_db)
):
    user_id = await get_current_user_id(token_payload, db)
    
    # 1. DB에서 최근 7일간의 건강 데이터 원본 행들 가져오기
    health_rows = await get_recent_health_metrics(db, user_id, days=7)
    
    # 2. 헬스 데이터를 수치 변화율 알고리즘에 밀어넣기
    metrics_result = calculate_mood_metrics(health_rows, period_days=1)
    
    # 3. 비식별화 + RAG 전문 서적 매칭 + LLM 컴포지션을 거쳐 완성된 HTML 리포트 생성
    html_report = await generate_dashboard_rag_report(db, user_id, metrics_result)
    
    return {"report": html_report}