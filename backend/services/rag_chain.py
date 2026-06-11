import asyncio
import os
import re
import uuid

from dotenv import load_dotenv
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI

from backend.services.db_client import (
    retrieve_emotion_dictionary,
    retrieve_similar_user_memories,
    retrieve_similar_chat_messages,
    save_user_memory,
    save_emotion_receipt,
    save_chat_message,
)
from backend.services.openai_llm import generate_bartender_reply

load_dotenv()


def mask_sensitive_patterns(text: str) -> str:
    if not text:
        return ""

    masked = text
    masked = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[이메일]", masked)
    masked = re.sub(r"\b010[-.\s]?\d{4}[-.\s]?\d{4}\b", "[전화번호]", masked)
    masked = re.sub(r"\b0\d{1,2}[-.\s]?\d{3,4}[-.\s]?\d{4}\b", "[전화번호]", masked)
    masked = re.sub(r"\b\d{6}[-\s]?\d{7}\b", "[주민등록번호]", masked)
    masked = re.sub(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b", "[카드번호]", masked)
    masked = re.sub(r"https?://[^\s]+", "[URL]", masked)

    return masked


EMOTION_ROUTER_PROMPT = ChatPromptTemplate.from_template("""
너는 MoodTender의 감정 분석 라우터다.

사용자의 발화를 읽고 감정 계열, 감정의 결, 감정 강도, 핵심 키워드, 상황 요약을 분석한다.

[감정 분류 체계]
기쁨 계열: 경사·축하 / 통쾌·후련 / 뿌듯·성취 / 잔잔한 만족 / 설렘·두근 / 안도·해방 / 벅참·감동 / 신남·들뜸 / 자랑스러움 / 그리운 기쁨
우울 계열: 가라앉음·무기력 / 자책·후회 / 공허·허전 / 슬픔·눈물 / 침잠·혼자 / 무덤덤·먹먹 / 좌절·낙담 / 소진·지쳐 처짐 / 외로운 우울 / 무의미·허무
불안 계열: 초조·긴장 / 막막함 / 걱정·근심 / 안절부절 / 두려움·겁 / 압박·부담 / 불확실·혼란 / 예민·과민 / 조마조마·불길
분노 계열: 욱·폭발 / 억울·분함 / 짜증·신경질 / 배신감 / 분개·치밀어오름 / 답답·울화 / 서운·삐침 / 분노 후 허탈
지침(번아웃) 계열: 탈진·소진 / 권태·지루 / 압박감·짓눌림 / 무기력한 피로 / 의욕 상실 / 번아웃·다 놓고 싶음
외로움 계열: 고립·혼자 / 그리움 / 소외·서운 / 쓸쓸·허전 / 단절·이해받지 못함 / 사무치는 외로움 / 군중 속 고독 / 보고픔·사무친 정 / 외톨이·겉도는 / 의지할 곳 없음
평온 계열: 담담·무던 / 여유·느긋 / 안온·편안 / 정돈·차분 / 만족스러운 고요 / 비움·홀가분 / 나른·노곤 / 충만·잔잔한 행복 / 사색·고즈넉 / 해방·자유 / 안도의 평온

[사용자 발화]
{user_text}

반드시 아래 JSON 형식으로만 출력한다.
JSON 앞뒤에 설명, 마크다운, 코드블록을 붙이지 않는다.

{{
  "emotion_family": "기쁨|우울|불안|분노|지침(번아웃)|외로움|평온 중 하나",
  "emotion_texture": "위 분류 체계 안의 세부 감정 결 중 하나",
  "emotion_intensity": 0부터 100 사이의 정수,
  "keywords": ["키워드1", "키워드2", "키워드3"],
  "situation_summary": "개인정보를 직접 드러내지 않는 상황 요약 한 문장"
}}
""")


SUMMARY_PROMPT = ChatPromptTemplate.from_template("""
너는 MoodTender의 개인정보 보호 요약기다.

역할:
- 사용자의 대화 내용을 DB에 저장하기 전에 비식별화된 요약문으로 바꾼다.
- 원문을 그대로 복사하지 않는다.
- 감정 흐름, 상황 맥락, 반복되는 개인 패턴만 남긴다.
- 이름, 장소, 기관명, 연락처, 계정 정보 등 개인을 특정할 수 있는 정보는 제거하거나 일반화한다.
- 의학적 진단이나 치료 판단은 만들지 않는다.

[비식별화 규칙]
- 사람 이름은 "가까운 사람", "친구", "가족", "동료"처럼 일반화한다.
- 회사명, 학교명, 팀명, 기관명은 "회사", "학교", "조직"처럼 일반화한다.
- 구체적인 지역, 장소, 주소는 "특정 장소", "지역", "학교", "회사"처럼 일반화한다.
- 전화번호, 이메일, 계좌번호, 주민등록번호, 학번, 사번, 주소는 저장하지 않는다.
- 사용자의 문장을 그대로 인용하지 않는다.
- 감정 판단을 과장하지 않는다.

[입력 텍스트]
{text}

비식별화된 요약문만 1~2문장으로 출력한다.
설명, 제목, 마크다운, 따옴표는 붙이지 않는다.
""")


RECEIPT_PROMPT = ChatPromptTemplate.from_template("""
너는 MoodTender의 감정 바텐더다.

아래 정보를 바탕으로 칵테일 소개 문장과 감정 영수증 문장을 만든다.

[규칙]
- 실제 음주 권유가 아니라 감정의 상징으로 표현한다.
- 마크다운, 이모지, 번호 목록은 쓰지 않는다.
- 한국어로 짧고 자연스럽게 작성한다.

[감정 분석]
감정 계열: {emotion_family}
감정의 결: {emotion_texture}
키워드: {keywords}

[칵테일 정보]
칵테일 방향: {cocktail_direction}
칵테일 색상: {cocktail_color}

[유사 과거 기록]
{related_memories}

[사용자 발화]
{user_text}

반드시 아래 JSON 형식으로만 출력한다.

{{
  "cocktail_line": "칵테일 소개 한 문장",
  "receipt_message": "감정 영수증 한 문장"
}}
""")


FREE_CHAT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """
너는 MoodTender의 감정 바텐더다.

첫 응답 이후 사용자의 이야기를 자연스럽게 이어 듣고 위로한다.

[대화 규칙]
- 사용자를 평가하거나 훈계하지 않는다.
- 감정을 과장하지 않고 차분하게 받아준다.
- 의학적 진단이나 치료 조언은 하지 않는다.
- 답변은 한국어로 작성한다.
- related_memories가 있으면 현재 대화와 자연스럽게 연결되는 내용만 참고한다.
- 관련 없는 과거 기억은 언급하지 않는다.

[유사 과거 기록]
{related_memories}
"""),
    MessagesPlaceholder(variable_name="history"),
    ("human", "{user_text}"),
])


def build_chains():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY 환경 변수를 .env에 설정해 주세요.")

    llm = ChatOpenAI(
        api_key=api_key,
        model="gpt-4o-mini",
        temperature=0.7,
    )

    emotion_chain = EMOTION_ROUTER_PROMPT | llm | JsonOutputParser()
    summary_chain = SUMMARY_PROMPT | llm | StrOutputParser()
    receipt_chain = RECEIPT_PROMPT | llm | JsonOutputParser()
    free_chat_chain = FREE_CHAT_PROMPT | llm | StrOutputParser()

    return emotion_chain, summary_chain, receipt_chain, free_chat_chain
def build_emotion_flow_context(
    related_memories: list[dict],
) -> str:
    if not related_memories:
        return "감정 변화 흐름 없음"

    flows = []

    for memory in related_memories:
        main_category = memory.get("main_category")
        sub_category = memory.get("sub_category")
        intensity = memory.get("emotion_intensity")

        if main_category and sub_category:
            if intensity is not None:
                flows.append(f"{main_category}/{sub_category}({intensity})")
            else:
                flows.append(f"{main_category}/{sub_category}")

    if not flows:
        return "감정 변화 흐름 없음"

    return "최근 유사 기억의 감정 흐름: " + " → ".join(flows)

def build_related_context(
    related_memories: list[dict],
    similar_chats: list[dict],
    emotion_flow: str = "",
) -> str:
    lines = []

    if emotion_flow:
        lines.append("[감정 변화 흐름]")
        lines.append(emotion_flow)

    if related_memories:
        lines.append("[장기 기억]")
        for memory in related_memories:
            memory_text = memory.get("memory_text")
            main_category = memory.get("main_category")
            sub_category = memory.get("sub_category")

            if memory_text:
                lines.append(
                    f"- {memory_text} "
                    f"(감정: {main_category}/{sub_category})"
                )

    if similar_chats:
        lines.append("[관련 과거 대화]")
        for chat in similar_chats:
            role = chat.get("role", "")
            content = chat.get("content", "")

            if content:
                lines.append(f"- {role}: {content}")

    if not lines:
        return "없음"

    return "\n".join(lines)


def build_bartender_input(
    user_text: str,
    emotion: dict,
    cocktail: dict,
    related_context: str,
) -> str:
    return f"""
사용자 발화:
{user_text}

감정 분석:
- 감정 계열: {emotion.get("emotion_family")}
- 감정의 결: {emotion.get("emotion_texture")}
- 감정 강도: {emotion.get("emotion_intensity")}
- 키워드: {emotion.get("keywords", [])}
- 상황 요약: {emotion.get("situation_summary")}

칵테일 방향:
{cocktail.get("cocktail_direction")}

칵테일 색상:
{cocktail.get("cocktail_color")}

참고할 과거 기록:
{related_context}

위 정보는 내부 참고용이다.
사용자에게는 자연스러운 바텐더 대사로만 답한다.
""".strip()


async def run_first_turn(
    emotion_chain,
    summary_chain,
    receipt_chain,
    user_id: int,
    session_id: str,
    user_text: str,
    db,
) -> tuple[dict, dict, dict]:
    safe_user_text = mask_sensitive_patterns(user_text)

    emotion = await asyncio.to_thread(
        emotion_chain.invoke,
        {"user_text": safe_user_text},
    )

    cocktail = await retrieve_emotion_dictionary(
        main_category=emotion.get("emotion_family", ""),
        sub_category=emotion.get("emotion_texture", ""),
    ) or {
        "cocktail_direction": "차분하게 감정을 정리하는 부드러운 칵테일",
        "cocktail_color": "투명",
    }

    related_memories = await retrieve_similar_user_memories(
        user_id=user_id,
        query_text=safe_user_text,
        limit=3,
    )

    similar_chats = await retrieve_similar_chat_messages(
        user_id=user_id,
        query_text=safe_user_text,
        limit=3,
    )

    emotion_flow = build_emotion_flow_context(related_memories)

    related_context = build_related_context(
        related_memories=related_memories,
        similar_chats=similar_chats,
        emotion_flow=emotion_flow,
    )

    bartender_input = build_bartender_input(
        user_text=safe_user_text,
        emotion=emotion,
        cocktail=cocktail,
        related_context=related_context,
    )

    bartender_reply_result = await generate_bartender_reply(
        user_id,
        bartender_input,
        db,
        save_messages=False,
    )

    if isinstance(bartender_reply_result, tuple):
        bartender_reply = bartender_reply_result[0]
    else:
        bartender_reply = bartender_reply_result

    await save_chat_message(
        user_id=user_id,
        role="user",
        content=user_text,
    )

    await save_chat_message(
        user_id=user_id,
        role="assistant",
        content=bartender_reply,
    )

    try:
        receipt = await asyncio.to_thread(
            receipt_chain.invoke,
            {
                "user_text": safe_user_text,
                "emotion_family": emotion.get("emotion_family"),
                "emotion_texture": emotion.get("emotion_texture"),
                "keywords": emotion.get("keywords", []),
                "cocktail_direction": cocktail.get("cocktail_direction"),
                "cocktail_color": cocktail.get("cocktail_color"),
                "related_memories": related_context,
            },
        )
    except Exception:
        receipt = {
            "cocktail_line": "",
            "receipt_message": "",
        }

    bartender_result = {
        "bartender_reply": bartender_reply,
        "cocktail_line": receipt.get("cocktail_line"),
        "receipt_message": receipt.get("receipt_message"),
        "used_memory": bool(related_memories or similar_chats),
    }

    return bartender_result, emotion, cocktail


async def run_free_chat(
    free_chat_chain,
    user_id: int,
    user_text: str,
    history: list,
) -> str:
    safe_user_text = mask_sensitive_patterns(user_text)

    related_memories = await retrieve_similar_user_memories(
        user_id=user_id,
        query_text=safe_user_text,
        limit=3,
    )

    similar_chats = await retrieve_similar_chat_messages(
        user_id=user_id,
        query_text=safe_user_text,
        limit=3,
    )

    emotion_flow = build_emotion_flow_context(related_memories)

    related_context = build_related_context(
        related_memories=related_memories,
        similar_chats=similar_chats,
    )

    response = await asyncio.to_thread(
        free_chat_chain.invoke,
        {
            "user_text": safe_user_text,
            "history": history,
            "related_memories": related_context,
        },
    )

    await save_chat_message(
        user_id=user_id,
        role="user",
        content=user_text,
    )

    await save_chat_message(
        user_id=user_id,
        role="assistant",
        content=response,
    )

    return response


async def finalize_memory(
    summary_chain,
    user_id: int,
    session_id: str,
    emotion: dict,
    cocktail: dict,
    bartender_result: dict,
    conversation_text: str,
) -> None:
    safe_conversation_text = mask_sensitive_patterns(conversation_text)

    conversation_summary = await asyncio.to_thread(
        summary_chain.invoke,
        {"text": safe_conversation_text},
    )

    await save_user_memory(
        user_id=user_id,
        memory_text=conversation_summary,
        main_category=emotion.get("emotion_family"),
        sub_category=emotion.get("emotion_texture"),
        emotion_intensity=int(emotion.get("emotion_intensity", 50)),
    )

    await save_emotion_receipt(
        user_id=user_id,
        dominant_sub_category=emotion.get("emotion_texture"),
        recommended_cocktail=cocktail.get("cocktail_direction"),
        summary_note=bartender_result.get("receipt_message"),
    )


def new_session_id() -> str:
    return str(uuid.uuid4())