import uuid
import bcrypt as _bcrypt_lib
from jose import jwt
from datetime import datetime, timedelta
from config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES

# Redis 없을 때 in-memory 블랙리스트로 대체
_token_blacklist: set = set()

def hash_pw(pw: str) -> str:
    return _bcrypt_lib.hashpw(pw.encode(), _bcrypt_lib.gensalt()).decode()

def verify_pw(plain: str, hashed: str) -> bool:
    return _bcrypt_lib.checkpw(plain.encode(), hashed.encode())

def create_access_token(username: str) -> dict:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    jti    = str(uuid.uuid4())
    payload = {"sub": username, "exp": expire, "jti": jti}
    token  = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return {"access_token": token, "jti": jti, "token_type": "bearer"}

def block_token(jti: str, expires_in_seconds: int):
    _token_blacklist.add(jti)

def is_token_blocked(jti: str) -> bool:
    return jti in _token_blacklist
