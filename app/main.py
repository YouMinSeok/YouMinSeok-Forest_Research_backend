from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import auth, research, board
from app.core.config import settings
from app.core.database import connect_to_mongo, close_mongo_connection

app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    debug=settings.DEBUG
)

# 프론트엔드 주소 (개발 + 배포 환경 둘 다 허용)
origins = [
    "http://localhost:3000",
    "http://192.168.0.11:3000",
    "https://port-0-youminseok-forest-research-backend-m8qrfco7a6ee3b26.sel4.cloudtype.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    await connect_to_mongo()
    print("✅ MongoDB 연결 성공!")

@app.on_event("shutdown")
async def shutdown_event():
    await close_mongo_connection()
    print("✅ MongoDB 연결 종료!")

# 기존 라우터 등록 ("/api" prefix로 사용)
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(research.router, prefix="/api/research", tags=["research"])
app.include_router(board.router, prefix="/api/board", tags=["board"])

@app.get("/ping")
async def ping():
    return {"message": "pong"}
