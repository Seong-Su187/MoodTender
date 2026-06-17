import statistics
import json
import os
from typing import List, Dict, Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

# ---------------------------------------------------------
# 🚀 [순환 참조 해결] rag_chain.py에서 가져오지 않고 독립적으로 LLM 생성 함수 정의
# ---------------------------------------------------------
def _make_llm(temperature: float = 0.7, model: str = "gpt-4.1-mini") -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        temperature=temperature,
        openai_api_key=os.getenv("OPENAI_API_KEY"),
    )

def calculate_mood_metrics(records: List[Dict[str, Any]], period_days: int = 1) -> Dict[str, Any]:
    if not records or len(records) < period_days + 2:
        return {
            "status": "insufficient_data",
            "analysis": {"emotion": "평온", "reason": "데이터가 충분하지 않아 일상적인 평온 상태로 가정합니다."}
        }

    period_records = records[-period_days:]
    past_records = records[:-period_days]

    steps_list = [r.get('step_count', 0) for r in past_records if r.get('step_count', 0) > 0]
    sleep_list = [r.get('sleep_minutes', 0) for r in past_records if r.get('sleep_minutes', 0) > 0]
    screen_list = [r.get('screen_time_minutes', 0) for r in past_records if r.get('screen_time_minutes', 0) > 0]

    b_steps = statistics.median(steps_list) if steps_list else 1
    b_sleep = statistics.median(sleep_list) if sleep_list else 1
    b_screen = statistics.median(screen_list) if screen_list else 1
    sleep_stdev = statistics.stdev(sleep_list) if len(sleep_list) > 1 else 0

    t_steps = round(statistics.mean([r.get('step_count', 0) for r in period_records]))
    t_sleep = round(statistics.mean([r.get('sleep_minutes', 0) for r in period_records]))
    t_screen = round(statistics.mean([r.get('screen_time_minutes', 0) for r in period_records]))

    app_keys = set()
    for r in period_records:
        app_keys.update((r.get('app_usage_json') or {}).keys())

    app_usage = {
        k: round(sum((r.get('app_usage_json') or {}).get(k, 0) for r in period_records) / len(period_records))
        for k in app_keys
    }
    social_time = sum(v for k, v in app_usage.items() if k.lower() in ['kakao', 'kakaotalk', 'instagram', 'message'])
    media_time = sum(v for k, v in app_usage.items() if 'youtube' in k.lower() or 'netflix' in k.lower())

    d_steps = (t_steps - b_steps) / b_steps
    d_sleep = (t_sleep - b_sleep) / b_sleep
    d_screen = (t_screen - b_screen) / b_screen

    emotion = "평온"
    reason = "신체 활동과 수면, 스마트폰 사용이 평소 기준선 내에서 안정적인 패턴을 보입니다."

    if d_steps <= -0.40 and d_sleep <= -0.15:
        emotion = "지침"
        reason = f"평소보다 활동량이 {abs(d_steps*100):.0f}% 감소하고 수면도 부족합니다. 에너지가 크게 고갈된 번아웃 신호가 보입니다."
    elif d_steps <= -0.30 and (d_sleep >= 0.20 or d_sleep <= -0.20) and media_time > 120:
        emotion = "우울"
        reason = f"활동량이 {abs(d_steps*100):.0f}% 줄고 수면 패턴이 깨졌으며, 영상 시청 시간이 높습니다. 무기력과 우울감이 의심됩니다."
    elif sleep_stdev > 60 and d_screen >= 0.30:
        emotion = "불안"
        reason = f"최근 수면이 불규칙한 가운데, 스마트폰 사용량이 평소보다 {d_screen*100:.0f}% 급증했습니다. 불안이나 초조함으로 인한 과각성 상태가 보입니다."
    elif d_screen >= 0.10 and social_time < 15:
        emotion = "외로움"
        reason = "스마트폰 사용 시간은 길지만 누군가와의 연락 비중이 매우 낮습니다. 고립감이나 외로움을 느낄 수 있는 패턴입니다."
    elif d_sleep <= -0.30 and d_screen >= 0.40:
        emotion = "분노"
        reason = "수면을 크게 줄이면서까지 스마트폰에 몰입하고 있습니다. 스트레스나 불만을 해소하려는 '보복성 철야' 패턴이 의심됩니다."
    elif d_steps >= 0.15 and d_sleep > -0.10 and social_time > 30:
        emotion = "기쁨"
        reason = "충분한 수면과 함께 외부 활동량이 평소보다 늘었고, 타인과의 연락도 활발합니다. 긍정적이고 활기찬 상태로 보입니다."

    return {
        "status": "success",
        "baseline": {"steps": b_steps, "sleep_minutes": b_sleep, "screen_time": b_screen},
        "today": {"steps": t_steps, "sleep_minutes": t_sleep, "screen_time": t_screen},
        "deltas": {"steps": round(d_steps, 2), "sleep": round(d_sleep, 2), "screen": round(d_screen, 2)},
        "analysis": {"emotion": emotion, "reason": reason}
    }


# ---------------------------------------------------------
# 🚀 [LLM Chains] 프롬프트 및 파이프라인 세팅
# ---------------------------------------------------------

extract_prompt = ChatPromptTemplate.from_messages([
    ("system", """
    당신은 심리 분석가입니다. 대화 내역을 읽고, 
    오늘 사용자가 겪은 핵심적인 '사건(issue)'과 그로 인한 '감정(emotion)'을 추출하세요.
    반드시 JSON 형식으로만 대답하세요: {{"issue": "사건 요약", "emotion": "감정 요약"}}
    특별한 사건이 없다면 {{"issue": "없음", "emotion": "평온함"}} 으로 작성하세요.
    설명이나 마크다운 없이 순수 JSON만 출력하세요.
    """),
    ("human", "{chat_history}")
])
extract_chain = extract_prompt | _make_llm(temperature=0.0, model="gpt-4.1-mini") | StrOutputParser()


prescription_prompt = ChatPromptTemplate.from_messages([
    ("system", """
    당신은 마음을 치유하는 바텐더입니다. 손님이 최근 '{issue}' 사건으로 인해 '{emotion}' 감정을 느끼고 있습니다.
    1. 손님의 마음을 깊이 공감하고 위로하는 1~2줄의 문장(emotion_analysis)을 작성하세요.
    2. 이 상황을 가볍게 타개할 수 있는 현실적이고 쉬운 행동 지침 3가지(checklist)를 배열 형태로 작성하세요.
    
    반드시 아래 JSON 형식으로만 대답하세요. 다른 말은 절대 하지 마세요:
    {{"emotion_analysis": "위로의 문장", "checklist": ["행동1", "행동2", "행동3"]}}
    """)
])
prescription_chain = prescription_prompt | _make_llm(temperature=0.7, model="gpt-4.1-mini") | StrOutputParser()


result_prompt = ChatPromptTemplate.from_messages([
    ("system", """
    당신은 마음을 치유하는 바텐더입니다. 손님이 기분 전환을 위해 다음 행동들을 하기로 약속했습니다: [{actions_str}]
    1. 이 행동들을 했을 때의 긍정적인 기대 효과(expected_effect)를 1줄로 적어주세요.
    2. 이 행동과 감정에 어울리는 창의적이고 감성적인 칵테일 이름(cocktail_name)을 하나 지어주세요.
    3. 칵테일과 함께 건넬 응원의 메시지(message)를 1줄로 적어주세요.
    
    반드시 아래 JSON 형식으로만 대답하세요. 다른 말은 절대 하지 마세요:
    {{"expected_effect": "기대 효과", "cocktail_name": "칵테일 이름", "message": "응원 메시지"}}
    """)
])
result_chain = result_prompt | _make_llm(temperature=0.7, model="gpt-4.1-mini") | StrOutputParser()


# 🚀 [버그 해결] LLM이 사용자의 입력을 읽도록 수정하고, 피드백 판단 기준을 극도로 깐깐하게 강화했습니다.
feedback_prompt = ChatPromptTemplate.from_messages([
    ("system", """
    당신은 대화 맥락을 분석하는 AI입니다. 
    바텐더가 이전에 '{cocktail_name}'(관련 고민: '{issue}')을 처방했습니다.
    이제 사용자가 한 발화가 이 처방에 대한 '직접적인 피드백(해결됨, 실천 여부, 후기)'인지 엄격하게 판단하세요.
    
    [엄격한 판단 기준]
    1. 사용자가 명시적으로 과거 고민('{issue}')이 나아졌다고 하거나, 처방받은 행동/칵테일('{cocktail_name}')을 언급하며 후기를 말할 때만 피드백으로 인정합니다.
    2. 일상적인 인사, 전혀 다른 새로운 고민, 혹은 "기대되는 일이 있어요" 같은 다른 주제라면 절대 피드백이 아닙니다.
    3. 피드백이 확실한 경우에만 is_feedback을 true로 설정하고, 긍정적일수록 높은 평점(1~5점)을 매기세요.
    4. 조금이라도 다른 이야기라면 무조건 false로 반환하세요. 혼자서 추측하여 지어내지 마세요.
    
    반드시 아래 JSON 형식으로만 대답하세요:
    피드백인 경우: {{"is_feedback": true, "taste_rating": 4, "user_review": "리뷰 요약"}}
    피드백이 아닌 경우: {{"is_feedback": false, "taste_rating": 0, "user_review": ""}}
    """),
    ("human", "사용자 발화: {user_input}")
])
feedback_chain = feedback_prompt | _make_llm(temperature=0.0, model="gpt-4.1-mini") | StrOutputParser()


# ---------------------------------------------------------
# 🚀 [실행 함수] 실제로 체인을 호출하고 JSON을 파싱하여 반환
# ---------------------------------------------------------

async def extract_memory_from_chat(chat_history: str) -> dict:
    try:
        raw_res = await extract_chain.ainvoke({"chat_history": chat_history})
        clean_json = raw_res.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(clean_json)
    except Exception as e:
        print(f"[LLM 분석 오류] 사건 추출 실패: {e}")
        return {"issue": "없음", "emotion": "평온함"}

async def generate_cocktail_prescription(issue: str, emotion: str) -> dict:
    try:
        raw_res = await prescription_chain.ainvoke({"issue": issue, "emotion": emotion})
        clean_json = raw_res.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(clean_json)
    except Exception as e:
        print(f"[LLM 분석 오류] 칵테일 처방 실패: {e}")
        return {
            "emotion_analysis": f"'{issue}' 때문에 많이 힘드셨겠어요. 깊은 {emotion}이 느껴집니다. 제가 도와드릴게요.",
            "checklist": ["따뜻한 차 한 잔 마시며 심호흡하기", "오늘 있었던 일 일기에 적어보기", "가벼운 산책으로 기분 전환하기"]
        }

async def generate_cocktail_result(selected_actions: list) -> dict:
    try:
        actions_str = ", ".join(selected_actions)
        raw_res = await result_chain.ainvoke({"actions_str": actions_str})
        clean_json = raw_res.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(clean_json)
    except Exception as e:
        print(f"[LLM 분석 오류] 칵테일 결과 실패: {e}")
        return {
            "expected_effect": "선택하신 행동들을 실천하시면 마음의 짐이 한결 가벼워지고 평온을 되찾을 거예요.",
            "cocktail_name": "미드나잇 릴렉서",
            "message": "손님을 위한 맞춤형 칵테일이 완성되었습니다. 오늘 하루도 고생 많으셨어요."
        }

async def analyze_cocktail_feedback(user_input: str, cocktail_name: str, issue: str) -> dict:
    try:
        raw_res = await feedback_chain.ainvoke({"user_input": user_input, "cocktail_name": cocktail_name, "issue": issue})
        clean_json = raw_res.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(clean_json)
    except Exception as e:
        print(f"[LLM 분석 오류] 피드백 감지 실패: {e}")
        return {"is_feedback": False, "taste_rating": 0, "user_review": ""}