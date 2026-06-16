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

def _make_llm(temperature=0.7, model="gpt-4o-mini"):
    return ChatOpenAI(model=model, temperature=temperature, openai_api_key=os.getenv("OPENAI_API_KEY"))

async def _embed(text: str) -> list[float]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: _embeddings.embed_query(text))

def _trim(text: str, speed: float) -> str:
    limit = 50 
    text = text.strip()
    return text[:limit] if len(text) > limit else text

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

def build_chains():
    bartender_chain = ChatPromptTemplate.from_messages([
        ("system", """
        너는 MoodTender, 따뜻하고 전문적인 AI 바텐더다.
        [손님 관련 기억] {memory_context}
        [관련 과거 대화] {past_chat_context}
        
        [규칙]
        1. 손님이 "기억나?", "그때 어땠어?", "무슨 일 있었지?" 등 과거를 물어보는데 날짜나 시간대가 명시되지 않았다면, 
           절대 추측하지 마라. 대신 "언제 있었던 일을 말씀하시는 건가요? 오늘, 어제, 아니면 다른 날인가요?"라고 친절하게 되물어라.
        2. 손님이 날짜를 말하면 [손님 관련 기억]에서 해당 날짜를 찾아 사건과 감정을 상세히 말하며 공감해라.
        3. 칵테일 추천 요청(술, 추천, 한잔 등)이 확실할 때만 추천 모드를 켜라. 과거를 묻는 도중에는 추천하지 마라.
        4. "기록에 따르면" 같은 기계적인 표현은 쓰지 않는다.
        5. 한 번에 하나의 질문만 한다.
        """),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{user_input}\n\n[지시] {cocktail_hint}"),
    ]) | _make_llm(0.7, "gpt-4.1") | StrOutputParser()
    
    return bartender_chain, _make_llm(0.0), _make_llm(0.2), _make_llm(0.3), _make_llm(0.7, "gpt-4.1-mini"), _make_llm(0.0), _make_llm(0.0, "gpt-4.1-mini")

bartender_chain, classify_chain, memory_summary_chain, receipt_chain, cocktail_chain, sub_classify_chain, deidentify_chain = build_chains()
CHAINS = (classify_chain, bartender_chain, memory_summary_chain, _make_llm(0.0), receipt_chain, cocktail_chain, sub_classify_chain, deidentify_chain)

# 🚀 대시보드 리포트 생성 체인 복구
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


async def rag_chat(db: AsyncSession, user_id: int, user_text: str, speed: float = 1.0, session_id: str = "", session_start=None, cocktail_done: bool = False, user_turn_count: int = 0) -> tuple[str, str, str]:
    user_text = _deidentify(user_text)
    
    # 🚀 [버그 해결] llm.py에서 감정 분석 데이터가 섞여 들어오는 것을 싹둑 잘라냅니다.
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
    
    should_recommend = (user_turn_count >= 3 or (cocktail_request and not is_asking_past)) and not cocktail_done
    
    raw_reply = await bartender_chain.ainvoke({
        "memory_context": _build_memory_context(memories),
        "past_chat_context": _build_past_chat_context(past_chats),
        "history": _build_history(chats),
        "user_input": clean_user_text,
        "cocktail_hint": "추천" if should_recommend else "대화"
    })
    
    reply = _trim(raw_reply, speed)
    
    # 🚀 오염되지 않은 깔끔한 텍스트(clean_user_text)만 DB에 저장합니다.
    user_message_id = await save_chat_message(db, user_id, "user", clean_user_text, query_embedding, session_id)
    await save_chat_message(db, user_id, "assistant", reply, await _embed(reply), session_id)
    
    await save_memory_if_needed(db, user_id, clean_user_text, reply, "평온", user_message_id)
    
    return reply, "평온", ("오늘의 칵테일" if should_recommend else "")

async def save_receipt(db, user_id, emotion, sub_emotion, cocktail, conversation_text, receipt_chain) -> None:
    try:
        note = await receipt_chain.ainvoke({"emotion": emotion, "sub_emotion": sub_emotion, "cocktail": cocktail, "conversation_text": conversation_text})
        await save_emotion_receipt(db=db, user_id=user_id, dominant_sub_category=sub_emotion, recommended_cocktail=cocktail, summary_note=note.strip())
    except Exception as e:
        print(f"Receipt save error: {e}")

async def save_memory_if_needed(db, user_id, user_text, assistant_reply, emotion, user_message_id) -> None:
    try:
        conv = f"사용자: {user_text}\n바텐더: {assistant_reply}"
        summary = await memory_summary_chain.ainvoke({"conversation_text": conv})
        if not summary or summary.strip().upper() == "NONE": return
        
        extracted = await extract_memory_from_chat(conv)
        new_memory = UserMemory(
            user_id=user_id, memory_text=summary.strip(), embedding=await _embed(summary),
            main_category=emotion, sub_category=extracted.get("emotion"),
            memory_type="event", importance=3, source_type="chat", 
            source_id=user_message_id, issue=extracted.get("issue") if extracted.get("issue") != "없음" else None,
            status="PENDING" if extracted.get("issue") != "없음" else None
        )
        db.add(new_memory)
        await db.commit()
    except Exception as e:
        print(f"Memory save error: {e}")
        await db.rollback()

# 🚀 [버그 해결] 비어있던 대시보드 리포트 생성 함수를 복구했습니다.
async def generate_dashboard_rag_report(db: AsyncSession, user_id: int, metrics_result: dict) -> str:
    if metrics_result.get("status") == "insufficient_data":
        return "💡 <b>데이터 수집 중</b><br><br>정확한 패턴 분석을 위해서는 최소 3일 이상의 데이터가 필요합니다."
    
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
    return llm_report