from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update
import random

# database 및 domain 모델 import (프로젝트 경로에 맞춤)
from backend.database import get_db
from backend.models import domain

router = APIRouter(tags=["Pairing"])

# 🧠 서버 메모리 구조: PIN 번호에 웹소켓 객체와 웹 유저의 ID를 함께 묶어서 기억
# 예: {"123456": {"websocket": ws, "user_id": 1}}
active_connections = {}

class VerifyRequest(BaseModel):
    pin: str
    user_id: int # 모바일 앱에서 로그인한 유저의 ID

# ---------------------------------------------------------
# 💻 1. [웹] 디바이스 연동 버튼 클릭 시 PIN 발급
# ---------------------------------------------------------
@router.websocket("/api/pairing/ws/{user_id}")
async def pairing_websocket(websocket: WebSocket, user_id: int):
    await websocket.accept()
    pin = str(random.randint(100000, 999999))
    
    # 발급한 PIN과 현재 접속한 웹 화면(websocket), 그리고 유저 ID를 매칭해 저장
    active_connections[pin] = {"websocket": websocket, "user_id": user_id}
    print(f"🔗 [웹소켓] 웹 유저({user_id})가 기기 연동 요청 (PIN: {pin})")

    try:
        await websocket.send_json({"type": "pin_generated", "pin": pin})
        while True:
            await websocket.receive_text()
            
    except WebSocketDisconnect:
        if pin in active_connections:
            del active_connections[pin]
            print(f"❌ [웹소켓 끊김] PIN 폐기: {pin}")

# ---------------------------------------------------------
# 📱 2. [모바일] PIN 번호 검증 및 DB 연동 상태 영구 저장
# ---------------------------------------------------------
@router.post("/api/mobile/pairing/verify")
async def verify_pairing(data: VerifyRequest, db: AsyncSession = Depends(get_db)):
    connection = active_connections.get(data.pin)
    
    if not connection:
        raise HTTPException(status_code=400, detail="유효하지 않거나 만료된 PIN 번호입니다.")
    
    # 🌟 핵심 보안 로직: 웹에서 로그인한 계정과 모바일에서 로그인한 계정이 같은가?
    if connection["user_id"] != data.user_id:
        raise HTTPException(status_code=403, detail="웹과 모바일의 로그인 계정이 다릅니다. 동일한 계정으로 시도해주세요.")
    
    try:
        # 🚀 1. Supabase DB의 users 테이블에 연동 완료 도장 찍기 (영구 저장)
        await db.execute(
            update(domain.User)
            .where(domain.User.id == data.user_id)
            .values(is_device_paired=True)
        )
        await db.commit()

        # 💻 2. 웹 화면(웹소켓)으로 연동 성공 메시지 알림
        ws = connection["websocket"]
        await ws.send_json({
            "type": "pairing_success", 
            "message": "디바이스 연결 성공!"
        })
        
        # 사용이 끝난 메모리 상의 PIN 번호 제거
        del active_connections[data.pin]
        print(f"✅ [기기 연동 성공] User {data.user_id}의 웹-모바일 동기화 및 DB 영구 저장 완료!")
        
        return {"status": "success", "message": "웹 화면 잠금이 해제되었습니다."}
        
    except Exception as e:
        await db.rollback() # 오류 발생 시 DB 롤백
        print(f"❌ [페어링 오류 발생]: {str(e)}")
        raise HTTPException(status_code=500, detail="기기 연결 중 오류가 발생했습니다.")