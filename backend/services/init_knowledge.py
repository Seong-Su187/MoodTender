# backend/services/init_knowledge.py
import asyncio
import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database import AsyncSessionLocal
from backend.models.domain import ActivityKnowledge
from backend.services.rag_chain import _embed # 임베딩 함수 재사용

load_dotenv()

# 📚 논문 기반 전문 지식 데이터 (필요시 계속 추가 가능)
KNOWLEDGE_DATA = [
    {
        "category": "우울",
        "title": "무기력 타개를 위한 행동 활성화 (Saeb et al., 2015)",
        "content": "신체 활동량이 급감하고 수면이 과다/부족한 무기력 상태일 때는 거창한 목표보다 '아주 작은 신체 움직임'이 효과적입니다. 5분간 창문 열고 환기하기, 따뜻한 물 한 잔 마시기, 집 앞 편의점까지 걸어가기 등 가벼운 행동 활성화(Behavioral Activation)가 우울감의 고리를 끊는 첫걸음이 됩니다."
    },
    {
        "category": "불안",
        "title": "수면 변동성과 과각성 안정화 (Cui et al., 2020)",
        "content": "수면 패턴이 불규칙하고 심야 스마트폰 확인 빈도가 높은 것은 뇌가 과각성(Hyper-arousal) 상태에 있다는 증거입니다. 시각적 자극(스크린)을 잠시 차단하고, 4-7-8 호흡법(4초 들이마시고, 7초 참고, 8초 내쉬기)을 하거나 캐모마일 같은 따뜻한 차를 마시며 부교감신경을 활성화하는 것이 좋습니다."
    },
    {
        "category": "지침",
        "title": "번아웃 시기의 경계선 긋기와 인지적 휴식 (Sahni et al., 2021)",
        "content": "활동량이 크게 줄고 폰 사용만 지속되는 번아웃 상태에서는 무언가를 '더' 하려 하기보다 '정지'하는 것이 필요합니다. 퇴근 후 스마트폰 알림을 1시간만 꺼두는 '디지털 디톡스'나, 조용한 음악을 들으며 시각적 입력을 차단하는 휴식이 뇌과학적으로 피로 회복에 가장 유리합니다."
    },
    {
        "category": "외로움",
        "title": "고립감 해소를 위한 약한 유대감 (Weak Ties) 형성",
        "content": "스마트폰 사용은 많으나 소셜 교류가 극히 적은 날에는 무기력한 고립감이 커질 수 있습니다. 무거운 고민 상담이 아니더라도, 오랜만에 친구에게 안부 메시지를 하나 보내거나 좋아하는 크리에이터의 영상에 다정한 댓글을 남기는 등 '가벼운 연결감'을 느끼는 행동이 정서 환기에 도움이 됩니다."
    }
]

async def seed_knowledge_base():
    """DB에 지식 베이스를 임베딩하여 삽입하는 함수"""
    async with AsyncSessionLocal() as db:
        for data in KNOWLEDGE_DATA:
            print(f"[{data['category']}] 임베딩 중...")
            # 1. 텍스트를 OpenAI 1536차원 벡터로 변환
            vec = await _embed(data["content"])
            
            # 2. DB 객체 생성
            new_knowledge = ActivityKnowledge(
                emotion_category=data["category"],
                title=data["title"],
                content=data["content"],
                embedding=vec
            )
            db.add(new_knowledge)
        
        await db.commit()
        print("✅ RAG 지식 베이스(Vector DB) 구축 완료!")

if __name__ == "__main__":
    asyncio.run(seed_knowledge_base())