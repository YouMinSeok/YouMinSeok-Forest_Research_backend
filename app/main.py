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

# 프론트엔드 주소 (개발 + 배포 환경 포함)
origins = [
    "http://localhost:3000",
    "http://192.168.0.11:3000",
    "https://researchforest.netlify.app",  # ✅ Netlify 배포 주소 추가
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

# 기존 라우터 등록
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(research.router, prefix="/api/research", tags=["research"])
app.include_router(board.router, prefix="/api/board", tags=["board"])

@app.get("/ping")
async def ping():
    return {"message": "pong"}
