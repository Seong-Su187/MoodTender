import statistics
from typing import List, Dict, Any

def calculate_mood_metrics(records: List[Dict[str, Any]], period_days: int = 1) -> Dict[str, Any]:
    """
    사용자의 최근 라이프 로그 데이터를 바탕으로 기준선(Baseline)과 변화율(Delta)을 계산하여,
    7가지 감정 계열(기쁨, 우울, 불안, 분노, 지침, 외로움, 평온) 중 하나를 추론합니다.

    period_days: 분석 대상 기간(가장 최근 N일)입니다. 1이면 마지막 날(오늘) 하루를,
    2~7이면 해당 기간 전체의 일별 평균을 '오늘'처럼 취급하여 baseline과 비교합니다.
    """
    if not records or len(records) < period_days + 2:
        return {
            "status": "insufficient_data",
            "analysis": {"emotion": "평온", "reason": "데이터가 충분하지 않아 일상적인 평온 상태로 가정합니다."}
        }

    # 1. 데이터 분리 (분석 대상 기간 vs 과거 baseline 데이터)
    period_records = records[-period_days:]
    past_records = records[:-period_days]

    # 2. 과거 데이터(Baseline) 목록 추출 (결측치 제외)
    steps_list = [r.get('step_count', 0) for r in past_records if r.get('step_count', 0) > 0]
    sleep_list = [r.get('sleep_minutes', 0) for r in past_records if r.get('sleep_minutes', 0) > 0]
    screen_list = [r.get('screen_time_minutes', 0) for r in past_records if r.get('screen_time_minutes', 0) > 0]

    # 3. 중앙값(Median) 기준선 및 수면 변동성(표준편차) 계산
    b_steps = statistics.median(steps_list) if steps_list else 1
    b_sleep = statistics.median(sleep_list) if sleep_list else 1
    b_screen = statistics.median(screen_list) if screen_list else 1
    sleep_stdev = statistics.stdev(sleep_list) if len(sleep_list) > 1 else 0

    # 4. 분석 대상 기간 데이터 (period_days일 평균 -> '오늘'처럼 취급)
    t_steps = round(statistics.mean([r.get('step_count', 0) for r in period_records]))
    t_sleep = round(statistics.mean([r.get('sleep_minutes', 0) for r in period_records]))
    t_screen = round(statistics.mean([r.get('screen_time_minutes', 0) for r in period_records]))

    # 앱 사용량 분석 (기간 내 일별 평균 -> 소셜 vs 미디어 소비)
    app_keys = set()
    for r in period_records:
        app_keys.update((r.get('app_usage_json') or {}).keys())

    app_usage = {
        k: round(sum((r.get('app_usage_json') or {}).get(k, 0) for r in period_records) / len(period_records))
        for k in app_keys
    }
    social_time = sum(v for k, v in app_usage.items() if k.lower() in ['kakao', 'kakaotalk', 'instagram', 'message'])
    media_time = sum(v for k, v in app_usage.items() if 'youtube' in k.lower() or 'netflix' in k.lower())

    # 5. 변화율(Delta) 계산
    d_steps = (t_steps - b_steps) / b_steps
    d_sleep = (t_sleep - b_sleep) / b_sleep
    d_screen = (t_screen - b_screen) / b_screen

    # ---------------------------------------------------------
    # 🧠 6. 7대 감정 추론 알고리즘 (Heuristic Mapping)
    # ---------------------------------------------------------
    emotion = "평온"
    reason = "신체 활동과 수면, 스마트폰 사용이 평소 기준선(Baseline) 내에서 안정적인 패턴을 보입니다."

    # 1. 지침(번아웃) 계열: 절대적 신체 활동 하락 + 수면 감소
    if d_steps <= -0.40 and d_sleep <= -0.15:
        emotion = "지침"
        reason = f"평소보다 활동량이 {abs(d_steps*100):.0f}% 감소하고 수면도 부족합니다. 에너지가 크게 고갈된 번아웃 신호가 보입니다."

    # 2. 우울 계열: 무기력증(활동 하락) + 수면 과다/불규칙 + 미디어(유튜브) 도피
    elif d_steps <= -0.30 and (d_sleep >= 0.20 or d_sleep <= -0.20) and media_time > 120:
        emotion = "우울"
        reason = f"활동량이 {abs(d_steps*100):.0f}% 줄고 수면 패턴이 깨졌으며, 영상 시청 시간이 높습니다. 무기력과 우울감이 의심됩니다."

    # 3. 불안 계열: 수면 변동성 심함 + 폰 사용 시간 급증 (과각성)
    elif sleep_stdev > 60 and d_screen >= 0.30:
        emotion = "불안"
        reason = f"최근 수면이 불규칙한 가운데, 스마트폰 사용량이 평소보다 {d_screen*100:.0f}% 급증했습니다. 불안이나 초조함으로 인한 과각성 상태가 보입니다."

    # 4. 외로움 계열: 폰 사용은 많으나 소셜(카카오톡 등) 사용은 극히 적음
    elif d_screen >= 0.10 and social_time < 15:
        emotion = "외로움"
        reason = "스마트폰 사용 시간은 길지만 누군가와의 연락(소셜 앱) 비중이 매우 낮습니다. 고립감이나 외로움을 느낄 수 있는 패턴입니다."

    # 5. 분노(스트레스) 계열: 수면 급감 + 과도한 스크린타임 (보복성 철야 증후군)
    elif d_sleep <= -0.30 and d_screen >= 0.40:
        emotion = "분노"
        reason = "수면을 크게 줄이면서까지 스마트폰에 몰입하고 있습니다. 스트레스나 불만을 해소하려는 '보복성 철야' 패턴이 의심됩니다."

    # 6. 기쁨(활력) 계열: 규칙적인 수면 + 활동량 증가 + 소셜 활동 증가
    elif d_steps >= 0.15 and d_sleep > -0.10 and social_time > 30:
        emotion = "기쁨"
        reason = "충분한 수면과 함께 외부 활동량이 평소보다 늘었고, 타인과의 연락도 활발합니다. 긍정적이고 활기찬 상태로 보입니다."

    # 결과 반환 포맷
    return {
        "status": "success",
        "baseline": {"steps": b_steps, "sleep_minutes": b_sleep, "screen_time": b_screen},
        "today": {"steps": t_steps, "sleep_minutes": t_sleep, "screen_time": t_screen},
        "deltas": {"steps": round(d_steps, 2), "sleep": round(d_sleep, 2), "screen": round(d_screen, 2)},
        "analysis": {"emotion": emotion, "reason": reason}
    }