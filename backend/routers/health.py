from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert 
from backend.database import get_db
from backend.models import schemas, domain
from backend.routers.auth import get_current_user

# 🚀 1~4단계에서 만든 서비스 모듈 임포트
from backend.services.analytics_service import calculate_mood_metrics
from backend.services.rag_chain import generate_dashboard_rag_report

router = APIRouter(
    tags=["Health Data"]
)

# ---------------------------------------------------------
# 📱 1. 모바일 앱 -> DB 저장 (UPSERT) - 기존 유지
# ---------------------------------------------------------
@router.post("/api/mobile/health-data")
async def save_health_data(
    data: schemas.HealthDataCreate, 
    db: AsyncSession = Depends(get_db),
    current_user: domain.User = Depends(get_current_user)
):
    try:
        stmt = insert(domain.HealthMetric).values(
            user_id=current_user.id,
            record_date=data.record_date,
            step_count=data.step_count,
            sleep_minutes=data.sleep_minutes,
            screen_time_minutes=data.screen_time_minutes,
            app_usage_json=data.app_usage_json
        )

        do_update_stmt = stmt.on_conflict_do_update(
            index_elements=['user_id', 'record_date'], 
            set_=dict(
                step_count=stmt.excluded.step_count,
                sleep_minutes=stmt.excluded.sleep_minutes,
                screen_time_minutes=stmt.excluded.screen_time_minutes,
                app_usage_json=stmt.excluded.app_usage_json
            )
        )

        await db.execute(do_update_stmt)
        await db.commit()
        return {"status": "success", "message": "데이터 동기화 완료"}

    except Exception as e:
        await db.rollback()
        print(f"DATABASE ERROR: {str(e)}") 
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------
# 🌐 2. 웹 대시보드 데이터 제공 (차트 렌더링용) - 기존 유지
# ---------------------------------------------------------
@router.get("/api/web/data")
async def get_web_data(
    db: AsyncSession = Depends(get_db),
    current_user: domain.User = Depends(get_current_user)
):
    result = await db.execute(
        select(domain.HealthMetric)
        .where(domain.HealthMetric.user_id == current_user.id)
        .order_by(domain.HealthMetric.record_date.asc())
    )
    records = result.scalars().all()
    
    data_list = [
        {
            "recordDate": r.record_date.strftime("%Y-%m-%d") if hasattr(r.record_date, 'strftime') else r.record_date,
            "stepCount": r.step_count,
            "sleepMinutes": r.sleep_minutes,
            "screenTimeMinutes": r.screen_time_minutes,
            "appUsageJson": r.app_usage_json
        }
        for r in records
    ]
    return {"data": data_list}


# ---------------------------------------------------------
# 🤖 3. LLM 대시보드 리포트 (RAG 파이프라인 통합) - 🚀 최종 업데이트!
# ---------------------------------------------------------
@router.get("/api/web/analyze")
async def analyze_data(
    db: AsyncSession = Depends(get_db),
    current_user: domain.User = Depends(get_current_user)
):
    # 1. DB에서 최신 데이터 28일치(Baseline 계산용) 추출
    result = await db.execute(
        select(domain.HealthMetric)
        .where(domain.HealthMetric.user_id == current_user.id)
        .order_by(domain.HealthMetric.record_date.asc())
        .limit(28) 
    )
    records = result.scalars().all()

    if not records:
        return {"report": "💡 <b>분석 대기 중</b><br><br>Supabase DB에 수집된 데이터가 없습니다. 앱에서 동기화를 진행해주세요."}

    # 2. SQLAlchemy 객체를 분석 서비스용 Dictionary로 변환
    record_dicts = [
        {
            "step_count": r.step_count,
            "sleep_minutes": r.sleep_minutes,
            "screen_time_minutes": r.screen_time_minutes,
            "app_usage_json": r.app_usage_json
        }
        for r in records
    ]

    # 🚀 Step 1: 데이터 기반 감정 룰 분석 (Baseline vs Delta)
    metrics_result = calculate_mood_metrics(record_dicts)

    # 🚀 Step 2 ~ 4: RAG 파이프라인 실행 (비식별화 -> 지식 검색 -> LLM)
    llm_html_report = await generate_dashboard_rag_report(
        db=db, 
        user_id=current_user.id, 
        metrics_result=metrics_result
    )

    # 데이터가 3일 미만이라 분석이 안 돌아갔을 경우 LLM 응답이 아닌 자체 메시지 출력
    if metrics_result.get("status") == "insufficient_data":
        return {"report": llm_html_report}

    # 🚀 Step 5: 최종 HTML 조립
    # 바텐더의 LLM 리포트 상단에 오늘의 실제 기록을 예쁘게 얹어줍니다.
    today = metrics_result.get('today', {"steps": 0, "sleep_minutes": 0, "screen_time": 0})
    
    final_report = (
        f"🥃 <b>MoodTender 데이터 진단 및 처방</b><br><br>"
        f"<div style='font-size: 0.9em; color: #b3a48c; margin-bottom: 15px; padding-bottom: 15px; border-bottom: 1px solid rgba(200, 160, 90, 0.2);'>"
        f"<b>오늘의 활동량:</b> 👣 {today['steps']}보<br>"
        f"<b>오늘의 수면량:</b> 🛏️ {today['sleep_minutes']//60}시간 {today['sleep_minutes']%60}분<br>"
        f"<b>스마트폰 사용:</b> 📱 {today['screen_time']}분"
        f"</div>"
        f"<div style='line-height: 1.6;'>"
        f"{llm_html_report}"
        f"</div>"
    )

    return {"report": final_report}
