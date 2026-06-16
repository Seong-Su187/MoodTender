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
from sqlalchemy import select, text as sql_text

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.output_parsers import StrOutputParser

from backend.models.domain import UserMemory
from backend.services.db_client import (
    search_user_memories,
    search_chat_messages,
    get_recent_chat_messages,
    get_recent_health_metrics,
    get_emotion_dictionary,
    save_chat_message,
    save_emotion_receipt,
    get_expert_knowledge, 
)

from backend.services.anonymizer import DataAnonymizer
from backend.services.analytics_service import extract_memory_from_chat 

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
    return "\n".join(f"- {m['memory_text']}" for m in memories[:3])

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

    if steps and steps < 4000:
        lines.append(f"어제 걸음수 {steps}보로 활동량이 적음")
    elif steps and steps >= 8000:
        lines.append(f"어제 걸음수 {steps}보로 활동량이 충분함")

    if screen and screen > 360:
        lines.append(f"어제 스크린타임 {screen // 60}시간으로 매우 긴 편")
    elif screen and screen > 240:
        lines.append(f"어제 스크린타임 {screen // 60}시간으로 긴 편")

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
    return "\n".join(f"- {'사용자' if c['role'] == 'user' else '바텐더'}: {c['content']}" for c in chats)

def _build_emotion_context(rows: list[dict]) -> str:
    if not rows:
        return "감정 사전 없음"
    row = rows[0]
    return f"세부감정: {row['sub_category']}, 칵테일 분위기: {row.get('cocktail_direction')}, 색상: {row.get('cocktail_color')}"

def build_chains():
    classify_chain = ChatPromptTemplate.from_messages([
        ("system", "사용자 발화의 주된 감정을 하나만 고른다.\n선택지: 기쁨, 우울, 불안, 분노, 지침, 외로움, 평온\n감정 단어 하나만 출력한다."),
        ("human", "{user_input}"),
    ]) | _make_llm(0.0) | StrOutputParser()

    bartender_chain = ChatPromptTemplate.from_messages([
        ("system", """
너는 MoodTender, 따뜻한 AI 바텐더다.
역할: 손님의 말을 먼저 듣고, 짧고 자연스럽게 공감하며, 질문은 한 번에 하나만 한다. 존댓말 필수.

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

[미완료된 칵테일 처방 및 고민 (리뷰 대기)]
{pending_cocktail_context}

규칙:
- 관련 기억이나 건강 데이터가 있으면 자연스럽게 대화에 녹여낸다. "기록에 따르면" 같은 말은 절대 쓰지 않는다.
- [미완료된 칵테일 처방 및 고민]이 "없음"이 아니라면, 대화 초반에 지난번 처방받은 칵테일을 실천해 보았는지 다정하게 물어본다.
- 한 번에 너무 많은 것을 제안하지 않는다.
"""),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{user_input}\n\n[지시] {cocktail_hint}"),
    ]) | _make_llm(0.7, model="gpt-4.1") | StrOutputParser()

    memory_summary_chain = ChatPromptTemplate.from_messages([
        ("system", "대화에서 다시 참고할 만한 내용만 1문장으로 요약한다. 저장할 내용이 없으면 NONE만 출력한다."),
        ("human", "{conversation_text}"),
    ]) | _make_llm(0.2) | StrOutputParser()

    memory_classify_chain = ChatPromptTemplate.from_messages([
        ("system", "아래 문장을 장기 기억으로 저장할지 판단한다. JSON만 출력한다. 형식: {{\"memory_type\": \"event\", \"importance\": 3}}"),
        ("human", "{summary}"),
    ]) | _make_llm(0.0) | StrOutputParser()

    receipt_chain = ChatPromptTemplate.from_messages([
        ("system", "대화를 분석해 오늘의 감정, 이유, 버틴 점, 추천 칵테일, 위로를 5문장으로 작성한다."),
        ("human", "감정: {emotion}\n세부감정: {sub_emotion}\n칵테일: {cocktail}\n대화:\n{conversation_text}"),
    ]) | _make_llm(0.3) | StrOutputParser()

    cocktail_chain = ChatPromptTemplate.from_messages([
        ("system", "10자 이내 명사구 하나만 출력한다. 예: 달콤한 복숭아 소다"),
        ("human", "감정: {emotion}\n칵테일 사전:\n{emotion_context}"),
    ]) | _make_llm(0.7, model="gpt-4.1-mini") | StrOutputParser()

    sub_classify_chain = ChatPromptTemplate.from_messages([
        ("system", "아래 세부감정 목록 중 가장 가까운 것을 하나 골라라.\n목록:\n{sub_categories}"),
        ("human", "{user_input}"),
    ]) | _make_llm(0.0) | StrOutputParser()

    deidentify_chain = ChatPromptTemplate.from_messages([
        ("system", "텍스트에서 개인정보를 일반화한다. 원문의 감정과 맥락은 유지한다."),
        ("human", "{user_input}"),
    ]) | _make_llm(0.0, model="gpt-4.1-mini") | StrOutputParser()

    return classify_chain, bartender_chain, memory_summary_chain, memory_classify_chain, receipt_chain, cocktail_chain, sub_classify_chain, deidentify_chain

CHAINS = build_chains()

async def _build_context(
    db: AsyncSession, user_id: int, query_embedding: list[float], emotion: str, session_id: str = "", session_start=None
) -> dict:
    memories, chats, past_chats, health_rows, emotion_rows, expert_knowledge = await asyncio.gather(
        search_user_memories(db, user_id, query_embedding, top_k=3),
        get_recent_chat_messages(db, user_id, session_id=session_id, limit=24),
        search_chat_messages(db, user_id, query_embedding, session_id=session_id, session_start=session_start, top_k=3),
        get_recent_health_metrics(db, user_id, days=7),
        get_emotion_dictionary(db, emotion),
        get_expert_knowledge(db, emotion),
    )

    pending_stmt = select(UserMemory).where(
        UserMemory.user_id == user_id, UserMemory.status == "PENDING", UserMemory.prescribed_cocktail != None
    ).order_by(UserMemory.created_at.desc()).limit(1)
    
    pending_res = await db.execute(pending_stmt)
    pending_m = pending_res.scalar_one_or_none()
    pending_cocktail_context = f"처방된 칵테일: {pending_m.prescribed_cocktail} (관련 고민: {pending_m.issue})" if pending_m else "없음"

    user_turn_count = sum(1 for c in chats if c["role"] == "user")

    return {
        "memory_context": _build_memory_context(memories),
        "history": _build_history(chats),
        "past_chat_context": _build_past_chat_context(past_chats),
        "health_context": _build_health_context(health_rows),
        "emotion_context": _build_emotion_context(emotion_rows),
        "emotion_rows_raw": emotion_rows,
        "expert_knowledge": expert_knowledge,
        "user_turn_count": user_turn_count,
        "pending_cocktail_context": pending_cocktail_context,
    }

async def save_memory_if_needed(
    db: AsyncSession, user_id: int, user_text: str, assistant_reply: str, emotion: str, 
    user_message_id: int, memory_summary_chain, memory_classify_chain
) -> None:
    try:
        if len(user_text.strip()) < 4: return

        conversation_text = f"사용자: {user_text}\n바텐더: {assistant_reply}"

        summary = await memory_summary_chain.ainvoke({"conversation_text": conversation_text})
        summary = (summary or "").strip()

        if not summary or summary.upper() == "NONE": return
        if any(word in summary for word in ["바텐더", "칵테일", "추천", "제안"]): return

        raw = await memory_classify_chain.ainvoke({"summary": summary})
        clean = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(clean)

        memory_type = parsed.get("memory_type", "event")
        importance = int(parsed.get("importance", 1))

        if importance < 3: return

        memory_embedding = await _embed(summary)

        extracted = await extract_memory_from_chat(conversation_text)
        issue_val = extracted.get("issue")
        is_issue = bool(issue_val and issue_val != "없음")

        new_memory = UserMemory(
            user_id=user_id,
            memory_text=summary,
            embedding=memory_embedding, 
            main_category=emotion,
            sub_category=extracted.get("emotion") if is_issue else None,
            emotion_intensity=60,
            memory_type=memory_type,
            importance=importance,
            source_type="chat",
            source_id=user_message_id,
            issue=issue_val if is_issue else None,
            status="PENDING" if is_issue else None 
        )
        db.add(new_memory)
        await db.commit()

    except Exception as e:
        print(f"[memory 통합 저장 오류] {e}")
        await db.rollback()
        return

async def save_receipt(
    db: AsyncSession, user_id: int, emotion: str, sub_emotion: str, cocktail: str, conversation_text: str, receipt_chain
) -> None:
    try:
        note = await receipt_chain.ainvoke({
            "emotion": emotion, "sub_emotion": sub_emotion, "cocktail": cocktail, 
            "conversation_text": conversation_text, "receipt_chain": receipt_chain
        })
        await save_emotion_receipt(
            db=db, user_id=user_id, dominant_sub_category=sub_emotion, recommended_cocktail=cocktail, summary_note=note.strip()
        )
    except Exception as e:
        print(f"[receipt 오류] {e}")
        raise

async def rag_chat(
    db: AsyncSession, user_id: int, user_text: str, speed: float = 1.0, session_id: str = "", 
    session_start=None, cocktail_done: bool = False, user_turn_count: int = 0
) -> tuple[str, str, str]:

    (classify_chain, bartender_chain, memory_summary_chain, memory_classify_chain, 
     receipt_chain, cocktail_chain, sub_classify_chain, deidentify_chain) = CHAINS

    user_text = await deidentify_chain.ainvoke({"user_input": user_text})
    user_text = _deidentify(user_text)

    query_embedding = await _embed(user_text)
    raw_emotion = await classify_chain.ainvoke({"user_input": user_text})
    emotion = raw_emotion.strip()
    if emotion not in _VALID_EMOTIONS: emotion = "평온"

    ctx = await _build_context(db=db, user_id=user_id, query_embedding=query_embedding, emotion=emotion, session_id=session_id, session_start=session_start)
    ctx.pop("user_turn_count", None)
    
    # 🚀 [버그 해결 1] 사용자가 칵테일을 달라고 '직접적으로' 요청했는지 체크합니다!
    explicit_request = any(keyword in user_text for keyword in ["칵테일", "추천", "한잔", "한 잔", "메뉴", "술", "줘"])
    
    # 🚀 3턴이 넘었거나 OR 사용자가 명시적으로 달라고 했으면 추천 모드로 돌입!
    should_recommend = (user_turn_count >= 3 or explicit_request) and not cocktail_done

    emotion_rows = ctx.pop("emotion_rows_raw", [])
    if should_recommend and emotion_rows:
        sub_categories = "\n".join(r["sub_category"] for r in emotion_rows)
        raw_sub = await sub_classify_chain.ainvoke({"sub_categories": sub_categories, "user_input": user_text})
        sub_emotion = raw_sub.strip()
        matched = next((r for r in emotion_rows if r["sub_category"] == sub_emotion), emotion_rows[0])
        sub_emotion_context = f"세부감정: {matched['sub_category']}, 칵테일 분위기: {matched.get('cocktail_direction')}, 색상: {matched.get('cocktail_color')}"
    else:
        sub_emotion_context = ctx["emotion_context"]

    speed_key = min(_SPEED_RANGE, key=lambda v: abs(v - speed))
    char_limit = _SPEED_RANGE[speed_key][1]
    
    # 🚀 강력 지시어
    cocktail_hint = "아직은 칵테일을 추천하지 말고 손님의 이야기를 더 들어준다." if not should_recommend else "손님의 이야기에 짧게 공감하고, 더 이상 질문하지 않는다."

    if should_recommend:
        raw_reply, cocktail_name = await asyncio.gather(
            bartender_chain.ainvoke({
                "memory_context": ctx["memory_context"], "past_chat_context": ctx["past_chat_context"],
                "health_context": ctx["health_context"], "expert_knowledge": ctx["expert_knowledge"], 
                "emotion_context": ctx["emotion_context"], "history": ctx["history"],
                "user_input": user_text, "cocktail_hint": cocktail_hint, "pending_cocktail_context": ctx["pending_cocktail_context"]
            }),
            cocktail_chain.ainvoke({"emotion": emotion, "emotion_context": sub_emotion_context}),
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
            "memory_context": ctx["memory_context"], "past_chat_context": ctx["past_chat_context"],
            "health_context": ctx["health_context"], "expert_knowledge": ctx["expert_knowledge"], 
            "emotion_context": ctx["emotion_context"], "history": ctx["history"],
            "user_input": user_text, "cocktail_hint": cocktail_hint, "pending_cocktail_context": ctx["pending_cocktail_context"]
        })
        cocktail_line = ""
        reply = _trim(raw_reply, speed)

    user_message_id = await save_chat_message(db=db, user_id=user_id, role="user", content=user_text, embedding=query_embedding, session_id=session_id)
    assistant_embedding = await _embed(reply)
    await save_chat_message(db=db, user_id=user_id, role="assistant", content=reply, embedding=assistant_embedding, session_id=session_id)

    await save_memory_if_needed(
        db=db, user_id=user_id, user_text=user_text, assistant_reply=reply, emotion=emotion,
        user_message_id=user_message_id, memory_summary_chain=memory_summary_chain, memory_classify_chain=memory_classify_chain
    )

    return reply, emotion, cocktail_line

dashboard_report_chain = ChatPromptTemplate.from_messages([
    ("system", """
    당신은 10년 차 전문 바텐더 'MoodTender'입니다.
    사용자의 최근 라이프 로그 데이터를 분석한 결과와, 심리학/행동요법 전문 지식을 바탕으로
    웹 대시보드에 띄울 '주간 상태 분석 리포트'를 작성해 주세요.
    
    [사용자 상태]
    분석된 감정 계열: {emotion}
    수치 변화율(Delta): {deltas}
    주요 사용 앱: {app_usage}
    
    [전문 지식 및 근거 (RAG)]
    {expert_knowledge}
    
    [작성 규칙]
    1. 따뜻하고 정중하며 통찰력 있는 톤을 유지하세요.
    2. 전문 지식을 참고하여 일상에서 할 수 있는 작은 행동을 제안하세요.
    3. 마지막엔 이 감정에 어울리는 가상의 칵테일 한 잔을 추천하세요.
    4. <b>, <br> 등 HTML 태그를 적극 사용하여 3~4문단으로 작성하세요.
    """)
]) | _make_llm(temperature=0.5, model="gpt-4o-mini") | StrOutputParser()

async def generate_dashboard_rag_report(db: AsyncSession, user_id: int, metrics_result: dict) -> str:
    if metrics_result.get("status") == "insufficient_data":
        return "💡 <b>데이터 수집 중</b><br><br>정확한 패턴 분석을 위해서는 최소 3일 이상의 데이터가 필요합니다."
    safe_context = DataAnonymizer.prepare_safe_context(user_id, metrics_result)
    emotion = safe_context['emotion']
    expert_knowledge = await get_expert_knowledge(db, emotion)
    llm_report = await dashboard_report_chain.ainvoke({
        "emotion": emotion, "deltas": safe_context['deltas'], "app_usage": safe_context['app_usage'], "expert_knowledge": expert_knowledge
    })
    llm_report = llm_report.strip()
    llm_report = re.sub(r'\s*<br\s*/?>\s*', '\n', llm_report, flags=re.IGNORECASE)
    llm_report = re.sub(r'\n+', '<br><br>', llm_report)
    return llm_report