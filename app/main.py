from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, research, board, activity, chat, websocket_native
from app.core.config import settings
from app.core.database import connect_to_mongo, close_mongo_connection

# FastAPI 앱 생성
app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    debug=settings.DEBUG
)

# 허용할 도메인 목록을 먼저 정의
cors_origins = [
    "http://localhost:3000",
    "http://192.168.0.11:3000",
    "http://192.168.92.1:3000",
    "http://172.30.1.71:3000",
    "https://researchforest.netlify.app",
    "https://port-0-youminseok-forest-research-backend-m8qrfco7a6ee3b26.sel4.cloudtype.app",
]

# CORS 미들웨어 추가
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    await connect_to_mongo()
    print("MongoDB 연결 성공!")

    # 채팅 데이터베이스 스키마 설정
    from app.core.database_setup import setup_chat_database
    await setup_chat_database()
    print("채팅 데이터베이스 스키마 설정 완료!")

@app.on_event("shutdown")
async def shutdown_event():
    await close_mongo_connection()
    print("MongoDB 연결 종료!")

# 라우터 등록 ("/api" prefix)
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(research.router, prefix="/api/research", tags=["research"])
app.include_router(board.router, prefix="/api/board", tags=["board"])
app.include_router(activity.router, prefix="/api/activity", tags=["activity"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])

# WebSocket 라우터 등록
app.include_router(websocket_native.router, tags=["websocket"])

@app.get("/ping")
async def ping():
    return {"message": "pong"}

# 기본 FastAPI 앱 사용 (Socket.IO 제거)
