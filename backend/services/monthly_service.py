"""
monthly_service.py
월간 감정 흐름 분석 서비스 — 주차별 집계 + 바텐더 월간 편지 생성
"""

import os
import json
from collections import Counter

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from backend.services.db_client import get_expert_knowledge

load_dotenv()


def _make_llm(temperature: float = 0.7, model: str = "gpt-4.1") -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        temperature=temperature,
        openai_api_key=os.getenv("OPENAI_API_KEY"),
    )


def aggregate_weekly_emotions(receipts: list) -> list:
    """
    emotion_receipts 레코드를 1~4주차(7일 단위)로 묶어
    주차별 지배 감정과 감정별 일수를 반환합니다.
    """
    weeks: dict[int, dict[str, int]] = {1: {}, 2: {}, 3: {}, 4: {}}
    for r in receipts:
        day = r.receipt_date.day
        week = min((day - 1) // 7 + 1, 4)
        emotion = r.dominant_sub_category or "평온"
        weeks[week][emotion] = weeks[week].get(emotion, 0) + 1

    result = []
    for w in [1, 2, 3, 4]:
        emotions = weeks[w]
        if not emotions:
            continue
        dominant = max(emotions, key=emotions.get)
        result.append({
            "label": f"{w}주차",
            "dominant_emotion": dominant,
            "count": sum(emotions.values()),
            "emotions": emotions,
        })
    return result


_MAIN_EMOTIONS = {"기쁨", "우울", "불안", "분노", "지침", "외로움", "평온"}


async def _get_main_emotion(db: AsyncSession, sub_category: str) -> str:
    """
    emotion_dictionary에서 sub_category → main_category를 조회합니다.
    정확 매핑 실패 시 '·' 구분자로 분할해 키워드별 재시도합니다.
    """
    if sub_category in _MAIN_EMOTIONS:
        return sub_category
    result = await db.execute(
        text("SELECT main_category FROM emotion_dictionary WHERE sub_category = :sub LIMIT 1"),
        {"sub": sub_category},
    )
    row = result.fetchone()
    if row:
        return row[0]
    for part in sub_category.split("·"):
        part = part.strip()
        if len(part) < 2:
            continue
        result = await db.execute(
            text("SELECT main_category FROM emotion_dictionary WHERE sub_category = :part LIMIT 1"),
            {"part": part},
        )
        row = result.fetchone()
        if row:
            return row[0]
    return "평온"


monthly_report_chain = ChatPromptTemplate.from_messages([
    ("system", """
당신은 10년 차 전문 바텐더 'MoodTender'입니다.
손님의 {year}년 {month}월 감정 흐름과 생활 데이터를 바탕으로,
웹 대시보드에 표시할 '월간 감정 흐름 분석 리포트'를 작성해 주세요.

[이번 달 주차별 감정 & 생활 흐름]
{flow_text}

[심리학·행동요법 전문 지식]
{expert_knowledge}

[참고 배경 지식 — 직접 인용하지 말고 문맥에 자연스럽게 녹여 사용하세요]
- 수면의 질이 떨어지면 뇌의 감정 반응 중추가 예민해져 부정적인 감정이 더 크게 느껴집니다.
- 규칙적인 걷기나 신체활동은 우울·불안 증상을 완화하는 데 매우 효과적이며, 수면의 질도 함께 개선됩니다.
- 야간 스마트폰 사용이 늘어날수록 수면과 기분 모두 악화될 수 있습니다.

[작성 규칙]
1. 정확히 3개의 <p> 단락으로 작성합니다.
   - 각 단락은 반드시 <p>...</p>로 감쌉니다
   - 단락 내 문장이 2개 이상이면 문장 사이에 <br>을 넣어 줄바꿈합니다
   - <br><br>은 절대 사용하지 않습니다
2. [1단락] 이달 주차별 감정 흐름 요약.
   생활 데이터(수면·걸음수·스크린타임)가 있다면 감정 변화의 맥락으로 자연스럽게 연결하세요.
   수치는 직접 언급하지 말고 감각적으로 표현하세요. (예: "몸이 무겁던 초반", "발걸음이 가벼워지던 주")
3. [2단락] 이달 감정 패턴의 심리학적 해석.
   단정 짓지 말고 "~였을 수 있어요", "~로 보입니다", "~예상됩니다" 등의 어투를 사용하세요.
   [전문 지식]과 [배경 지식]을 참고해 패턴이 생긴 이유를 부드럽게 해석합니다.
4. [3단락] 다음을 위한 가벼운 실천 제안.
   [전문 지식]을 참고해 지금 당장 할 수 있는 구체적인 행동을 1~2가지 제안합니다. (예: 5분 환기, 짧은 산책)
   마지막 문장은 이달의 MoodTender 시그니처 칵테일 "{cocktail}"을 바텐더의 언어로 감성적으로 소개하며 권하세요.
   칵테일 이름은 반드시 원문 그대로 사용하고, 왜 이 칵테일인지 한 문장으로 자연스럽게 연결합니다.
5. 중요 키워드는 <b>볼드</b>로 강조합니다.
6. 전체 분량은 건강 & 분석 리포트와 비슷하게, 너무 짧지도 길지도 않게 작성합니다.
7. 10년 차 바텐더의 따뜻하고 통찰력 있는 어투로, "손님"라는 호칭을 씁니다.
""")
]) | _make_llm(temperature=0.5) | StrOutputParser()


async def generate_monthly_emotion_report(
    db: AsyncSession,
    user_id: int,
    weeks: list,
    year: int,
    month: int,
    cocktail: str | None = None,
) -> str:
    """
    주차별 감정 흐름 데이터를 받아 바텐더 스타일의 월간 편지를 생성합니다.
    """
    if not weeks:
        return (
            "이번 달 감정 기록이 아직 충분하지 않아요. "
            "대화를 더 나누다 보면 손님의 이야기를 더 잘 담아드릴 수 있을 거예요."
        )

    all_emotions = []
    for w in weeks:
        for emotion, count in w["emotions"].items():
            all_emotions.extend([emotion] * count)

    top_sub = Counter(all_emotions).most_common(1)[0][0] if all_emotions else "평온"
    main_emotion = await _get_main_emotion(db, top_sub)

    expert_knowledge = await get_expert_knowledge(db, main_emotion)

    flow_lines = []
    for w in weeks:
        health = w.get("health") or {}
        parts = [f"- {w['label']}: {w['main_emotion']} ({w['count']}일)"]
        hints = []
        if health.get("sleep"):
            h = health["sleep"]
            hints.append(f"수면 평균 {h // 60}시간 {h % 60}분" if h >= 60 else f"수면 평균 {h}분")
        if health.get("steps"):
            hints.append(f"걸음 평균 {health['steps']:,}보")
        if health.get("screen"):
            hints.append(f"스크린타임 평균 {health['screen']}분")
        if hints:
            parts.append("  [생활] " + ", ".join(hints))
        flow_lines.append("\n".join(parts))
    flow_text = "\n".join(flow_lines)

    report = await monthly_report_chain.ainvoke({
        "year": year,
        "month": month,
        "flow_text": flow_text,
        "expert_knowledge": expert_knowledge or "관련 전문 지식 없음",
        "cocktail": cocktail or "시그니처 칵테일",
    })

    return report.strip()


language_chain = ChatPromptTemplate.from_messages([
    ("system", """당신은 심리언어학 전문가입니다.
사용자가 한 달간 AI 바텐더와 나눈 대화를 주차별로 읽고,
말투와 감정 표현이 어떻게 변화했는지 분석해주세요.

주차별 변화를 각각 별도 단락으로 나눠서 작성하세요.
예: "초반에는 '그냥 다 싫어', '모르겠어' 같은 표현이 많았지만, 후반엔 '해볼게요', '조금 나아진 것 같아요'로 바뀌었어요."

변화가 없거나 데이터가 부족하면 "이달은 일관된 감정 상태를 유지하셨어요"라고 말하세요.
각 단락은 반드시 <p>...</p>로 감싸고, 단락 사이는 한 줄 띄워주세요. 전체 2~3문단.
"""),
    ("human", "{weekly_notes_text}")
]) | _make_llm(0.5) | StrOutputParser()


async def generate_language_change_analysis(weekly_notes: dict) -> str:
    has_data = any(msgs for msgs in weekly_notes.values())
    if not has_data:
        return ""

    lines = []
    for week in [1, 2, 3, 4]:
        msgs = weekly_notes.get(week, [])
        if msgs:
            lines.append(f"{week}주차: " + " / ".join(msgs[:15]))

    if not lines:
        return ""

    try:
        result = await language_chain.ainvoke({"weekly_notes_text": "\n".join(lines)})
        return str(result).strip()
    except Exception as e:
        print(f"Language analysis error: {e}")
        return ""
