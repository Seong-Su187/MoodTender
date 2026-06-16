from pydantic import BaseModel
from datetime import date
from typing import Dict, Optional

# --- 기존 유저 및 인증 스키마 ---
class UserCreate(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str
    id: int

# --- 기존 LLM 및 대화 스키마 ---
class LLMRequest(BaseModel):
    text: str
    speed: float = 1.0
    session_id: str = ""

class LLMResponse(BaseModel):
    reply: str
    emotion: str = ""

class ChatRequest(BaseModel):
    user_id: int
    text: str

# --- 모바일 건강 데이터 스키마 ---
class HealthDataCreate(BaseModel):
    record_date: date               
    step_count: int                 
    sleep_minutes: int              
    screen_time_minutes: int        
    app_usage_json: Dict[str, int]

# --- 장기 기억 스키마 ---
class MemoryCreate(BaseModel):
    issue: str
    emotion: str

class MemoryResponse(MemoryCreate):
    id: int
    user_id: int
    status: str
    prescribed_cocktail: Optional[str] = None
    
    class Config:
        from_attributes = True

# --- 대시보드 칵테일 제조 API용 스키마 ---
class IssueResponse(BaseModel):
    id: int
    issue: str
    emotion: str
    record_date: date

class SuggestionRequest(BaseModel):
    issue_id: int

class SuggestionResponse(BaseModel):
    emotion_analysis: str
    checklist: list[str]

class CraftCocktailRequest(BaseModel):
    issue_id: int
    selected_actions: list[str]

class CraftCocktailResponse(BaseModel):
    expected_effect: str
    cocktail_name: str
    message: str

# 🚀 [추가됨] 칵테일 맛 평가(리뷰) 제출용 스키마
class ReviewRequest(BaseModel):
    issue_id: int
    taste_rating: int
    user_review: str