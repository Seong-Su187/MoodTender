"""
monthly.py
월간 감정 흐름 분석 라우터 — GET /api/web/monthly-analysis
"""

from collections import Counter
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, extract, text as sql_text

from backend.database import get_db
from backend.models import domain
from backend.routers.auth import get_current_user
from backend.services.monthly_service import (
    aggregate_weekly_emotions,
    generate_monthly_emotion_report,
)

router = APIRouter(tags=["Monthly Analysis"])

_MAIN_EMOTIONS = {"기쁨", "우울", "불안", "분노", "지침", "외로움", "평온"}


async def _resolve_sub_to_main(db: AsyncSession, sub: str) -> str:
    """정확 매핑 없으면 '·' 분할 키워드로 재시도."""
    if sub in _MAIN_EMOTIONS:
        return sub
    row = (await db.execute(
        sql_text("SELECT main_category FROM emotion_dictionary WHERE sub_category = :sub LIMIT 1"),
        {"sub": sub},
    )).fetchone()
    if row:
        return row[0]
    for part in sub.split("·"):
        part = part.strip()
        if len(part) < 2:
            continue
        row = (await db.execute(
            sql_text("SELECT main_category FROM emotion_dictionary WHERE sub_category = :part LIMIT 1"),
            {"part": part},
        )).fetchone()
        if row:
            return row[0]
    return "평온"


@router.get("/api/web/monthly-analysis")
async def get_monthly_analysis(
    year: int = None,
    month: int = None,
    db: AsyncSession = Depends(get_db),
    current_user: domain.User = Depends(get_current_user),
):
    # 기본값: 현재 연월 (KST)
    now_kst = datetime.now(timezone(timedelta(hours=9)))
    if year is None:
        year = now_kst.year
    if month is None:
        month = now_kst.month

    # 1. 해당 월의 emotion_receipts 조회
    receipts = (await db.execute(
        select(domain.EmotionReceipt)
        .where(domain.EmotionReceipt.user_id == current_user.id)
        .where(extract("year", domain.EmotionReceipt.receipt_date) == year)
        .where(extract("month", domain.EmotionReceipt.receipt_date) == month)
        .order_by(domain.EmotionReceipt.receipt_date.asc())
    )).scalars().all()

    # 2. 해당 월의 health_metrics 조회
    health_rows = (await db.execute(
        select(domain.HealthMetric)
        .where(domain.HealthMetric.user_id == current_user.id)
        .where(extract("year", domain.HealthMetric.record_date) == year)
        .where(extract("month", domain.HealthMetric.record_date) == month)
        .order_by(domain.HealthMetric.record_date.asc())
    )).scalars().all()

    # 3. 주차별 건강 데이터 평균 계산 (1~4주차)
    weekly_health: dict[int, dict] = {w: {"steps": [], "sleep": [], "screen": []} for w in range(1, 5)}
    for r in health_rows:
        week = min((r.record_date.day - 1) // 7 + 1, 4)
        if r.step_count:
            weekly_health[week]["steps"].append(r.step_count)
        if r.sleep_minutes:
            weekly_health[week]["sleep"].append(r.sleep_minutes)
        if r.screen_time_minutes:
            weekly_health[week]["screen"].append(r.screen_time_minutes)

    def avg(lst): return round(sum(lst) / len(lst)) if lst else None

    weekly_health_avg = {
        w: {
            "steps":  avg(weekly_health[w]["steps"]),
            "sleep":  avg(weekly_health[w]["sleep"]),
            "screen": avg(weekly_health[w]["screen"]),
        }
        for w in range(1, 5)
    }

    # 4. 주차별 감정 집계
    weeks = aggregate_weekly_emotions(receipts)

    # 5. sub_category → main_category 매핑 (모든 sub 대상)
    all_subs = {sub for w in weeks for sub in w["emotions"].keys()}
    sub_to_main: dict[str, str] = {}
    for sub in all_subs:
        sub_to_main[sub] = await _resolve_sub_to_main(db, sub)

    for w in weeks:
        w["main_emotion"] = sub_to_main.get(w["dominant_emotion"], "평온")
        # 같은 main_emotion으로 묶인 sub_category 총합
        main_em = w["main_emotion"]
        w["main_emotion_count"] = sum(
            cnt for sub, cnt in w["emotions"].items()
            if sub_to_main.get(sub, "평온") == main_em
        )
        week_num = int(w["label"].replace("주차", ""))
        w["health"] = weekly_health_avg.get(week_num, {})

    # 6. 이번 달 가장 많이 추천된 칵테일 집계
    cocktail_counts = Counter(
        r.recommended_cocktail for r in receipts if r.recommended_cocktail
    )
    top_cocktail = cocktail_counts.most_common(1)[0][0] if cocktail_counts else None

    # 7. 바텐더 월간 편지 생성 (LLM)
    report = await generate_monthly_emotion_report(
        db=db,
        user_id=current_user.id,
        weeks=weeks,
        year=year,
        month=month,
        cocktail=top_cocktail,
    )

    return {
        "year": year,
        "month": month,
        "weeks": weeks,
        "report": report,
    }


@router.get("/api/web/yearly-analysis")
async def get_yearly_analysis(
    year: int = None,
    db: AsyncSession = Depends(get_db),
    current_user: domain.User = Depends(get_current_user),
):
    now_kst = datetime.now(timezone(timedelta(hours=9)))
    if year is None:
        year = now_kst.year

    receipts = (await db.execute(
        select(domain.EmotionReceipt)
        .where(domain.EmotionReceipt.user_id == current_user.id)
        .where(extract("year", domain.EmotionReceipt.receipt_date) == year)
        .order_by(domain.EmotionReceipt.receipt_date.asc())
    )).scalars().all()

    # 월별 감정 집계
    month_map: dict[int, dict[str, int]] = {m: {} for m in range(1, 13)}
    for r in receipts:
        m = r.receipt_date.month
        emotion = r.dominant_sub_category or "평온"
        month_map[m][emotion] = month_map[m].get(emotion, 0) + 1

    # sub_category → main_category 매핑
    unique_subs = {e for emotions in month_map.values() for e in emotions}
    sub_to_main: dict[str, str] = {}
    for sub in unique_subs:
        sub_to_main[sub] = await _resolve_sub_to_main(db, sub)

    months = []
    for m in range(1, 13):
        emotions = month_map[m]
        if emotions:
            top_sub = max(emotions, key=emotions.get)
            months.append({
                "month": m,
                "label": f"{m}월",
                "main_emotion": sub_to_main.get(top_sub, "평온"),
                "count": sum(emotions.values()),
            })
        else:
            months.append({"month": m, "label": f"{m}월", "main_emotion": None, "count": 0})

    return {"year": year, "months": months}
