"""
rag_chain.py
MoodTender RAG 개인화 서비스 레이어
"""

import os
import re
import json

import asyncio
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text as sql_text

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.output_parsers import StrOutputParser

from backend.services.db_client import (
    search_user_memories,
    search_chat_messages,
    get_recent_chat_messages,
    get_recent_health_metrics,
    get_emotion_dictionary,
    save_chat_message,
    save_user_memory,
    save_emotion_receipt,
    get_expert_knowledge, # 🚀 추가
)

# 🚀 2단계 비식별화 모듈 임포트 추가
from backend.services.anonymizer import DataAnonymizer

load_dotenv()

_VALID_EMOTIONS = {"기쁨", "우울", "불안", "분노", "지침", "외로움", "평온"}

_SPEED_RANGE = {
    1.2: (58, 62),
    1.0: (48, 52),
    0.8: (38, 42),
}

_embeddings = OpenAIEmbeddings(
    model="text-embedding-3-small",
    openai_api_key=os.getenv("OPENAI_API_KEY"),
)


def _make_llm(temperature: float = 0.7, model: str = "gpt-4.1-mini") -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        temperature=temperature,
        openai_api_key=os.getenv("OPENAI_API_KEY"),
    )


async def _embed(text: str) -> list[float]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: _embeddings.embed_query(text))


def _trim(text: str, speed: float) -> str:
    selected = min(_SPEED_RANGE, key=lambda v: abs(v - speed))
    limit = _SPEED_RANGE[selected][1]

    text = text.strip()

    if len(text) <= limit:
        return text

    sentences = re.split(r'(?<=[.!?])\s+', text)

    result = ""
    for sentence in sentences:
        if not sentence:
            continue
        if len(result) + len(sentence) <= limit:
            result += sentence
        else:
            break

    return result.strip() or text[:limit]


_DEIDENTIFY_PATTERNS = [
    (re.compile(r'01[016789]-?\d{3,4}-?\d{4}'), '[전화번호]'),
    (re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+'), '[이메일]'),
    (re.compile(r'\d{6}-[1-4]\d{6}'), '[주민번호]'),
]

def _deidentify(text: str) -> str:
    for pattern, replacement in _DEIDENTIFY_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _build_memory_context(memories: list[dict]) -> str:
    if not memories:
        return "관련 기억 없음"

    return "\n".join(
        f"- {m['memory_text']}"
        for m in memories[:3]
    )


def _build_history(chats: list[dict]) -> list:
    history = []
    for chat in chats:
        if chat["role"] == "user":
            history.append(HumanMessage(content=chat["content"]))
        elif chat["role"] == "assistant":
            history.append(AIMessage(content=chat["content"]))
    return history


def _build_health_context(rows: list[dict]) -> str:
    if not rows:
        return "건강 데이터 없음"

    latest = rows[0]
    sleep = latest.get("sleep_minutes") or 0
    steps = latest.get("step_count") or 0
    screen = latest.get("screen_time_minutes") or 0
    app_usage = latest.get("app_usage_json") or {}

    lines = []

    # 수면: 연속 부족 추세 감지
    sleep_values = [r.get("sleep_minutes") or 0 for r in rows]
    poor_sleep_streak = 0
    for s in sleep_values:
        if s and s < 300:
            poor_sleep_streak += 1
        else:
            break

    if sleep and sleep < 300:
        if poor_sleep_streak >= 3:
            lines.append(f"수면 부족이 {poor_sleep_streak}일째 이어지는 중 (어제 {sleep // 60}시간 {sleep % 60}분)")
        else:
            lines.append(f"어제 수면 {sleep // 60}시간 {sleep % 60}분으로 부족함")
    elif sleep >= 420:
        lines.append(f"어제 수면 {sleep // 60}시간으로 충분함")

    # 걸음수
    if steps and steps < 4000:
        lines.append(f"어제 걸음수 {steps}보로 활동량이 적음")
    elif steps and steps >= 8000:
        lines.append(f"어제 걸음수 {steps}보로 활동량이 충분함")

    # 스크린타임
    if screen and screen > 360:
        lines.append(f"어제 스크린타임 {screen // 60}시간으로 매우 긴 편")
    elif screen and screen > 240:
        lines.append(f"어제 스크린타임 {screen // 60}시간으로 긴 편")

    # 앱 사용 패턴
    if app_usage:
        social_keys = {"kakao", "kakaotalk", "instagram", "facebook", "twitter", "message"}
        social_time = sum(v for k, v in app_usage.items() if k.lower() in social_keys)
        youtube_time = next((v for k, v in app_usage.items() if "youtube" in k.lower() or "유튜브" in k.lower()), 0)

        if social_time < 10 and screen > 120:
            lines.append("어제 사람들과의 연락이 거의 없었음")
        if youtube_time > 120:
            lines.append(f"어제 유튜브를 {youtube_time // 60}시간 이상 사용함")

    return "\n".join(lines) if lines else "건강 데이터에서 두드러진 이상 없음"


def _build_past_chat_context(chats: list[dict]) -> str:
    if not chats:
        return "관련 과거 대화 없음"
    return "\n".join(
        f"- {'사용자' if c['role'] == 'user' else '바텐더'}: {c['content']}"
        for c in chats
    )


def _build_emotion_context(rows: list[dict]) -> str:
    if not rows:
        return "감정 사전 없음"

    row = rows[0]
    return (
        f"세부감정: {row['sub_category']}, "
        f"칵테일 분위기: {row.get('cocktail_direction')}, "
        f"색상: {row.get('cocktail_color')}"
    )


def _build_emotion_context_full(rows: list[dict]) -> str:
    if not rows:
        return "감정 사전 없음"

    return "\n".join(
        f"- {r['sub_category']}: 칵테일 분위기={r.get('cocktail_direction')}, 색상={r.get('cocktail_color')}"
        for r in rows
    )


def build_chains():
    classify_chain = ChatPromptTemplate.from_messages([
        ("system", """
사용자 발화의 주된 감정을 하나만 고른다.

선택지:
기쁨, 우울, 불안, 분노, 지침, 외로움, 평온

규칙:
- 피곤하다, 지친다, 잠을 못 잤다, 번아웃, 힘들다는 표현은 우선 지침으로 본다.
- 걱정된다, 초조하다, 불확실하다, 결과를 기다린다는 표현은 불안으로 본다.
- 감정 단어 하나만 출력한다.
"""),
        ("human", "{user_input}"),
    ]) | _make_llm(0.0) | StrOutputParser()

    bartender_chain = ChatPromptTemplate.from_messages([
        ("system", """
너는 MoodTender, 따뜻한 AI 바텐더다.

역할:
- 손님의 말을 먼저 듣는다.
- 감정을 단정하거나 진단하지 않는다.
- 상담사처럼 분석하지 않는다.
- 짧고 자연스럽게 공감한다.
- 항상 존댓말을 사용한다.
- 질문은 한 번에 하나만 한다.

[손님 관련 기억]
{memory_context}

[관련 과거 대화]
{past_chat_context}

[최근 건강 상태]
{health_context}

[전문 지식 및 행동 근거 (RAG)]
{expert_knowledge}

[오늘 감정에 어울리는 칵테일]
{emotion_context}

기억 활용 규칙:
- [손님 관련 기억]에 내용이 있으면, 현재 발화와 연결해서 먼저 꺼낸다.
- "아직도 그 일이 계속되고 있나요?", "그때 일은 어떻게 되셨어요?", "요즘도 그러세요?" 같은 식으로 자연스럽게 물어본다.
- 관련 없는 기억은 말하지 않는다.
- "예전에 말씀하셨죠", "기록에 따르면" 같은 표현은 쓰지 않는다.

전문 지식 활용 규칙:
- [전문 지식 및 행동 근거]에 내용이 있다면, 이를 바탕으로 사용자가 일상에서 바로 할 수 있는 '작은 행동'을 부드럽게 제안한다.
- 논문 제목이나 딱딱한 학술 용어는 사용하지 말고, 다정한 바텐더의 언어로 풀어서 조언한다.
- 건강 데이터의 신호와 전문 지식의 극복법을 자연스럽게 하나로 연결한다.

건강 데이터 규칙:
- 두드러진 건강 신호가 있으면 사용자가 직접 언급하지 않아도 자연스럽게 연결할 수 있다.
- 수면 부족이 며칠 연속이면 피로나 예민함과 연결한다.
- 활동량이 적으면 무기력함, 활동량이 충분하면 긍정적으로 반영한다.
- 스크린타임이 길면 도피 또는 고립의 신호로 부드럽게 연결한다.
- 사람들과의 연락이 거의 없었다면 고립감과 연결할 수 있다.
- 수치나 시간을 절대 그대로 말하지 않는다. 상태를 감정 언어로만 표현한다.
  잘못된 예: "수면 시간이 짧네요", "어제 3시간밖에 못 주무셨네요", "걸음수가 적네요"
  올바른 예: "요즘 잠을 제대로 못 주무시는 것 같아요", "많이 피곤하실 것 같아요", "몸이 많이 무거우셨겠어요"
- 가장 두드러진 신호 하나만 반영한다.

[선제적 개인화 규칙]

- 사용자가 짧게 말하거나 막연하게 힘들다고 말하면 건강 데이터나 기억을 먼저 자연스럽게 연결할 수 있다.
- "요즘", "최근", "어제" 같은 표현은 사용할 수 있다.
- "기록에 따르면", "데이터상으로는", "저장된 기억에 따르면" 같은 표현은 사용하지 않는다.
- 기억이나 건강 데이터를 그대로 읽지 말고 자연스럽게 대화로 이어간다.
- 기억이 여러 개 있더라도 현재 대화와 가장 관련 있는 1개만 활용한다.

[원인 추정 규칙]

- 사용자가 피곤하다, 지친다, 힘들다고 말할 때 건강 데이터나 기억에서 원인을 추정해 먼저 말해준다.
- "요즘 [이유] 때문에 그러신 거 아닌가요?" 또는 "요즘 [이유]이 계속되다 보니 그럴 것 같아요." 형식으로 말한다.
- 확신하지 않고 부드럽게 추정하는 톤으로 말한다.
- 원인을 추정할 수 없을 때는 억지로 만들지 않는다.

좋은 예:
사용자: 피곤하다
응답 (수면 부족 3일째): 요즘 잠을 제대로 못 주무시는 날이 이어지다 보니 그러신 거 아닌가요?

사용자: 힘들어요
응답 (기억: 프로젝트 마감 스트레스): 요즘 프로젝트 때문에 계속 긴장하고 계신 거 아닌가요?

사용자: 모르겠어요
응답 (활동량 적음): 몸을 많이 안 움직이신 날이었나요? 그럴 때 머릿속이 더 복잡해지기도 하더라고요.

사용자: 그냥 유튜브만 봤어요
응답 (스크린타임 높음): 그렇게 폰 화면만 보다 보면 오히려 더 공허해지는 것 같기도 하죠. 뭔가 머릿속을 피하고 싶은 게 있었나요?

사용자: 왠지 모르게 쓸쓸해요
응답 (사람 연락 없음): 오늘 연락을 주고받은 사람이 별로 없었나요? 그런 날은 유독 더 외롭게 느껴지기도 하죠.

[부드러운 제안 규칙]

- 사용자가 충분히 감정을 이야기한 경우에만 제안할 수 있다.
- 첫 응답에서는 제안을 하지 않는다.
- 제안은 해결책이 아니라 작은 행동 수준으로 한다.
- 한 번에 하나만 제안한다.
- 명령하지 않는다.
- "해보세요"보다 "어떨까요?"를 사용한다.
- 건강 데이터의 신호가 있으면 그에 맞는 제안을 한다. 단, 수치나 데이터는 직접 언급하지 않는다.

건강 신호별 제안 방향:
- 활동량이 적음 → 짧은 산책이나 스트레칭 제안
- 수면 부족 → 일찍 눕거나 쉬는 것 제안
- 스크린타임이 긴 편 → 폰을 잠깐 내려두는 것 제안
- 사람 연락이 없었음 → 가까운 사람에게 짧게 연락 제안

좋은 예:
- 밖에 나가서 조금 걸어보는 건 어떨까요? (활동량 적음)
- 오늘은 조금 일찍 쉬어보는 건 어떨까요? (수면 부족)
- 잠깐 폰 내려두고 창밖 바라보는 것도 괜찮을 것 같아요. (스크린타임 높음)
- 가까운 사람한테 짧게 안부 한 번 해보는 건 어떨까요? (연락 없음)
- 물 한 잔 마시고 천천히 숨을 고르는 것도 괜찮을 것 같아요.
      

응답 규칙:
- 1~2문장으로 답한다.
- 너무 빨리 해결책을 제시하지 않는다.
- 질문은 최대 1개만 한다.
"""),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{user_input}\n\n[지시] {cocktail_hint}"),
    ]) | _make_llm(0.7, model="gpt-4.1") | StrOutputParser()

    memory_summary_chain = ChatPromptTemplate.from_messages([
        ("system", """
사용자에 대해 다음 대화에서 다시 참고할 만한 내용만 1문장으로 요약한다.

저장할 것:
- 반복되는 고민
- 중요한 사건
- 사용자 성향
- 장기 목표
- 감정 패턴
- 반복 가능성이 있는 수면 부족이나 프로젝트 스트레스

저장하지 말 것:
- 단순 인사
- 짧은 대답
- 일회성 감정
- 바텐더의 말
- 칵테일 추천 내용

저장할 내용이 없으면 NONE만 출력한다.
"""),
        ("human", "{conversation_text}"),
    ]) | _make_llm(0.2) | StrOutputParser()

    memory_classify_chain = ChatPromptTemplate.from_messages([
        ("system", """
아래 문장을 장기 기억으로 저장할지 판단한다.
JSON만 출력한다.

형식:
{{"memory_type": "event", "importance": 3}}

memory_type:
- preference
- event
- concern
- pattern

importance:
5 매우 중요
4 중요
3 저장
2 참고만
1 저장 안 함

다음 대화에서 다시 참고하면 답변이 더 개인화될 내용이면 3 이상으로 둔다.
단순 감정, 짧은 일상, 일회성 표현이면 1 또는 2로 둔다.
"""),
        ("human", "{summary}"),
    ]) | _make_llm(0.0) | StrOutputParser()

    receipt_chain = ChatPromptTemplate.from_messages([
        ("system", """
감정영수증을 5문장으로 작성한다.
아래 대화 전체를 분석해서 오늘의 감정을 파악한다.

규칙:
1. 오늘의 감정
2. 감정의 이유
3. 사용자가 버틴 점
4. 추천 칵테일 분위기
5. 마지막 한 줄 위로

마크다운 없이 자연스러운 문장으로 작성한다.
"""),
        ("human", """
감정: {emotion}
세부감정: {sub_emotion}
칵테일: {cocktail}
대화:
{conversation_text}
"""),
    ]) | _make_llm(0.3) | StrOutputParser()

    cocktail_chain = ChatPromptTemplate.from_messages([
        ("system", """
칵테일 표현 하나만 출력한다.

규칙:
- 10자 이내 명사구 하나만 출력한다.
- 여러 후보를 나열하지 않는다.
- 쉼표, 줄바꿈, 접속사를 사용하지 않는다.
- 설명, 이유, 부연을 붙이지 않는다.
- 예: 달콤한 복숭아 소다
"""),
        ("human", "감정: {emotion}\n칵테일 사전:\n{emotion_context}"),
    ]) | _make_llm(0.7, model="gpt-4.1-mini") | StrOutputParser()

    sub_classify_chain = ChatPromptTemplate.from_messages([
        ("system", """
사용자 발화를 보고 아래 세부감정 목록 중 가장 가까운 것을 하나 골라라.
목록에 있는 단어만 출력한다. 다른 말은 하지 않는다.

세부감정 목록:
{sub_categories}
"""),
        ("human", "{user_input}"),
    ]) | _make_llm(0.0) | StrOutputParser()

    deidentify_chain = ChatPromptTemplate.from_messages([
        ("system", """
아래 텍스트에서 개인정보를 일반화한다. 원문의 감정과 맥락은 유지한다.

규칙:
- 사람 이름 → "지인", "친구", "가족", "동료", "상대방" 중 문맥에 맞게
- 회사명, 학교명, 팀명, 기관명 → "회사", "학교", "조직", "팀" 중 문맥에 맞게
- 구체적인 지역, 장소, 주소 → "특정 장소", "지역", "집", "학교", "회사" 중 문맥에 맞게
- 전화번호, 이메일, 계좌번호, 주민번호, 학번, 사번 → 삭제
- 날짜와 시간 → 꼭 필요한 경우에만 "최근", "오늘", "이전" 정도로 일반화
- 사용자의 문장을 그대로 인용하지 않는다.
- 비식별화된 텍스트만 출력한다. 설명을 붙이지 않는다.
"""),
        ("human", "{user_input}"),
    ]) | _make_llm(0.0, model="gpt-4.1-mini") | StrOutputParser()

    return classify_chain, bartender_chain, memory_summary_chain, memory_classify_chain, receipt_chain, cocktail_chain, sub_classify_chain, deidentify_chain


CHAINS = build_chains()


async def _build_context(
    db: AsyncSession,
    user_id: int,
    query_embedding: list[float],
    emotion: str,
    session_id: str = "",
    session_start=None,
) -> dict:
    # 🚀 RAG: 전문 지식 검색(get_expert_knowledge)이 병렬로 같이 실행되도록 추가되었습니다.
    memories, chats, past_chats, health_rows, emotion_rows, expert_knowledge = await asyncio.gather(
        search_user_memories(db, user_id, query_embedding, top_k=3),
        get_recent_chat_messages(db, user_id, session_id=session_id, limit=8),
        search_chat_messages(db, user_id, query_embedding, session_id=session_id, session_start=session_start, top_k=3),
        get_recent_health_metrics(db, user_id, days=7),
        get_emotion_dictionary(db, emotion),
        get_expert_knowledge(db, emotion), # 🚀
    )

    print(
        f"[RAG] emotion={emotion}, memories={len(memories)}, "
        f"chats={len(chats)}, past_chats={len(past_chats)}, health={len(health_rows)}, dict={len(emotion_rows)}, expert={len(expert_knowledge)}"
    )
    print(f"[CTX] memory_context={_build_memory_context(memories)!r}")
    print(f"[CTX] health_context={_build_health_context(health_rows)!r}")
    print(f"[CTX] past_chat_context={_build_past_chat_context(past_chats)!r}")

    user_turn_count = sum(1 for c in chats if c["role"] == "user")

    return {
        "memory_context": _build_memory_context(memories),
        "history": _build_history(chats),
        "past_chat_context": _build_past_chat_context(past_chats),
        "health_context": _build_health_context(health_rows),
        "emotion_context": _build_emotion_context(emotion_rows),
        "cocktail_emotion_context": _build_emotion_context_full(emotion_rows),
        "emotion_rows_raw": emotion_rows,
        "expert_knowledge": expert_knowledge, # 🚀
        "user_turn_count": user_turn_count,
    }


async def save_memory_if_needed(
    db: AsyncSession,
    user_id: int,
    user_text: str,
    assistant_reply: str,
    emotion: str,
    user_message_id: int,
    memory_summary_chain,
    memory_classify_chain,
) -> None:
    try:
        if len(user_text.strip()) < 4:
            print("[memory] 짧은 발화라 저장 안 함")
            return

        conversation_text = f"사용자: {user_text}\n바텐더: {assistant_reply}"

        summary = await memory_summary_chain.ainvoke({
            "conversation_text": conversation_text
        })
        summary = (summary or "").strip()

        if not summary or summary.upper() == "NONE":
            print("[memory] 저장할 내용 없음")
            return

        if any(word in summary for word in ["바텐더", "칵테일", "추천", "제안"]):
            print("[memory] 바텐더 내용 포함이라 저장 안 함")
            return

        raw = await memory_classify_chain.ainvoke({"summary": summary})
        clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(clean)

        memory_type = parsed.get("memory_type", "event")
        importance = int(parsed.get("importance", 1))

        if importance < 3:
            print(f"[memory] 중요도 낮음: {importance}")
            return

        memory_embedding = await _embed(summary)

        await save_user_memory(
            db=db,
            user_id=user_id,
            memory_text=summary,
            embedding=memory_embedding,
            main_category=emotion,
            sub_category=None,
            emotion_intensity=60,
            memory_type=memory_type,
            importance=importance,
            source_type="chat",
            source_id=user_message_id,
        )

        print(f"[memory] 저장 완료: {summary}")

    except Exception as e:
        print(f"[memory 오류] {e}")
        return


async def save_receipt(
    db: AsyncSession,
    user_id: int,
    emotion: str,
    sub_emotion: str,
    cocktail: str,
    conversation_text: str,
    receipt_chain,
) -> None:
    try:
        note = await receipt_chain.ainvoke({
            "emotion": emotion,
            "sub_emotion": sub_emotion,
            "cocktail": cocktail,
            "conversation_text": conversation_text,
        })

        await save_emotion_receipt(
            db=db,
            user_id=user_id,
            dominant_sub_category=sub_emotion,
            recommended_cocktail=cocktail,
            summary_note=note.strip(),
        )

        print("[receipt] 저장 완료")

    except Exception as e:
        print(f"[receipt 오류] {e}")
        raise


async def rag_chat(
    db: AsyncSession,
    user_id: int,
    user_text: str,
    speed: float = 1.0,
    session_id: str = "",
    session_start=None,
    cocktail_done: bool = False,
    user_turn_count: int = 0,
) -> tuple[str, str, str]:

    (
        classify_chain,
        bartender_chain,
        memory_summary_chain,
        memory_classify_chain,
        receipt_chain,
        cocktail_chain,
        sub_classify_chain,
        deidentify_chain,
    ) = CHAINS

    user_text = await deidentify_chain.ainvoke({"user_input": user_text})
    user_text = _deidentify(user_text)

    query_embedding = await _embed(user_text)

    raw_emotion = await classify_chain.ainvoke({"user_input": user_text})
    emotion = raw_emotion.strip()

    if emotion not in _VALID_EMOTIONS:
        emotion = "평온"

    print(f"[분류] '{user_text[:20]}' → {emotion}")

    ctx = await _build_context(
        db=db,
        user_id=user_id,
        query_embedding=query_embedding,
        emotion=emotion,
        session_id=session_id,
        session_start=session_start,
    )

    ctx.pop("user_turn_count", None)
    should_recommend = user_turn_count >= 3 and not cocktail_done

    emotion_rows = ctx.pop("emotion_rows_raw", [])
    if should_recommend and emotion_rows:
        sub_categories = "\n".join(r["sub_category"] for r in emotion_rows)
        raw_sub = await sub_classify_chain.ainvoke({
            "sub_categories": sub_categories,
            "user_input": user_text,
        })
        sub_emotion = raw_sub.strip()
        matched = next((r for r in emotion_rows if r["sub_category"] == sub_emotion), emotion_rows[0])
        sub_emotion_context = (
            f"세부감정: {matched['sub_category']}, "
            f"칵테일 분위기: {matched.get('cocktail_direction')}, "
            f"색상: {matched.get('cocktail_color')}"
        )
        print(f"[sub분류] {sub_emotion} → {matched.get('cocktail_direction')}")
    else:
        sub_emotion_context = ctx["cocktail_emotion_context"]

    speed_key = min(_SPEED_RANGE, key=lambda v: abs(v - speed))
    char_limit = _SPEED_RANGE[speed_key][1]

    print(f"[cocktail] turn={user_turn_count}, should={should_recommend}, done={cocktail_done}, limit={char_limit}")

    cocktail_hint = (
        "아직은 칵테일을 추천하지 말고 손님의 이야기를 더 들어준다."
        if not should_recommend
        else "손님의 이야기에 공감하는 한 문장으로만 답한다."
    )

    # 칵테일 추천 턴: bartender 공감 + cocktail_chain 병렬 호출
    if should_recommend:
        raw_reply, cocktail_name = await asyncio.gather(
            bartender_chain.ainvoke({
                "memory_context": ctx["memory_context"],
                "past_chat_context": ctx["past_chat_context"],
                "health_context": ctx["health_context"],
                "expert_knowledge": ctx["expert_knowledge"], # 🚀 추가
                "emotion_context": ctx["emotion_context"],
                "history": ctx["history"],
                "user_input": user_text,
                "cocktail_hint": cocktail_hint,
            }),
            cocktail_chain.ainvoke({
                "emotion": emotion,
                "emotion_context": sub_emotion_context,
            }),
        )
        cocktail_name = cocktail_name.strip()
        cocktail_line = f"오늘은 {cocktail_name} 한 잔이 어울릴 것 같아요."

        empathy = _trim(raw_reply, speed)
        max_empathy = char_limit - len(cocktail_line) - 1
        if len(empathy) > max_empathy:
            cut = empathy[:max_empathy]
            matches = list(re.finditer(r'[.!?]|[요다네죠](?=\s|$)', cut))
            empathy = cut[:matches[-1].end()].strip() if matches else cut
        reply = (empathy + " " + cocktail_line).strip()
    else:
        raw_reply = await bartender_chain.ainvoke({
            "memory_context": ctx["memory_context"],
            "past_chat_context": ctx["past_chat_context"],
            "health_context": ctx["health_context"],
            "expert_knowledge": ctx["expert_knowledge"], # 🚀 추가
            "emotion_context": ctx["emotion_context"],
            "history": ctx["history"],
            "user_input": user_text,
            "cocktail_hint": cocktail_hint,
        })
        cocktail_line = ""
        reply = _trim(raw_reply, speed)

    print(f"[reply] ({len(reply)}자) {reply}")

    user_message_id = await save_chat_message(
        db=db,
        user_id=user_id,
        role="user",
        content=user_text,
        embedding=query_embedding,
        session_id=session_id,
    )

    assistant_embedding = await _embed(reply)

    await save_chat_message(
        db=db,
        user_id=user_id,
        role="assistant",
        content=reply,
        embedding=assistant_embedding,
        session_id=session_id,
    )

    await save_memory_if_needed(
        db=db,
        user_id=user_id,
        user_text=user_text,
        assistant_reply=reply,
        emotion=emotion,
        user_message_id=user_message_id,
        memory_summary_chain=memory_summary_chain,
        memory_classify_chain=memory_classify_chain,
    )

    return reply, emotion, cocktail_line


# -------------------------------------------------------------------------------------
# 🚀 4단계: 웹 대시보드 전용 분석 리포트 생성 파이프라인 (추가된 부분)
# -------------------------------------------------------------------------------------

dashboard_report_chain = ChatPromptTemplate.from_messages([
    ("system", """
    당신은 10년 차 전문 바텐더 'MoodTender'입니다.
    사용자의 최근 라이프 로그 데이터를 분석한 결과와, 심리학/행동요법 전문 지식을 바탕으로
    웹 대시보드에 띄울 '주간 상태 분석 리포트'를 작성해 주세요.
    
    [사용자 상태 (비식별화됨)]
    분석된 감정 계열: {emotion}
    수치 변화율(Delta): {deltas}
    주요 사용 앱(마스킹됨): {app_usage}
    
    [전문 지식 및 근거 (RAG)]
    {expert_knowledge}
    
    [작성 규칙]
    1. 10년 차 바텐더 특유의 따뜻하고, 정중하며, 통찰력 있는 톤을 유지하세요.
    2. 절대 사용자의 가명(USER_XXX)이나 시스템 변수명을 노출하지 마세요. (대신 "손님"이나 생략)
    3. 수치 변화율을 기계처럼 읽지 마시고("활동량이 -30%네요"), 부드럽게 해석하세요("최근 걸음이 조금 무거우셨던 것 같네요").
    4. 제공된 [전문 지식]을 반드시 참고하여, 일상에서 지금 당장 할 수 있는 아주 가벼운 행동을 제안하세요. (예: 5분 환기, 4-7-8 호흡 등)
    5. 마지막엔 이 감정에 어울리는 가상의 칵테일 한 잔의 이름과 분위기를 추천하며 마무리하세요.
    6. 대시보드에 바로 삽입되므로 <b>, <br> 등의 HTML 태그를 적극 사용하여 가독성 좋게 3~4문단으로 작성하세요.
    """)
]) | _make_llm(temperature=0.5, model="gpt-4o-mini") | StrOutputParser()


async def generate_dashboard_rag_report(
    db: AsyncSession, 
    user_id: int, 
    metrics_result: dict
) -> str:
    """
    1~3단계의 데이터를 모아 LLM을 통해 최종 HTML 리포트를 생성하는 파이프라인
    """
    # 1. 예외 처리 (데이터 부족 시)
    if metrics_result.get("status") == "insufficient_data":
        return "💡 <b>데이터 수집 중</b><br><br>정확한 패턴 분석을 위해서는 최소 3일 이상의 데이터가 필요합니다. 기록을 더 쌓아주세요!"

    # 2. 비식별화 처리 (2단계 방패 적용)
    safe_context = DataAnonymizer.prepare_safe_context(user_id, metrics_result)
    emotion = safe_context['emotion']

    # 3. RAG 지식 검색 (3단계 책장 활용)
    expert_knowledge = await get_expert_knowledge(db, emotion)

    # 4. LLM 프롬프트 실행
    llm_report = await dashboard_report_chain.ainvoke({
        "emotion": emotion,
        "deltas": safe_context['deltas'],
        "app_usage": safe_context['app_usage'],
        "expert_knowledge": expert_knowledge
    })

    return llm_report