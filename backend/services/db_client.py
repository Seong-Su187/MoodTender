"""
db_client.py
SQLAlchemy AsyncSession 기반 DB 클라이언트
"""

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


def _vec(embedding: list[float]) -> str:
    return "[" + ",".join(str(x) for x in embedding) + "]"


def _to_dicts(result) -> list[dict]:
    keys = result.keys()
    return [dict(zip(keys, row)) for row in result.fetchall()]


async def search_user_memories(
    db: AsyncSession,
    user_id: int,
    query_embedding: list[float],
    top_k: int = 3,
) -> list[dict]:
    result = await db.execute(
        text("""
            SELECT
                id,
                memory_text,
                memory_type,
                importance,
                main_category,
                sub_category,
                source_type,
                source_id,
                created_at,
                1 - (embedding <=> CAST(:vec AS vector)) AS similarity
            FROM user_memories
            WHERE user_id = :user_id
              AND embedding IS NOT NULL
            ORDER BY embedding <=> CAST(:vec AS vector)
            LIMIT :top_k
        """),
        {
            "vec": _vec(query_embedding),
            "user_id": user_id,
            "top_k": top_k,
        },
    )
    return _to_dicts(result)


async def get_recent_chat_messages(
    db: AsyncSession,
    user_id: int,
    session_id: str,
    limit: int = 8,
) -> list[dict]:
    result = await db.execute(
        text("""
            SELECT id, role, content, created_at
            FROM chat_messages
            WHERE user_id = :user_id
                AND session_id = :session_id
            ORDER BY created_at DESC
            LIMIT :limit
        """),
        {"user_id": user_id, "session_id": session_id,"limit": limit},
    )
    rows = _to_dicts(result)
    return list(reversed(rows))


async def get_recent_health_metrics(
    db: AsyncSession,
    user_id: int,
    days: int = 7,
) -> list[dict]:
    result = await db.execute(
        text("""
            SELECT record_date, step_count, sleep_minutes,
                   screen_time_minutes, app_usage_json, depression_score
            FROM health_metrics
            WHERE user_id = :user_id
              AND record_date >= CURRENT_DATE - (:days || ' days')::interval
            ORDER BY record_date DESC
        """),
        {"user_id": user_id, "days": str(days)},
    )
    return _to_dicts(result)


async def get_emotion_dictionary(
    db: AsyncSession,
    main_category: Optional[str] = None,
) -> list[dict]:
    if main_category:
        result = await db.execute(
            text("""
                SELECT main_category, sub_category, situation_example,
                       cocktail_direction, cocktail_color
                FROM emotion_dictionary
                WHERE main_category = :main_category
            """),
            {"main_category": main_category},
        )
    else:
        result = await db.execute(
            text("""
                SELECT main_category, sub_category, situation_example,
                       cocktail_direction, cocktail_color
                FROM emotion_dictionary
            """)
        )
    return _to_dicts(result)


async def search_chat_messages(
    db: AsyncSession,
    user_id: int,
    query_embedding: list[float],
    session_id: str = "",
    top_k: int = 3,
) -> list[dict]:
    result = await db.execute(
        text("""
            SELECT role, content, created_at,
                   1 - (embedding <=> CAST(:vec AS vector)) AS similarity
            FROM chat_messages
            WHERE user_id = :user_id
              AND embedding IS NOT NULL
              AND session_id != :session_id
            ORDER BY embedding <=> CAST(:vec AS vector)
            LIMIT :top_k
        """),
        {
            "vec": _vec(query_embedding),
            "user_id": user_id,
            "session_id": session_id,
            "top_k": top_k,
        },
    )
    return _to_dicts(result)


async def save_chat_message(
    db: AsyncSession,
    user_id: int,
    role: str,
    content: str,
    embedding: Optional[list[float]] = None,
    session_id: Optional[str] = None,
) -> int:
    try:
        params = {"user_id": user_id, "role": role, "content": content, "session_id": session_id}

        if embedding is not None:
            params["vec"] = _vec(embedding)
            result = await db.execute(
                text("""
                    INSERT INTO chat_messages
                        (user_id, role, content, embedding, session_id)
                    VALUES
                        (:user_id, :role, :content, CAST(:vec AS vector), :session_id)
                    RETURNING id
                """),
                params,
            )
        else:
            result = await db.execute(
                text("""
                    INSERT INTO chat_messages
                        (user_id, role, content, session_id)
                    VALUES
                        (:user_id, :role, :content, :session_id)
                    RETURNING id
                """),
                params,
            )

        await db.commit()
        return result.scalar()

    except Exception as e:
        await db.rollback()
        print(f"[DB ERROR] save_chat_message: {e}")
        raise


async def save_user_memory(
    db: AsyncSession,
    user_id: int,
    memory_text: str,
    embedding: list[float],
    main_category: Optional[str],
    sub_category: Optional[str],
    emotion_intensity: int = 60,
    memory_type: str = "event",
    importance: int = 3,
    source_type: str = "chat",
    source_id: Optional[int] = None,
) -> int:
    try:
        result = await db.execute(
            text("""
                INSERT INTO user_memories
                    (user_id, memory_text, embedding, main_category, sub_category,
                     emotion_intensity, memory_type, importance, source_type, source_id)
                VALUES
                    (:user_id, :memory_text, CAST(:vec AS vector),
                     :main_category, :sub_category, :emotion_intensity,
                     :memory_type, :importance, :source_type, :source_id)
                RETURNING id
            """),
            {
                "user_id": user_id,
                "memory_text": memory_text,
                "vec": _vec(embedding),
                "main_category": main_category,
                "sub_category": sub_category,
                "emotion_intensity": emotion_intensity,
                "memory_type": memory_type,
                "importance": importance,
                "source_type": source_type,
                "source_id": source_id,
            },
        )
        await db.commit()
        return result.scalar()

    except Exception as e:
        await db.rollback()
        print(f"[DB ERROR] save_user_memory: {e}")
        raise


async def save_emotion_receipt(
    db: AsyncSession,
    user_id: int,
    dominant_sub_category: str,
    recommended_cocktail: str,
    summary_note: str,
    weather: Optional[str] = None,
) -> int:
    result = await db.execute(
        text("""
            INSERT INTO emotion_receipts
                (user_id, receipt_date, weather, dominant_sub_category,
                 recommended_cocktail, summary_note)
            VALUES
                (:user_id, (NOW() AT TIME ZONE 'Asia/Seoul')::date, :weather, :dominant_sub_category,
                 :recommended_cocktail, :summary_note)
            RETURNING id
        """),
        {
            "user_id": user_id,
            "weather": weather,
            "dominant_sub_category": dominant_sub_category,
            "recommended_cocktail": recommended_cocktail,
            "summary_note": summary_note,
        },
    )
    await db.commit()
    return result.scalar()