from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert 
from backend.database import get_db
from backend.models import schemas, domain

router = APIRouter(
    tags=["Health Data"]
)

# ---------------------------------------------------------
# 📱 1. 모바일 앱 -> DB 저장 (UPSERT)
# ---------------------------------------------------------
@router.post("/api/mobile/health-data")
async def save_health_data(
    data: schemas.HealthDataCreate, 
    db: AsyncSession = Depends(get_db)
):
    current_user_id = 1 # 테스트용 고정 ID

    try:
        # PostgreSQL UPSERT 쿼리
        stmt = insert(domain.HealthMetric).values(
            user_id=current_user_id,
            record_date=data.record_date,
            step_count=data.step_count,
            sleep_minutes=data.sleep_minutes,
            screen_time_minutes=data.screen_time_minutes,
            app_usage_json=data.app_usage_json,
            depression_score=data.depression_score
        )

        # 🚀 에러 방지: 제약조건 이름 대신 컬럼 조합을 사용하여 충돌 처리
        do_update_stmt = stmt.on_conflict_do_update(
            index_elements=['user_id', 'record_date'], 
            set_=dict(
                step_count=stmt.excluded.step_count,
                sleep_minutes=stmt.excluded.sleep_minutes,
                screen_time_minutes=stmt.excluded.screen_time_minutes,
                app_usage_json=stmt.excluded.app_usage_json,
                depression_score=stmt.excluded.depression_score
            )
        )

        await db.execute(do_update_stmt)
        await db.commit()
        return {"status": "success", "message": "데이터 동기화 완료"}

    except Exception as e:
        await db.rollback()
        # 에러 로그 출력
        print(f"DATABASE ERROR: {str(e)}") 
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------
# 🌐 2. 웹 대시보드 데이터 제공
# ---------------------------------------------------------
@router.get("/api/web/data")
async def get_web_data(db: AsyncSession = Depends(get_db)):
    current_user_id = 1
    
    result = await db.execute(
        select(domain.HealthMetric)
        .where(domain.HealthMetric.user_id == current_user_id)
        .order_by(domain.HealthMetric.record_date.asc())
    )
    records = result.scalars().all()
    
    data_list = [
        {
            "recordDate": r.record_date.strftime("%Y-%m-%d") if hasattr(r.record_date, 'strftime') else r.record_date,
            "stepCount": r.step_count,
            "sleepMinutes": r.sleep_minutes,
            "screenTimeMinutes": r.screen_time_minutes,
            "appUsageJson": r.app_usage_json,
            "depressionScore": r.depression_score
        }
        for r in records
    ]
    return {"data": data_list}