"""
rag_chain.py - MoodTender RAG 서비스 전체 코드
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

load_dotenv()

# LLM 생성 함수 (순환 참조 방지를 위해 여기 정의)
def _make_llm(temperature=0.7, model="gpt-4o-mini"):
    return ChatOpenAI(model=model, temperature=temperature, openai_api_key=os.getenv("OPENAI_API_KEY"))

_embeddings = OpenAIEmbeddings(model="text-embedding-3-small", openai_api_key=os.getenv("OPENAI_API_KEY"))

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
    return "\n".join(f"- 날짜: {m.created_at.strftime('%Y-%m-%d') if hasattr(m, 'created_at') else '알 수 없음'}, 내용: {m.memory_text}" for m in memories[:3]) if memories else "관련 기억 없음"

def _build_history(chats: list[dict]) -> list:
    history = []
    for chat in chats:
        if chat["role"] == "user": history.append(HumanMessage(content=chat["content"]))
        elif chat["role"] == "assistant": history.append(AIMessage(content=chat["content"]))
    return history

def build_chains():
    bartender_chain = ChatPromptTemplate.from_messages([
        ("system", """
        너는 MoodTender, 따뜻한 AI 바텐더다.
        [손님 관련 기억] {memory_context}
        [관련 과거 대화] {past_chat_context}
        
        규칙:
        1. 손님이 과거의 일을 물어보는데 날짜나 시간대가 명시되지 않았다면, 추측하지 말고 즉시 되물어라.
           - "언제 있었던 일을 말씀하시는 건가요? 오늘, 어제, 아니면 다른 날인가요?"
        2. 손님이 날짜를 말하면 [손님 관련 기억]에서 해당 날짜를 확인하여 정확하게 공감해라.
        3. 칵테일 추천 요청(술, 추천, 한잔 등)이 확실할 때만 칵테일을 추천하라.
        4. 한 번에 하나의 질문만 한다.
        """),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{user_input}\n\n[지시] {cocktail_hint}"),
    ]) | _make_llm(0.7, "gpt-4.1") | StrOutputParser()
    
    return bartender_chain, _make_llm(0.0), _make_llm(0.2), _make_llm(0.3), _make_llm(0.7, "gpt-4.1-mini"), _make_llm(0.0), _make_llm(0.0, "gpt-4.1-mini")

bartender_chain, classify_chain, memory_summary_chain, receipt_chain, cocktail_chain, sub_classify_chain, deidentify_chain = build_chains()

async def rag_chat(db, user_id, user_text, speed=1.0, session_id="", session_start=None, cocktail_done=False, user_turn_count=0) -> tuple[str, str, str]:
    user_text = _deidentify(await deidentify_chain.ainvoke({"user_input": user_text}))
    query_embedding = await _embed(user_text)
    
    memories, chats, past_chats = await asyncio.gather(
        search_user_memories(db, user_id, query_embedding, top_k=3),
        get_recent_chat_messages(db, user_id, session_id=session_id, limit=24),
        search_chat_messages(db, user_id, query_embedding, session_id=session_id, session_start=session_start, top_k=3),
    )
    
    # 과거 확인 로직
    past_keywords = ["기억", "저번", "지난번", "예전", "전에", "어제", "그저께", "언제"]
    is_asking_past = any(k in user_text for k in past_keywords)
    cocktail_request = any(k in user_text for k in ["칵테일", "추천", "한잔", "한 잔", "메뉴", "술", "줘"])
    
    # 🚀 사용자가 과거를 묻고 있다면, 추천 모드를 무조건 OFF
    should_recommend = (user_turn_count >= 3 or (cocktail_request and not is_asking_past)) and not cocktail_done
    
    raw_reply = await bartender_chain.ainvoke({
        "memory_context": _build_memory_context(memories),
        "past_chat_context": "\n".join(f"- {c['content']}" for c in past_chats),
        "history": _build_history(chats),
        "user_input": user_text,
        "cocktail_hint": "추천" if should_recommend else "대화"
    })
    
    reply = _trim(raw_reply, speed)
    
    user_message_id = await save_chat_message(db, user_id, "user", user_text, query_embedding, session_id)
    await save_chat_message(db, user_id, "assistant", reply, await _embed(reply), session_id)
    
    await save_memory_if_needed(db, user_id, user_text, reply, "평온", user_message_id)
    
    return reply, "평온", ("오늘의 칵테일" if should_recommend else "")

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

async def save_receipt(db, user_id, emotion, sub_emotion, cocktail, conversation_text, receipt_chain) -> None:
    try:
        note = await receipt_chain.ainvoke({"emotion": emotion, "sub_emotion": sub_emotion, "cocktail": cocktail, "conversation_text": conversation_text})
        await save_emotion_receipt(db=db, user_id=user_id, dominant_sub_category=sub_emotion, recommended_cocktail=cocktail, summary_note=note.strip())
    except Exception as e:
        print(f"Receipt save error: {e}")