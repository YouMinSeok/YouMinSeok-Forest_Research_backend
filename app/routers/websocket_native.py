# app/routers/websocket_native.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from typing import Dict, List
import json
import jwt
from datetime import datetime
import pytz
from app.core.database import db
from app.core.config import settings

router = APIRouter()

# 서울 타임존
seoul_tz = pytz.timezone('Asia/Seoul')

# 연결된 클라이언트들 관리
class ConnectionManager:
    def __init__(self):
        # room_id -> List[WebSocket]
        self.active_connections: Dict[str, List[WebSocket]] = {}
        # websocket -> user_info
        self.user_connections: Dict[WebSocket, dict] = {}

    async def connect(self, websocket: WebSocket, room_id: str, user_info: dict):
        await websocket.accept()

        if room_id not in self.active_connections:
            self.active_connections[room_id] = []

        self.active_connections[room_id].append(websocket)
        self.user_connections[websocket] = {
            "user_id": user_info["id"],
            "user_name": user_info["name"],
            "room_id": room_id
        }

        print(f"✅ WebSocket 연결: {user_info['name']} -> {room_id}")

    def disconnect(self, websocket: WebSocket):
        user_info = self.user_connections.get(websocket)
        if user_info:
            room_id = user_info["room_id"]
            if room_id in self.active_connections:
                self.active_connections[room_id].remove(websocket)
                if not self.active_connections[room_id]:
                    del self.active_connections[room_id]

            del self.user_connections[websocket]
            print(f"❌ WebSocket 연결 해제: {user_info['user_name']}")

    async def send_to_room(self, room_id: str, message: dict):
        if room_id in self.active_connections:
            connections = self.active_connections[room_id].copy()
            for connection in connections:
                try:
                    await connection.send_text(json.dumps(message))
                except:
                    # 연결이 끊어진 경우 제거
                    self.disconnect(connection)

    async def send_typing_status(self, room_id: str, sender_websocket: WebSocket, typing_data: dict):
        if room_id in self.active_connections:
            connections = self.active_connections[room_id].copy()
            for connection in connections:
                if connection != sender_websocket:  # 본인 제외
                    try:
                        await connection.send_text(json.dumps(typing_data))
                    except:
                        self.disconnect(connection)

manager = ConnectionManager()

async def get_user_from_token(token: str):
    """JWT 토큰에서 사용자 정보 추출"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        user_name: str = payload.get("name")

        if not user_id or not user_name:
            return None

        return {"id": user_id, "name": user_name}
    except jwt.PyJWTError:
        return None

@router.websocket("/ws/chat/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    # 토큰 확인
    token = None
    if "authorization" in websocket.headers:
        auth_header = websocket.headers["authorization"]
        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]

    # 쿼리 파라미터에서도 토큰 확인
    query_params = websocket.query_params
    if not token and "token" in query_params:
        token = query_params["token"]

    if not token:
        await websocket.close(code=4001, reason="No token provided")
        return

    # 사용자 인증
    user_info = await get_user_from_token(token)
    if not user_info:
        await websocket.close(code=4002, reason="Invalid token")
        return

    # 채팅방 권한 확인
    room = await db["chat_rooms"].find_one({"room_id": room_id})
    if not room:
        await websocket.close(code=4003, reason="Room not found")
        return

    if user_info["id"] not in [room["user1_id"], room["user2_id"]]:
        await websocket.close(code=4004, reason="Access denied")
        return

    # 연결 수락
    await manager.connect(websocket, room_id, user_info)

    # 채팅방 참가 알림
    await manager.send_to_room(room_id, {
        "type": "user_joined",
        "user_id": user_info["id"],
        "user_name": user_info["name"]
    })

    try:
        while True:
            # 메시지 수신
            data = await websocket.receive_text()
            message_data = json.loads(data)

            message_type = message_data.get("type")

            if message_type == "send_message":
                await handle_send_message(room_id, user_info, message_data)

            elif message_type == "typing_start":
                await manager.send_typing_status(room_id, websocket, {
                    "type": "user_typing",
                    "user_id": user_info["id"],
                    "user_name": user_info["name"],
                    "typing": True
                })

            elif message_type == "typing_stop":
                await manager.send_typing_status(room_id, websocket, {
                    "type": "user_typing",
                    "user_id": user_info["id"],
                    "user_name": user_info["name"],
                    "typing": False
                })

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        # 채팅방 나감 알림
        await manager.send_to_room(room_id, {
            "type": "user_left",
            "user_id": user_info["id"],
            "user_name": user_info["name"]
        })

async def handle_send_message(room_id: str, user_info: dict, message_data: dict):
    """메시지 전송 처리"""
    message_text = message_data.get("message", "").strip()

    if not message_text:
        return

    # 데이터베이스에 메시지 저장
    message_doc = {
        "room_id": room_id,
        "sender_id": user_info["id"],
        "sender_name": user_info["name"],
        "message": message_text,
        "created_at": datetime.now(seoul_tz),
        "is_read": False
    }

    result = await db["chat_messages"].insert_one(message_doc)
    message_doc["_id"] = str(result.inserted_id)

    print(f"💬 메시지 저장: {user_info['name']} -> {room_id}: {message_text}")

    # 채팅방의 마지막 메시지 업데이트
    await db["chat_rooms"].update_one(
        {"room_id": room_id},
        {
            "$set": {
                "last_message": message_text,
                "last_message_at": datetime.now(seoul_tz)
            }
        }
    )

    # 채팅방의 모든 사용자에게 메시지 전송
    await manager.send_to_room(room_id, {
        "type": "new_message",
        "id": message_doc["_id"],
        "room_id": room_id,
        "sender_id": user_info["id"],
        "sender_name": user_info["name"],
        "message": message_text,
        "created_at": message_doc["created_at"].isoformat(),
        "is_read": False
    })
