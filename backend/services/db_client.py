import os

import asyncpg
from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = AsyncOpenAI(api_key=OPENAI_API_KEY)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536


async def get_conn():
    url = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    return await asyncpg.connect(url, statement_cache_size=0)


def to_vector_literal(values: list[float]) -> str:
    return "[" + ",".join(str(v) for v in values) + "]"


async def create_embedding(text: str) -> list[float]:
    if not text or not text.strip():
        text = "내용 없음"

    response = await client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
        dimensions=EMBEDDING_DIMENSIONS,
    )

    return response.data[0].embedding


# ==========================================
# 감정 사전 조회
# ==========================================
async def retrieve_emotion_dictionary(
    main_category: str,
    sub_category: str,
) -> dict | None:
    conn = await get_conn()
    try:
        row = await conn.fetchrow("""
            SELECT
                main_category,
                sub_category,
                situation_example,
                cocktail_direction,
                cocktail_color
            FROM emotion_dictionary
            WHERE main_category = $1
              AND sub_category = $2
            LIMIT 1
        """, main_category, sub_category)

        if row:
            return dict(row)

        row = await conn.fetchrow("""
            SELECT
                main_category,
                sub_category,
                situation_example,
                cocktail_direction,
                cocktail_color
            FROM emotion_dictionary
            WHERE main_category = $1
            LIMIT 1
        """, main_category)

        return dict(row) if row else None
    finally:
        await conn.close()


# ==========================================
# 유사 기억 검색 (RAG)
# ==========================================
async def retrieve_similar_user_memories(
    user_id: int,
    query_text: str,
    limit: int = 3,
) -> list[dict]:
    query_embedding = await create_embedding(query_text)
    query_vector = to_vector_literal(query_embedding)

    conn = await get_conn()
    try:
        rows = await conn.fetch("""
            SELECT
                id,
                memory_text,
                main_category,
                sub_category,
                emotion_intensity,
                created_at,
                embedding <=> $1::vector AS distance
            FROM user_memories
            WHERE user_id = $2
              AND embedding IS NOT NULL
            ORDER BY embedding <=> $1::vector
            LIMIT $3
        """, query_vector, user_id, limit)

        return [dict(row) for row in rows]
    finally:
        await conn.close()


# ==========================================
# 유사 대화 검색 (chat_messages)
# ==========================================
async def retrieve_similar_chat_messages(
    user_id: int,
    query_text: str,
    limit: int = 3,
) -> list[dict]:
    query_embedding = await create_embedding(query_text)
    query_vector = to_vector_literal(query_embedding)

    conn = await get_conn()
    try:
        rows = await conn.fetch("""
            SELECT
                id,
                role,
                content,
                created_at,
                embedding <=> $1::vector AS distance
            FROM chat_messages
            WHERE user_id = $2
              AND embedding IS NOT NULL
            ORDER BY embedding <=> $1::vector
            LIMIT $3
        """, query_vector, user_id, limit)

        return [dict(row) for row in rows]
    finally:
        await conn.close()

# ==========================================
# 기억 저장
# ==========================================
async def save_user_memory(
    user_id: int,
    memory_text: str,
    main_category: str,
    sub_category: str,
    emotion_intensity: int = 50,
) -> None:
    embedding = await create_embedding(memory_text)
    embedding_vector = to_vector_literal(embedding)

    conn = await get_conn()
    try:
        await conn.execute("""
            INSERT INTO user_memories (
                user_id,
                memory_text,
                embedding,
                main_category,
                sub_category,
                emotion_intensity
            ) VALUES ($1, $2, $3::vector, $4, $5, $6)
        """,
            user_id,
            memory_text,
            embedding_vector,
            main_category,
            sub_category,
            emotion_intensity,
        )
    finally:
        await conn.close()


# ==========================================
# 영수증 저장
# ==========================================
async def save_emotion_receipt(
    user_id: int,
    dominant_sub_category: str,
    recommended_cocktail: str,
    summary_note: str,
    weather: str | None = None,
) -> None:
    conn = await get_conn()
    try:
        await conn.execute("""
            INSERT INTO emotion_receipts (
                user_id,
                weather,
                dominant_sub_category,
                recommended_cocktail,
                summary_note
            ) VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (user_id, receipt_date)
            DO NOTHING
        """,
            user_id,
            weather,
            dominant_sub_category,
            recommended_cocktail,
            summary_note,
        )
    finally:
        await conn.close()

# ==========================================
# 대화 저장 (chat_messages)
# ==========================================
async def save_chat_message(
    user_id: int,
    role: str,
    content: str,
) -> None:
    embedding_vector = None

    if content and content.strip():
        embedding = await create_embedding(content)
        embedding_vector = to_vector_literal(embedding)

    conn = await get_conn()
    try:
        if embedding_vector:
            await conn.execute("""
                INSERT INTO chat_messages (
                    user_id,
                    role,
                    content,
                    embedding
                ) VALUES ($1, $2, $3, $4::vector)
            """, user_id, role, content, embedding_vector)
        else:
            await conn.execute("""
                INSERT INTO chat_messages (
                    user_id,
                    role,
                    content
                ) VALUES ($1, $2, $3)
            """, user_id, role, content)
    finally:
        await conn.close()