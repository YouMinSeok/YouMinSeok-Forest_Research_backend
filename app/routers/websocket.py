# app/routers/websocket.py
import socketio
from fastapi import HTTPException
from app.core.database import db
from datetime import datetime
import pytz
import jwt
from app.core.config import settings

# 서울 타임존 객체 생성
seoul_tz = pytz.timezone('Asia/Seoul')

# Socket.IO 서버 생성
sio = socketio.AsyncServer(
    cors_allowed_origins="*",
    logger=True,
    engineio_logger=True
)

# 연결된 사용자들 저장 (user_id -> session_id)
connected_users = {}

async def get_user_from_token(token):
    """JWT 토큰에서 사용자 정보 추출"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            return None

        # 데이터베이스에서 사용자 조회
        from bson import ObjectId
        try:
            user = await db["users"].find_one({"_id": ObjectId(user_id)})
        except:
            user = await db["users"].find_one({"_id": user_id})
        if user is None:
            return None

        user["id"] = str(user["_id"])
        return user
    except jwt.PyJWTError:
        return None

@sio.event
async def connect(sid, environ):
    """클라이언트 연결"""
    print(f"클라이언트 연결: {sid}")

@sio.event
async def disconnect(sid):
    """클라이언트 연결 해제"""
    print(f"클라이언트 연결 해제: {sid}")
    # 연결된 사용자 목록에서 제거
    user_to_remove = None
    for user_id, session_id in connected_users.items():
        if session_id == sid:
            user_to_remove = user_id
            break

    if user_to_remove:
        del connected_users[user_to_remove]
        print(f"사용자 {user_to_remove} 연결 해제됨")

@sio.event
async def join_chat(sid, data):
    """채팅방 참가"""
    try:
        token = data.get('token')
        room_id = data.get('room_id')

        if not token or not room_id:
            await sio.emit('error', {'message': '토큰과 방 ID가 필요합니다.'}, room=sid)
            return

        # 토큰으로 사용자 인증
        user = await get_user_from_token(token)
        if not user:
            await sio.emit('error', {'message': '유효하지 않은 토큰입니다.'}, room=sid)
            return

        user_id = user['id']

        # 사용자 세션 저장
        connected_users[user_id] = sid

        # 채팅방에 참가
        await sio.enter_room(sid, room_id)

        print(f"🎯 채팅방 참가: {user['name']} ({user_id}) -> {room_id}")
        print(f"🔗 WebSocket 세션: {sid}")

        # 채팅방 참가 확인 메시지
        await sio.emit('joined_room', {
            'room_id': room_id,
            'user_id': user_id,
            'user_name': user['name']
        }, room=sid)

    except Exception as e:
        print(f"채팅방 참가 에러: {e}")
        await sio.emit('error', {'message': '채팅방 참가에 실패했습니다.'}, room=sid)

@sio.event
async def send_message(sid, data):
    """메시지 전송"""
    try:
        token = data.get('token')
        room_id = data.get('room_id')
        message = data.get('message', '').strip()

        if not token or not room_id or not message:
            await sio.emit('error', {'message': '모든 필드가 필요합니다.'}, room=sid)
            return

        # 토큰으로 사용자 인증
        user = await get_user_from_token(token)
        if not user:
            await sio.emit('error', {'message': '유효하지 않은 토큰입니다.'}, room=sid)
            return

        user_id = user['id']
        user_name = user['name']

        # 데이터베이스에 메시지 저장
        message_doc = {
            "room_id": room_id,
            "sender_id": user_id,
            "sender_name": user_name,
            "message": message,
            "created_at": datetime.now(seoul_tz),
            "is_read": False
        }

        result = await db["chat_messages"].insert_one(message_doc)
        message_doc["_id"] = str(result.inserted_id)

        print(f"💬 새 메시지 저장됨: {message[:50]}...")
        print(f"👤 송신자: {user_name} ({user_id})")
        print(f"🏠 채팅방: {room_id}")
        print(f"🔑 메시지 ID: {result.inserted_id}")

        # 채팅방의 마지막 메시지 업데이트
        update_result = await db["chat_rooms"].update_one(
            {"room_id": room_id},
            {
                "$set": {
                    "last_message": message,
                    "last_message_at": datetime.now(seoul_tz)
                }
            }
        )

        print(f"📝 채팅방 업데이트 완료: {update_result.modified_count}개 문서 수정됨")

        # 채팅방의 모든 사용자에게 메시지 전송
        await sio.emit('new_message', {
            'id': message_doc["_id"],
            'room_id': room_id,
            'sender_id': user_id,
            'sender_name': user_name,
            'message': message,
            'created_at': message_doc["created_at"].isoformat(),
            'is_read': False
        }, room=room_id)

        print(f"메시지 전송 완료: {user_name} -> {room_id}: {message}")

    except Exception as e:
        print(f"메시지 전송 에러: {e}")
        await sio.emit('error', {'message': '메시지 전송에 실패했습니다.'}, room=sid)

@sio.event
async def typing_start(sid, data):
    """타이핑 시작"""
    try:
        token = data.get('token')
        room_id = data.get('room_id')

        if not token or not room_id:
            return

        user = await get_user_from_token(token)
        if not user:
            return

        # 해당 방의 다른 사용자들에게 타이핑 상태 전송
        await sio.emit('user_typing', {
            'user_id': user['id'],
            'user_name': user['name'],
            'room_id': room_id,
            'typing': True
        }, room=room_id, skip_sid=sid)

    except Exception as e:
        print(f"타이핑 시작 에러: {e}")

@sio.event
async def typing_stop(sid, data):
    """타이핑 중지"""
    try:
        token = data.get('token')
        room_id = data.get('room_id')

        if not token or not room_id:
            return

        user = await get_user_from_token(token)
        if not user:
            return

        # 해당 방의 다른 사용자들에게 타이핑 중지 상태 전송
        await sio.emit('user_typing', {
            'user_id': user['id'],
            'user_name': user['name'],
            'room_id': room_id,
            'typing': False
        }, room=room_id, skip_sid=sid)

    except Exception as e:
        print(f"타이핑 중지 에러: {e}")

@sio.event
async def leave_chat(sid, data):
    """채팅방 나가기"""
    try:
        room_id = data.get('room_id')
        if room_id:
            await sio.leave_room(sid, room_id)
            print(f"사용자가 채팅방 {room_id}에서 나감")

    except Exception as e:
        print(f"채팅방 나가기 에러: {e}")

# FastAPI 앱에 Socket.IO 추가하기 위한 함수
def get_socketio_app():
    return sio
