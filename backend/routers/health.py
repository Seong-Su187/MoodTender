from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert 
from backend.database import get_db
from backend.models import schemas, domain
from backend.routers.auth import get_current_user # 🚀 의존성 임포트

router = APIRouter(
    tags=["Health Data"]
)

# ---------------------------------------------------------
# 📱 1. 모바일 앱 -> DB 저장 (UPSERT)
# ---------------------------------------------------------
@router.post("/api/mobile/health-data")
async def save_health_data(
    data: schemas.HealthDataCreate, 
    db: AsyncSession = Depends(get_db),
    current_user: domain.User = Depends(get_current_user) # 🚀 유저 자동 주입
):
    try:
        # PostgreSQL UPSERT 쿼리 (current_user.id 사용)
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
# 🌐 2. 웹 대시보드 데이터 제공
# ---------------------------------------------------------
@router.get("/api/web/data")
async def get_web_data(
    db: AsyncSession = Depends(get_db),
    current_user: domain.User = Depends(get_current_user) # 🚀 유저 자동 주입
):
    # current_user.id 사용 (고정 1 삭제)
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
# 🤖 3. LLM 분석용 리포트 제공
# ---------------------------------------------------------
@router.get("/api/web/analyze")
async def analyze_data(
    db: AsyncSession = Depends(get_db),
    current_user: domain.User = Depends(get_current_user) # 🚀 유저 자동 주입
):
    result = await db.execute(
        select(domain.HealthMetric)
        .where(domain.HealthMetric.user_id == current_user.id)
        .order_by(domain.HealthMetric.record_date.asc())
    )
    records = result.scalars().all()

    if not records:
        return {"report": "Supabase DB에 아직 수집된 데이터가 없습니다."}

    latest = records[-1]  # 제일 최신 데이터 (오늘)

    sleep_hrs = latest.sleep_minutes // 60
    usage_dict = latest.app_usage_json or {}
    youtube_min = usage_dict.get('youtube', 0)
    kakao_min = usage_dict.get('kakao', 0)

    report = (f"💡 <b>AI 상태 분석 리포트:</b><br><br>"
              f"오늘 수면 시간은 <b>{sleep_hrs}시간</b>이며, 걸음 수는 <b>{latest.step_count}보</b>입니다. "
              f"스마트폰을 총 <b>{latest.screen_time_minutes}분</b> 사용하셨네요.<br>"
              f"특히 유튜브 시청에 {youtube_min}분, 카카오톡에 {kakao_min}분을 소요했습니다. ")

    if sleep_hrs < 6 and youtube_min > 60:
        report += "<br><br>⚠️ <b>경고 신호:</b> 수면 시간이 부족한 상태에서 심야 영상 시청 빈도가 높습니다."
    else:
        report += "<br><br>✅ <b>안정 상태:</b> 건강한 일상 패턴을 유지하고 계십니다!"

    return {"report": report}