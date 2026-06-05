from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from datetime import datetime

from database import get_db
from models.domain import User
from models.schemas import UserCreate, Token
from services.security import hash_pw, verify_pw, create_access_token, block_token, is_token_blocked
from config import SECRET_KEY, ALGORITHM

router = APIRouter()

def get_current_user_token(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="토큰이 없습니다.")
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        jti = payload.get("jti")
        if is_token_blocked(jti):
            raise HTTPException(status_code=401, detail="로그아웃된 토큰입니다.")
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")

@router.post("/signup")
def signup(user: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == user.username).first():
        raise HTTPException(status_code=400, detail="이미 존재하는 아이디입니다.")
    new_user = User(username=user.username, hashed_password=hash_pw(user.password))
    db.add(new_user); db.commit(); db.refresh(new_user)
    return {"id": new_user.id, "username": new_user.username}

@router.post("/login", response_model=Token)
def login(user: UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.username == user.username).first()
    if not db_user or not verify_pw(user.password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 틀렸습니다.")
    token_data = create_access_token(db_user.username)
    return {"access_token": token_data["access_token"], "token_type": token_data["token_type"]}

@router.post("/logout")
def logout(token_payload: dict = Depends(get_current_user_token)):
    jti = token_payload.get("jti")
    exp = token_payload.get("exp")
    now = int(datetime.utcnow().timestamp())
    expires_in = max(exp - now, 0)
    if expires_in > 0:
        block_token(jti, expires_in)
    return {"message": "성공적으로 로그아웃 되었습니다."}

@router.get("/check-username")
def check_username(username: str, db: Session = Depends(get_db)):
    exists = db.query(User).filter(User.username == username).first()
    if exists:
        return {"is_available": False, "message": "이미 사용 중인 아이디입니다."}
    return {"is_available": True, "message": "사용 가능한 아이디입니다."}
