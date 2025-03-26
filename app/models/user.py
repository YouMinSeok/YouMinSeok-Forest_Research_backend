# app/models/user.py
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class UserCreate(BaseModel):
    name: str
    password: str
    email: EmailStr
    role: str  # "student" 또는 "professor"


class UserLogin(BaseModel):
    email: EmailStr
    password: str

class User(BaseModel):
    id: Optional[str]
    name: str
    student_number: Optional[str]
    email: EmailStr
    password: str
    role: str
    is_active: bool = False
    created_at: datetime = datetime.utcnow()

    class Config:
        orm_mode = True
