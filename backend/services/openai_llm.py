from pathlib import Path
import re
from openai import AsyncOpenAI, OpenAIError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc

# 기존 설정값 유지
from backend.config import OPENAI_API_KEY, OPENAI_MODEL
from backend.models.domain import ChatMessage, UserMemory, EmotionDictionary

# --- 기존 프롬프트 설정 유지 ---
BASE_DIR = Path(__file__).resolve().parents[2]
AGENT_PROMPT_PATHS = (BASE_DIR / "agent_ko.md", BASE_DIR / "agent.md")

def _load_agent_prompt() -> str:
    for path in AGENT_PROMPT_PATHS:
        if path.exists():
            prompt = path.read_text(encoding="utf-8").strip()
            if prompt:
                return prompt
    return DEFAULT_SYSTEM_PROMPT

DEFAULT_SYSTEM_PROMPT = """너는 MoodTender다. 사용자의 지친 마음을 위로하는 따뜻한 한국어 AI 바텐더다."""
ENDPOINT_SYSTEM_PROMPT = """
[필수 규칙]
1. 채팅 설명문이 아니라 바로 말하는 대사다.
2. 전체 응답 길이는 아래 [속도별 답변 길이] 범위를 따른다.
3. 마크다운, 따옴표, 이모지, 무대 지시문은 쓰지 않는다.
4. 사용자가 쓴 밈은 설명하지 말고 감정만 먼저 받아준다.
5. 사용자가 반말이나 비속어를 써도 바텐더는 항상 존댓말로 답한다.
6. 사용자의 반말, 비속어, 거친 표현을 따라 하지 않는다.
"""
REPLY_LENGTH_BY_SPEED = {
    1.2: (58, 62),
    1.0: (48, 52),
    0.8: (38, 42),
}

# --- 로직 함수들 ---

def _reply_length_range(speed: float) -> tuple[float, int, int]:
    selected_speed = min(REPLY_LENGTH_BY_SPEED, key=lambda value: abs(value - speed))
    min_chars, max_chars = REPLY_LENGTH_BY_SPEED[selected_speed]
    return selected_speed, min_chars, max_chars

def _compose_system_prompt(prompt: str, context: str = "", cocktail_info: str = "", speed: float = 1.0) -> str:
    """프롬프트를 조합하여 시스템 메시지 생성"""
    selected_speed, min_chars, max_chars = _reply_length_range(speed)
    length_prompt = (
        "[속도별 답변 길이]\n"
        "1.2배속: 전체 응답을 58~62자로 쓴다.\n"
        "1.0배속: 전체 응답을 48~52자로 쓴다.\n"
        "0.8배속: 전체 응답을 38~42자로 쓴다.\n"
        f"현재 선택된 속도는 {selected_speed:.1f}배속이다.\n"
        f"이번 답변은 공백과 문장부호를 포함해 {min_chars}~{max_chars}자로 맞춘다."
    )
    base = f"{prompt.strip()}\n\n[과거 기억 및 대화 맥락]\n{context}\n\n[추천 칵테일 정보]\n{cocktail_info}\n\n{ENDPOINT_SYSTEM_PROMPT.strip()}\n\n{length_prompt}"
    return base

# [기존 helper 유지]
def _clean_reply(reply: str) -> str:
    reply = reply.strip()
    reply = re.sub(r"^[\s>*#\-•\d.]+", "", reply)
    reply = re.sub(r"\s{2,}", " ", reply)
    reply = reply.replace('"', "").replace("'", "")
    return reply.strip()

def _limit_reply_sentences(reply: str, user_text: str) -> str:
    max_sentences = 3 if any(w in user_text for w in ["죽고", "사라지고", "끝내고"]) else 2
    sentences = re.findall(r"[^.!?。！？]+[.!?。！？]?", reply)
    sentences = [s.strip() for s in sentences if s.strip()]
    return " ".join(sentences[:max_sentences]) if len(sentences) > max_sentences else reply

# --- DB 연동 및 RAG 로직 추가 ---

async def _get_chat_history(db: AsyncSession, user_id: int) -> str:
    """최근 대화 10개를 불러와 텍스트로 변환"""
    stmt = select(ChatMessage).where(ChatMessage.user_id == user_id).order_by(desc(ChatMessage.created_at)).limit(10)
    result = await db.execute(stmt)
    history = result.scalars().all()[::-1]
    return "\n".join([f"{m.role}: {m.content}" for m in history])

async def _get_emotion_category(client: AsyncOpenAI, history: str) -> str:
    """대화 맥락을 읽고 감정 카테고리 추출"""
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": "대화 맥락을 분석해 감정 카테고리 하나만 말해. [기쁨, 우울, 불안, 분노, 지침, 외로움, 평온]"},
                  {"role": "user", "content": history}]
    )
    return response.choices[0].message.content.strip()

async def _get_cocktail_data(db: AsyncSession, category: str) -> str:
    """DB에서 감정별 칵테일 정보 조회"""
    stmt = select(EmotionDictionary).where(EmotionDictionary.main_category == category)
    result = await db.execute(stmt)
    data = result.scalars().first()
    return f"색상: {data.cocktail_color}, 방향: {data.cocktail_direction}" if data else "일반적인 칵테일"

# --- 메인 실행 함수 ---

async def generate_bartender_reply(user_id: int, user_text: str, db: AsyncSession, speed: float = 1.0, db_text: str | None = None) -> tuple[str, str]:
    text = user_text.strip()
    if not text: return "...", "평온"

    client = AsyncOpenAI(api_key=OPENAI_API_KEY)

    # 1. DB에 유저 말 저장 (LLM에 보내는 텍스트와 저장용 텍스트가 다르면 db_text 사용)
    saved_text = (db_text or text).strip()
    db.add(ChatMessage(user_id=user_id, role="user", content=saved_text))
    await db.commit()

    # 2. 컨텍스트 빌드
    history = await _get_chat_history(db, user_id)
    emotion_cat = await _get_emotion_category(client, history)
    cocktail_info = await _get_cocktail_data(db, emotion_cat)

    # 3. 프롬프트 구성
    agent_prompt = _load_agent_prompt()
    sys_prompt = _compose_system_prompt(agent_prompt, history, cocktail_info, speed)

    try:
        response = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "system", "content": sys_prompt}, {"role": "user", "content": text}]
        )
    except OpenAIError:
        return "조금 쉬고 싶으신가요? 제가 곁에 있을게요.", emotion_cat

    reply = _clean_reply(response.choices[0].message.content or "")
    reply = _limit_reply_sentences(reply, text)

    # 4. 바텐더 말 저장
    db.add(ChatMessage(user_id=user_id, role="assistant", content=reply))
    await db.commit()

    return reply, emotion_cat
