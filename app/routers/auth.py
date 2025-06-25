import os
from fastapi import APIRouter, HTTPException, BackgroundTasks, status, Response, Cookie
from app.schemas.user import UserCreate, UserLogin
from app.core.database import db
from app.utils.email import generate_verification_code, send_verification_email
from datetime import datetime, timedelta
import jwt  # PyJWT 사용
from app.core.config import settings
from app.utils.security import get_password_hash, verify_password
import logging
from bson import ObjectId

router = APIRouter()
logger = logging.getLogger("auth_router")
logging.basicConfig(level=logging.INFO)

# settings.DEBUG를 사용하여 로컬/프로덕션 환경을 구분합니다.
is_local = settings.DEBUG

def get_cookie_options():
    if is_local:
        # 로컬 환경 (HTTP)
        return {
            "httponly": True,
            "max_age": 2592000,  # 30일 (30 * 24 * 60 * 60)
            "secure": False,       # HTTP에서는 secure False
            "samesite": "Lax",     # 기본적으로 Lax
            "path": "/"            # 전체 경로 적용
        }
    else:
        # 프로덕션 환경 (HTTPS)
        return {
            "httponly": True,
            "max_age": 2592000,  # 30일 (30 * 24 * 60 * 60)
            "secure": True,        # HTTPS 환경에서는 True
            "samesite": "None",    # cross-site 요청 허용
            "path": "/"            # domain 옵션 제거
        }

def fix_mongo_object_ids(obj):
    if isinstance(obj, list):
        return [fix_mongo_object_ids(item) for item in obj]
    elif isinstance(obj, dict):
        new_obj = {}
        for key, value in obj.items():
            if isinstance(value, ObjectId):
                new_obj[key] = str(value)
            else:
                new_obj[key] = fix_mongo_object_ids(value)
        return new_obj
    return obj

@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(user: UserCreate, background_tasks: BackgroundTasks):
    existing_name = await db.users.find_one({"name": user.name})
    if existing_name:
        raise HTTPException(status_code=400, detail="이미 사용중인 이름입니다.")

    existing_email = await db.users.find_one({"email": user.email})
    if existing_email:
        raise HTTPException(status_code=400, detail="이미 사용중인 이메일입니다.")

    hashed_password = get_password_hash(user.password)
    user_data = user.dict()
    user_data["password"] = hashed_password
    user_data["is_active"] = False
    user_data["created_at"] = datetime.utcnow()
    await db.users.insert_one(user_data)

    await db.user_verification.delete_many({"email": user.email, "role": user.role})

    code = generate_verification_code()
    expires_at = datetime.utcnow() + timedelta(minutes=4)
    await db.user_verification.insert_one({
        "email": user.email,
        "role": user.role,
        "code": code,
        "expires_at": expires_at,
        "created_at": datetime.utcnow()
    })

    logger.info(f"회원가입: {user.email} 에 대해 인증 코드 {code} 발송 (만료: {expires_at})")
    background_tasks.add_task(send_verification_email, user.email, code)

    return {
        "message": "회원가입 요청 완료. 인증 코드가 전송되었습니다.",
        "email": user.email,
        "role": user.role
    }

@router.post("/verify", status_code=status.HTTP_200_OK)
async def verify_code(data: dict, response: Response):
    email = data.get("email")
    role = data.get("role")
    code = data.get("code")
    if not email or not role or not code:
        raise HTTPException(status_code=400, detail="필수 정보 누락")

    record = await db.user_verification.find_one({"email": email, "role": role})
    if not record:
        raise HTTPException(status_code=404, detail="인증 정보가 존재하지 않습니다.")

    current_time = datetime.utcnow()
    expires_at = record["expires_at"]
    if expires_at.tzinfo is not None:
        expires_at = expires_at.replace(tzinfo=None)

    if current_time > expires_at:
        raise HTTPException(status_code=400, detail="인증 코드가 만료되었습니다.")
    if record["code"] != code:
        raise HTTPException(status_code=400, detail="인증 코드가 일치하지 않습니다.")

    await db.users.update_one({"email": email}, {"$set": {"is_active": True}})
    await db.user_verification.delete_one({"email": email, "role": role})

    user = await db.users.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=404, detail="사용자 정보를 찾을 수 없습니다.")

    current_time = datetime.utcnow()
    expiry_time = current_time + timedelta(days=30)  # 30일로 대폭 연장
    logger.info(f"이메일 인증 토큰 생성 - 현재 시간: {current_time}, 만료 시간: {expiry_time}")

    payload = {
        "sub": str(user["_id"]),
        "name": user["name"],
        "email": user["email"],
        "exp": expiry_time
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")

    response.set_cookie(
        key="access_token",
        value=token,
        **get_cookie_options()
    )

    logger.info(f"{email} 인증 완료, 계정 활성화됨.")
    return {"message": "이메일 인증 완료. 계정이 활성화되었습니다."}

@router.post("/login", status_code=status.HTTP_200_OK)
async def login(user: UserLogin, response: Response):
    existing = await db.users.find_one({"email": user.email})
    if not existing:
        raise HTTPException(status_code=400, detail="존재하지 않는 계정입니다.")
    if not verify_password(user.password, existing["password"]):
        raise HTTPException(status_code=400, detail="비밀번호가 일치하지 않습니다.")
    if not existing.get("is_active", False):
        raise HTTPException(status_code=400, detail="계정이 활성화되지 않았습니다. 이메일 인증을 진행해주세요.")

    current_time = datetime.utcnow()
    expiry_time = current_time + timedelta(days=30)  # 30일로 대폭 연장
    logger.info(f"로그인 토큰 생성 - 현재 시간: {current_time}, 만료 시간: {expiry_time}")

    payload = {
        "sub": str(existing["_id"]),
        "name": existing["name"],
        "email": existing["email"],
        "exp": expiry_time
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")

    response.set_cookie(
        key="access_token",
        value=token,
        **get_cookie_options()
    )

    logger.info(f"{existing['email']} 로그인 성공, JWT 토큰 발급됨.")

    # 클라이언트에서 사용할 수 있도록 토큰과 사용자 정보를 응답에 포함
    return {
        "message": "로그인 성공",
        "access_token": token,
        "user": {
            "id": str(existing["_id"]),
            "name": existing["name"],
            "email": existing["email"],
            "role": existing.get("role", "user")
        }
    }

@router.get("/me", status_code=status.HTTP_200_OK)
async def get_current_user_endpoint(access_token: str = Cookie(None)):
    if not access_token:
        raise HTTPException(status_code=401, detail="토큰이 제공되지 않았습니다.")
    try:
        payload = jwt.decode(access_token, settings.SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="토큰이 만료되었습니다.")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")

    user = await db.users.find_one({"email": payload["email"]})
    if not user:
        raise HTTPException(status_code=404, detail="사용자 정보를 찾을 수 없습니다.")

    user["_id"] = str(user["_id"])
    user.pop("password", None)
    return {"user": user}

@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(response: Response):
    response.delete_cookie("access_token")
    return {"message": "로그아웃 성공"}
