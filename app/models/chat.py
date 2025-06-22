# app/models/chat.py
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from bson import ObjectId

class ChatRoomCreate(BaseModel):
    user1_id: str
    user2_id: str
    user1_name: str
    user2_name: str

class ChatRoom(BaseModel):
    id: Optional[str] = Field(alias="_id")
    room_id: str  # 두 사용자 ID로 생성된 고유 방 ID (예: "user1_user2")
    user1_id: str
    user2_id: str
    user1_name: str
    user2_name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_message: Optional[str] = None
    last_message_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        json_encoders = {ObjectId: str}

class ChatMessageCreate(BaseModel):
    room_id: str
    sender_id: str
    sender_name: str
    message: str

class ChatMessage(BaseModel):
    id: Optional[str] = Field(alias="_id")
    room_id: str
    sender_id: str
    sender_name: str
    message: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_read: bool = False

    class Config:
        populate_by_name = True
        json_encoders = {ObjectId: str}

class ChatRoomResponse(BaseModel):
    room_id: str
    other_user_id: str
    other_user_name: str
    last_message: Optional[str]
    last_message_at: Optional[datetime]
    unread_count: int
