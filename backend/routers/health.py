from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from backend.database import get_db
from backend.models import schemas, domain
from backend.routers.auth import get_current_user
from typing import Optional
from datetime import datetime, timezone, timedelta

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
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: domain.User = Depends(get_current_user)
):
    # 1. 날짜 파싱 (기본값: 오늘 하루)
    now_kst_date = datetime.now(timezone(timedelta(hours=9))).date()
    end_date_obj = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else now_kst_date
    start_date_obj = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else end_date_obj

    # 분석 기간은 최대 7일로 제한 (방어적 처리)
    if (end_date_obj - start_date_obj).days > 6:
        start_date_obj = end_date_obj - timedelta(days=6)

    # 2. 선택한 기간(start_date~end_date)의 기록 조회 -> '오늘'처럼 취급할 데이터
    period_query = (
        select(domain.HealthMetric)
        .where(domain.HealthMetric.user_id == current_user.id)
        .where(domain.HealthMetric.record_date >= start_date_obj)
        .where(domain.HealthMetric.record_date <= end_date_obj)
        .order_by(domain.HealthMetric.record_date.asc())
    )
    period_records = (await db.execute(period_query)).scalars().all()

    if not period_records:
        return {"report": "💡 <b>분석 대기 중</b><br><br>선택한 기간에 수집된 데이터가 없습니다. 앱에서 동기화를 진행해주세요."}

    # 3. 선택 기간 이전 데이터 최대 28일 (Baseline 계산용)
    baseline_query = (
        select(domain.HealthMetric)
        .where(domain.HealthMetric.user_id == current_user.id)
        .where(domain.HealthMetric.record_date < start_date_obj)
        .order_by(domain.HealthMetric.record_date.desc())
        .limit(28)
    )
    baseline_records = list(reversed((await db.execute(baseline_query)).scalars().all()))

    records = baseline_records + list(period_records)

    # 4. SQLAlchemy 객체를 분석 서비스용 Dictionary로 변환
    record_dicts = [
        {
            "step_count": r.step_count,
            "sleep_minutes": r.sleep_minutes,
            "screen_time_minutes": r.screen_time_minutes,
            "app_usage_json": r.app_usage_json
        }
        for r in records
    ]

    # 🚀 Step 1: 데이터 기반 감정 룰 분석 (Baseline vs Delta) - 선택 기간을 '오늘'처럼 취급
    metrics_result = calculate_mood_metrics(record_dicts, period_days=len(period_records))

    # 🚀 Step 2 ~ 4: RAG 파이프라인 실행 (비식별화 -> 지식 검색 -> LLM)
    report_data = await generate_dashboard_rag_report(
        db=db,
        user_id=current_user.id,
        metrics_result=metrics_result
    )
    llm_html_report = report_data["html"]

    # 데이터가 부족해서 분석이 안 돌아갔을 경우 LLM 응답이 아닌 자체 메시지 출력
    if metrics_result.get("status") == "insufficient_data":
        return {"report": llm_html_report}

    # 🚀 Step 5: 최종 HTML 조립
    # 바텐더의 LLM 리포트 상단에 분석 기준 데이터를 예쁘게 얹어줍니다.
    today = metrics_result.get('today', {"steps": 0, "sleep_minutes": 0, "screen_time": 0})

    if start_date_obj == end_date_obj:
        # 하루만 선택한 경우: 그날(또는 "오늘") 기준
        date_label = "오늘" if end_date_obj == now_kst_date else f"{end_date_obj.month}/{end_date_obj.day}"
        label_steps = f"{date_label}의 활동량"
        label_sleep = f"{date_label}의 수면량"
        label_screen = f"{date_label} 스마트폰 사용"
    else:
        # 여러 날을 선택한 경우: 기간 평균 기준
        period_label = f"{start_date_obj.month}/{start_date_obj.day}~{end_date_obj.month}/{end_date_obj.day}"
        label_steps = f"{period_label} 평균 활동량"
        label_sleep = f"{period_label} 평균 수면량"
        label_screen = f"{period_label} 평균 스마트폰 사용"

    final_report = (
        f"🥃 <b>MoodTender 데이터 진단 및 추천</b><br><br>"
        f"<div style='font-size: 0.9em; color: #b3a48c; margin-bottom: 15px; padding-bottom: 15px; border-bottom: 1px solid rgba(200, 160, 90, 0.2);'>"
        f"<b>{label_steps}:</b> 👣 {today['steps']}보<br>"
        f"<b>{label_sleep}:</b> 🛏️ {today['sleep_minutes']//60}시간 {today['sleep_minutes']%60}분<br>"
        f"<b>{label_screen}:</b> 📱 {today['screen_time']}분"
        f"</div>"
        f"<div style='line-height: 1.6;'>"
        f"{llm_html_report}"
        f"</div>"
    )

    return {"report": final_report}
