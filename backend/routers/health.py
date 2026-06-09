from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert # 🌟 UPSERT를 위한 핵심 라이브러리
from backend.database import get_db
from backend.models import schemas, domain

router = APIRouter(
    tags=["Health Data"]
)

# ---------------------------------------------------------
# 📱 1. 모바일 앱 -> DB 저장 (15분마다 갱신되는 UPSERT 로직)
# ---------------------------------------------------------
@router.post("/api/mobile/health-data")
async def save_health_data(
    data: schemas.HealthDataCreate, 
    db: AsyncSession = Depends(get_db)
):
    # 🚨 임시: JWT 연동 전까지는 테스트를 위해 user_id를 1로 고정
    current_user_id = 1 

    # 1. PostgreSQL 전용 UPSERT 쿼리 생성 (일단 Insert 시도)
    stmt = insert(domain.HealthMetric).values(
        user_id=current_user_id,
        record_date=data.record_date, # 스키마 필드명에 맞춤
        step_count=data.step_count,
        sleep_minutes=data.sleep_minutes,
        screen_time_minutes=data.screen_time_minutes,
        app_usage_json=data.app_usage_json,
        depression_score=data.depression_score
    )

    # 2. 충돌 시 업데이트 로직 (uq_health_user_date 제약조건에 걸리면 Update 실행)
    do_update_stmt = stmt.on_conflict_do_update(
        constraint='uq_health_user_date',
        set_=dict(
            step_count=stmt.excluded.step_count,
            sleep_minutes=stmt.excluded.sleep_minutes,
            screen_time_minutes=stmt.excluded.screen_time_minutes,
            app_usage_json=stmt.excluded.app_usage_json,
            depression_score=stmt.excluded.depression_score
        )
    )

    try:
        # 비동기로 쿼리 실행 및 커밋
        await db.execute(do_update_stmt)
        await db.commit()
        return {"status": "success", "message": "모바일 건강 데이터가 성공적으로 동기화(UPSERT) 되었습니다."}
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"데이터베이스 저장 중 에러 발생: {str(e)}")


# ---------------------------------------------------------
# 🌐 2. 웹 대시보드 데이터 제공 (프론트엔드 연동)
# ---------------------------------------------------------
@router.get("/api/web/data")
async def get_web_data(db: AsyncSession = Depends(get_db)):
    current_user_id = 1
    
    # 해당 유저의 데이터를 날짜순으로 가져오기
    result = await db.execute(
        select(domain.HealthMetric)
        .where(domain.HealthMetric.user_id == current_user_id)
        .order_by(domain.HealthMetric.record_date.asc())
    )
    records = result.scalars().all()
    
    # 프론트엔드 Javascript가 읽기 편하도록 카멜케이스(CamelCase)로 변환해서 응답
    data_list = [
        {
            # date 객체를 문자열로 변환
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


# ---------------------------------------------------------
# 🤖 3. LLM 분석용 리포트 제공
# ---------------------------------------------------------
@router.get("/api/web/analyze")
async def analyze_data(db: AsyncSession = Depends(get_db)):
    current_user_id = 1
    
    result = await db.execute(
        select(domain.HealthMetric)
        .where(domain.HealthMetric.user_id == current_user_id)
        .order_by(domain.HealthMetric.record_date.asc())
    )
    records = result.scalars().all()
    
    if not records:
        return {"report": "Supabase DB에 아직 수집된 데이터가 없습니다."}
    
    latest = records[-1] # 제일 최신 데이터 (오늘)
    
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