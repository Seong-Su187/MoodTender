from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
import random

router = APIRouter(tags=["Pairing"])

# 🧠 서버 메모리 구조 변경: PIN 번호에 웹소켓 객체와 웹 유저의 ID를 함께 묶어서 기억
# 예: {"123456": {"websocket": ws, "user_id": 1}}
active_connections = {}

class VerifyRequest(BaseModel):
    pin: str
    user_id: int # 모바일 앱에서 로그인한 유저의 ID

# ---------------------------------------------------------
# 💻 1. [웹] 디바이스 연동 버튼 클릭 시 PIN 발급
# ---------------------------------------------------------
# 웹에서 로그인한 user_id를 주소에 실어서 보냅니다.
@router.websocket("/api/pairing/ws/{user_id}")
async def pairing_websocket(websocket: WebSocket, user_id: int):
    await websocket.accept()
    pin = str(random.randint(100000, 999999))
    
    # 발급한 PIN과 현재 접속한 웹 화면(websocket), 그리고 유저 ID를 매칭해 저장
    active_connections[pin] = {"websocket": websocket, "user_id": user_id}
    print(f"[웹소켓] 웹 유저({user_id})가 기기 연동 요청 (PIN: {pin})")

    try:
        await websocket.send_json({"type": "pin_generated", "pin": pin})
        while True:
            await websocket.receive_text()
            
    except WebSocketDisconnect:
        if pin in active_connections:
            del active_connections[pin]
            print(f"[웹소켓 끊김] PIN 폐기: {pin}")

# ---------------------------------------------------------
# 📱 2. [모바일] PIN 번호 및 동일 계정 검증
# ---------------------------------------------------------
@router.post("/api/mobile/pairing/verify")
async def verify_pairing(data: VerifyRequest):
    connection = active_connections.get(data.pin)
    
    if not connection:
        raise HTTPException(status_code=400, detail="유효하지 않거나 만료된 PIN 번호입니다.")
    
    # 🌟 핵심 보안 로직: 웹에서 로그인한 계정과 모바일에서 로그인한 계정이 같은가?
    if connection["user_id"] != data.user_id:
        raise HTTPException(status_code=403, detail="웹과 모바일의 로그인 계정이 다릅니다. 동일한 계정으로 시도해주세요.")
    
    try:
        ws = connection["websocket"]
        await ws.send_json({
            "type": "pairing_success", 
            "message": "디바이스 연결 성공!"
        })
        
        del active_connections[data.pin]
        print(f"[기기 연동 성공] User {data.user_id}의 웹-모바일 동기화 완료!")
        
        return {"status": "success", "message": "웹 화면 잠금이 해제되었습니다."}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail="기기 연결 중 오류가 발생했습니다.")