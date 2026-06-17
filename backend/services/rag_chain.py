"""
rag_chain.py - MoodTender RAG 서비스 전체 코드 (생략 없음)
"""
import os
import re
import json
import asyncio
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.output_parsers import StrOutputParser

from backend.models.domain import UserMemory
from backend.services.db_client import (
    search_user_memories, search_chat_messages, get_recent_chat_messages,
    get_recent_health_metrics, get_emotion_dictionary, save_chat_message,
    save_emotion_receipt, get_expert_knowledge, 
)
from backend.services.analytics_service import extract_memory_from_chat 
from backend.services.anonymizer import DataAnonymizer

load_dotenv()

# OpenAI 설정
_embeddings = OpenAIEmbeddings(model="text-embedding-3-small", openai_api_key=os.getenv("OPENAI_API_KEY"))

def _make_llm(temperature: float = 0.7, model: str = "gpt-4.1-mini") -> ChatOpenAI:
    return ChatOpenAI(model=model, temperature=temperature, openai_api_key=os.getenv("OPENAI_API_KEY"))

async def _embed(text: str) -> list[float]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: _embeddings.embed_query(text))

_SPEED_RANGE = {
    1.2: (160, 180),
    1.0: (140, 160),
    0.8: (110, 130),
}

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
            result += sentence + " "
        else:
            break

    return result.strip() or text[:limit]

def _deidentify(text: str) -> str:
    patterns = [(re.compile(r'01[016789]-?\d{3,4}-?\d{4}'), '[전화번호]'),
                (re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+'), '[이메일]'),
                (re.compile(r'\d{6}-[1-4]\d{6}'), '[주민번호]')]
    for p, r in patterns: text = p.sub(r, text)
    return text

def _build_memory_context(memories: list[dict]) -> str:
    if not memories: return "관련 기억 없음"
    lines = []
    for m in memories[:3]:
        date_str = m.get('created_at')
        if hasattr(date_str, 'strftime'):
            date_str = date_str.strftime('%Y-%m-%d')
        elif not date_str:
            date_str = '알 수 없음'
        lines.append(f"- 날짜: {date_str}, 내용: {m.get('memory_text', '')}")
    return "\n".join(lines)

def _build_history(chats: list[dict]) -> list:
    history = []
    for chat in chats:
        if chat["role"] == "user": history.append(HumanMessage(content=chat["content"]))
        elif chat["role"] == "assistant": history.append(AIMessage(content=chat["content"]))
    return history

def _build_past_chat_context(chats: list[dict]) -> str:
    return "\n".join(f"- {c['content']}" for c in chats)

_MAIN_EMOTIONS = frozenset({"기쁨", "우울", "불안", "분노", "지침", "외로움", "평온"})

async def _classify_emotion(user_text: str) -> str:
    result = await classify_chain.ainvoke([
        HumanMessage(content=(
            "다음 발화에서 사용자의 감정을 아래 7가지 중 하나만 골라 단어만 답해라.\n"
            "- 기쁨: 설렘, 성취감, 즐거움\n"
            "- 우울: 무기력함, 슬픔, 의욕 없음, 기분 저조\n"
            "- 불안: 걱정, 두려움, 초조함\n"
            "- 분노: 짜증, 화남, 억울함\n"
            "- 지침: 피로, 번아웃, 몸과 마음의 소진\n"
            "- 외로움: 혼자라는 느낌, 누군가 그리움, 연결 부재, 소외감\n"
            "- 평온: 안정, 차분함, 별다른 감정 없음\n\n"
            f"발화: {user_text}"
        ))
    ])
    emotion = result.content.strip()
    return emotion if emotion in _MAIN_EMOTIONS else "평온"

async def _build_cocktail_hint(db: AsyncSession, recommend: bool, emotion: str = "평온") -> str:
    if not recommend:
        return "대화"
    entries = await get_emotion_dictionary(db, emotion)
    if not entries:
        entries = await get_emotion_dictionary(db)
    if not entries:
        return "추천"
    db_lines = "\n".join(
        f"- {e['sub_category']}: {e['cocktail_direction']} / 색상: {e['cocktail_color']}"
        for e in entries
    )
    return (
        f"추천 - 손님의 감정({emotion})과 상황을 참고해 아래 [감정-칵테일 DB]에서 "
        "가장 어울리는 방향성과 색상을 반드시 반영해 창의적인 칵테일 이름을 지어 추천하라. "
        "대화 문장 안에서 자연스럽게 칵테일을 제안하되, 시스템 처리를 위해 응답의 제일 마지막 줄에 단독으로 [칵테일: 칵테일이름] 태그를 반드시 추가하라.\n"
        f"[감정-칵테일 DB ({emotion})]\n{db_lines}"
    )

# 체인 및 프롬프트 정의
bartender_prompt = ChatPromptTemplate.from_messages([
    ("system", """
    너는 MoodTender, 따뜻하고 전문적인 AI 바텐더다.
    [손님 관련 기억] {memory_context}
    [관련 과거 대화] {past_chat_context}
    
    [규칙]
    1. 손님이 "기억나?", "그때 어땠어?", "무슨 일 있었지?" 등 과거를 물어보는데 날짜나 시간대가 명시되지 않았다면, 
       절대 추측하지 마라. 대신 "언제 있었던 일을 말씀하시는 건가요? 오늘, 어제, 아니면 다른 날인가요?"라고 친절하게 되물어라.
    2. 손님이 날짜를 말하면 [손님 관련 기억]에서 해당 날짜를 찾아 사건과 감정을 상세히 말하며 공감해라.
    3. [지시]가 '추천'일 때만 칵테일 이름을 언급하며 추천하라. [지시]가 '대화'이면 손님이 칵테일을 달라고 요구해도, 아직 때가 아니라며 자연스럽게 대화를 유도하고 절대 칵테일 이름을 지어내거나 언급하지 마라.
    4. "기록에 따르면" 같은 기계적인 표현은 쓰지 않는다.
    5. 한 번에 하나의 질문만 한다.
    6. 답변은 2~3문장, 150자 이내로 간결하게 한다. 불필요한 부연 설명을 넣지 마라.
    """),
    MessagesPlaceholder(variable_name="history"),
    ("human", "{user_input}\n\n[지시] {cocktail_hint}"),
])

bartender_chain = bartender_prompt | _make_llm(0.7, "gpt-4.1") | StrOutputParser()
classify_chain = _make_llm(0.0)
memory_summary_chain = ChatPromptTemplate.from_messages([("system", "대화 요약"), ("human", "{conversation_text}")]) | _make_llm(0.2) | StrOutputParser()

receipt_chain = ChatPromptTemplate.from_messages([
    ("system", "대화를 분석해 오늘의 감정, 주요 원인, 스스로 잘 버텨낸 점, 추천하는 칵테일의 의미, 그리고 따뜻한 위로를 각각 1문장씩 총 5문장으로 작성한다."),
    ("human", "감정: {emotion}\n세부감정: {sub_emotion}\n칵테일: {cocktail}\n대화:\n{conversation_text}")
]) | _make_llm(0.3) | StrOutputParser()

cocktail_chain = _make_llm(0.7, "gpt-4.1-mini")
sub_classify_chain = _make_llm(0.0, "gpt-4.1-mini")
deidentify_chain = _make_llm(0.0)

# CHAINS 정의
CHAINS = (classify_chain, bartender_chain, memory_summary_chain, _make_llm(0.0), receipt_chain, cocktail_chain, sub_classify_chain, deidentify_chain)

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
]) | _make_llm(temperature=0.5, model="gpt-4.1-mini") | StrOutputParser()

weekly_receipt_report_chain = ChatPromptTemplate.from_messages([
    ("system", """
    당신은 10년 차 전문 바텐더 'MoodTender'입니다.
    사용자가 최근 일주일간 작성한 감정 영수증과 생활 데이터를 바탕으로
    웹 대시보드에 띄울 '주간 상태 분석 리포트'를 작성해 주세요.

    [이번 주 감정 영수증 요약]
    주요 감정: {emotion}
    최근 영수증 메모: {notes}
    가장 많이 추천된 칵테일: {top_cocktail}

    [생활 데이터 — 보조 참고용, 감정 판단의 근거가 아니라 맥락으로만 가볍게 언급]
    {health_context}

    [전문 지식 및 근거 (RAG)]
    {expert_knowledge}

    [작성 규칙]
    1. 따뜻하고 정중하며 통찰력 있는 톤을 유지하세요.
    2. 감정 영수증 메모에 드러난 흐름을 중심으로 분석하고, 생활 데이터는 보조적인 맥락으로만 자연스럽게 녹여 언급하세요.
    3. 전문 지식을 참고하여 일상에서 할 수 있는 작은 행동을 제안하세요.
    4. 마지막엔 이 감정에 어울리는 가상의 칵테일 한 잔을 추천하세요.
    5. <b>, <br> 등 HTML 태그를 적극 사용하여 3~4문단으로 작성하세요.
    """)
]) | _make_llm(temperature=0.5, model="gpt-4.1-mini") | StrOutputParser()

async def generate_weekly_report_from_receipts(db: AsyncSession, receipt_summary: dict, health_context: str) -> dict:
    from backend.services.monthly_service import _get_main_emotion

    main_emotion = await _get_main_emotion(db, receipt_summary["dominant_sub"])
    expert_knowledge = await get_expert_knowledge(db, main_emotion)
    notes_text = " / ".join(receipt_summary["notes"][-5:]) if receipt_summary["notes"] else "기록된 메모 없음"

    llm_report = await weekly_receipt_report_chain.ainvoke({
        "emotion": main_emotion,
        "notes": notes_text,
        "top_cocktail": receipt_summary["top_cocktail"] or "아직 없음",
        "health_context": health_context,
        "expert_knowledge": expert_knowledge,
    })

    llm_report = llm_report.strip()
    llm_report = re.sub(r'\s*<br\s*/?>\s*', '\n', llm_report, flags=re.IGNORECASE)
    llm_report = re.sub(r'\n+', '<br><br>', llm_report)
    return {"status": "success", "html": llm_report}

async def rag_chat(db: AsyncSession, user_id: int, user_text: str, speed: float = 1.0, session_id: str = "", session_start=None, cocktail_done: bool = False, user_turn_count: int = 0) -> tuple[str, str, str]:
    user_text = _deidentify(user_text)
    
    clean_user_text = user_text
    if "사용자 발화:" in user_text:
        match = re.search(r'사용자 발화:\s*(.*?)(?=\s*감정 분석:|$)', user_text, re.DOTALL)
        if match:
            clean_user_text = match.group(1).strip()
            
    query_embedding = await _embed(clean_user_text)
    
    memories, chats, past_chats = await asyncio.gather(
        search_user_memories(db, user_id, query_embedding, top_k=3),
        get_recent_chat_messages(db, user_id, session_id=session_id, limit=24),
        search_chat_messages(db, user_id, query_embedding, session_id=session_id, session_start=session_start, top_k=3),
    )
    
    past_keywords = ["기억", "저번", "지난번", "예전", "전에", "어제", "그저께", "언제"]
    is_asking_past = any(k in clean_user_text for k in past_keywords)
    
    cocktail_request = any(k in clean_user_text for k in ["칵테일", "추천", "한잔", "한 잔", "메뉴", "술", "줘"])
    
    # 🚀 [버그 해결] 이미 추천을 받았어도 "다른", "다시" 등의 키워드로 재요청하면 칵테일 추천 모드를 다시 켭니다!
    re_request_keywords = ["다른", "다시", "바꿔", "별로", "새로운", "딴거", "딴 거", "아닌", "다르게"]
    is_re_request = cocktail_request and any(k in clean_user_text for k in re_request_keywords)
    
    should_recommend = (cocktail_request and not is_asking_past and not cocktail_done) or is_re_request
    
    recent_user_msgs = " / ".join(
        c["content"] for c in chats[-6:] if c["role"] == "user"
    )
    classify_input = f"{recent_user_msgs} / {clean_user_text}".strip(" /")
    main_emotion = await _classify_emotion(classify_input)
    cocktail_hint = await _build_cocktail_hint(db, should_recommend, main_emotion)

    raw_reply = await bartender_chain.ainvoke({
        "memory_context": _build_memory_context(memories),
        "past_chat_context": _build_past_chat_context(past_chats),
        "history": _build_history(chats),
        "user_input": clean_user_text,
        "cocktail_hint": cocktail_hint
    })

    extracted_cocktail = "오늘의 칵테일"
    if should_recommend:
        cocktail_match = re.search(r'\[칵테일:\s*([^\]]+)\]', raw_reply)
        if cocktail_match:
            extracted_cocktail = cocktail_match.group(1).strip()
            raw_reply = re.sub(r'\[칵테일:\s*[^\]]+\]', '', raw_reply).strip()

    reply = _trim(raw_reply, speed)

    user_message_id = await save_chat_message(db, user_id, "user", clean_user_text, query_embedding, session_id)
    await save_chat_message(db, user_id, "assistant", reply, await _embed(reply), session_id)

    await save_memory_if_needed(db, user_id, clean_user_text, reply, main_emotion, user_message_id)

    return reply, main_emotion, (extracted_cocktail if should_recommend else "")

async def save_receipt(db, user_id, emotion, sub_emotion, cocktail, conversation_text, receipt_chain) -> None:
    try:
        emotion = emotion or "평온"
        sub_emotion = sub_emotion or "평온"
        cocktail = cocktail or "당신을 위한 따뜻한 위로 한 잔"
        conversation_text = conversation_text or "오늘 하루도 정말 고생 많으셨습니다."
        
        note = await receipt_chain.ainvoke({
            "emotion": emotion, 
            "sub_emotion": sub_emotion, 
            "cocktail": cocktail, 
            "conversation_text": conversation_text
        })
        
        await save_emotion_receipt(db=db, user_id=user_id, dominant_sub_category=sub_emotion, recommended_cocktail=cocktail, summary_note=note.strip())
        await db.commit()
        
    except Exception as e:
        print(f"Receipt save error: {e}")

async def save_memory_if_needed(db, user_id, user_text, assistant_reply, emotion, user_message_id) -> None:
    try:
        conv = f"사용자: {user_text}\n바텐더: {assistant_reply}"
        summary = await memory_summary_chain.ainvoke({"conversation_text": conv})
        if not summary or summary.strip().upper() == "NONE": return
        
        extracted = await extract_memory_from_chat(conv)
        new_issue = extracted.get("issue")
        
        if new_issue == "없음": 
            return

        existing_stmt = select(UserMemory).where(
            UserMemory.user_id == user_id,
            UserMemory.status == "PENDING",
            UserMemory.prescribed_cocktail == None
        ).order_by(UserMemory.created_at.desc()).limit(1)
        
        existing_res = await db.execute(existing_stmt)
        existing_m = existing_res.scalar_one_or_none()

        if existing_m:
            existing_m.memory_text += f" / {summary.strip()}"
            existing_m.issue = new_issue
            await db.commit()
        else:
            new_memory = UserMemory(
                user_id=user_id, memory_text=summary.strip(), embedding=await _embed(summary),
                main_category=emotion, sub_category=extracted.get("emotion"),
                memory_type="event", importance=3, source_type="chat", 
                source_id=user_message_id, issue=new_issue, status="PENDING"
            )
            db.add(new_memory)
            await db.commit()
            
    except Exception as e:
        print(f"Memory save error: {e}")
        await db.rollback()

async def generate_dashboard_rag_report(db: AsyncSession, user_id: int, metrics_result: dict) -> dict:
    if metrics_result.get("status") == "insufficient_data":
        return {
            "status": "insufficient_data",
            "html": "💡 <b>데이터 수집 중</b><br><br>정확한 패턴 분석을 위해서는 최소 3일 이상의 데이터가 필요합니다.",
        }

    safe_context = DataAnonymizer.prepare_safe_context(user_id, metrics_result)
    emotion = safe_context['emotion']
    expert_knowledge = await get_expert_knowledge(db, emotion)

    llm_report = await dashboard_report_chain.ainvoke({
        "emotion": emotion,
        "deltas": safe_context['deltas'],
        "app_usage": safe_context['app_usage'],
        "expert_knowledge": expert_knowledge
    })

    llm_report = llm_report.strip()
    llm_report = re.sub(r'\s*<br\s*/?>\s*', '\n', llm_report, flags=re.IGNORECASE)
    llm_report = re.sub(r'\n+', '<br><br>', llm_report)
    return {"status": "success", "html": llm_report}