from passlib.context import CryptContext
from fastapi import HTTPException, Cookie, Header
from typing import Optional
import jwt  # PyJWT 사용
from jwt import ExpiredSignatureError, InvalidTokenError
from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_current_user(access_token: str = Cookie(None)):
    """
    쿠키 "access_token"에서 JWT 토큰을 읽어 "sub"와 "name"을 추출하여 사용자 정보를 반환합니다.
    """
    if not access_token:
        raise HTTPException(status_code=401, detail="토큰이 제공되지 않았습니다.")
    try:
        payload = jwt.decode(access_token, settings.SECRET_KEY, algorithms=["HS256"])
        user_id: str = payload.get("sub")
        user_name: str = payload.get("name")
        if user_id is None or user_name is None:
            raise HTTPException(status_code=401, detail="토큰 정보가 부족합니다(sub, name).")
    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="토큰이 만료되었습니다.")
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")

    return {"id": user_id, "name": user_name}
