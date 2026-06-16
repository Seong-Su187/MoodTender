from pydantic import BaseModel
from datetime import date
from typing import Dict, Optional

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

class HealthDataCreate(BaseModel):
    record_date: date               
    step_count: int                 
    sleep_minutes: int              
    screen_time_minutes: int        
    app_usage_json: Dict[str, int]

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

class IssueResponse(BaseModel):
    id: int
    issue: str
    emotion: str
    record_date: date
    # 🚀 [추가됨] 이 고민이 처방을 받은 상태인지 확인하기 위한 필드
    prescribed_cocktail: Optional[str] = None

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

class ReviewRequest(BaseModel):
    issue_id: int
    taste_rating: int
    user_review: str