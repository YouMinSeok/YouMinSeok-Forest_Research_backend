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

# 허용할 도메인 목록 (개발, Netlify 프론트엔드, 백엔드 도메인)
origins = [
    "http://localhost:3000",
    "http://192.168.0.11:3000",
    "http://192.168.92.1:3000",              # 현재 사용 중인 프론트엔드 오리진
    "https://researchforest.netlify.app",    # 프로덕션 프론트엔드 주소
    "https://port-0-youminseok-forest-research-backend-m8qrfco7a6ee3b26.sel4.cloudtype.app",  # 백엔드 공개 주소
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,         # 위 목록에 포함된 오리진만 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    await connect_to_mongo()
    print("MongoDB 연결 성공!")

@app.on_event("shutdown")
async def shutdown_event():
    await close_mongo_connection()
    print("MongoDB 연결 종료!")

# 라우터 등록 ("/api" prefix)
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(research.router, prefix="/api/research", tags=["research"])
app.include_router(board.router, prefix="/api/board", tags=["board"])

@app.get("/ping")
async def ping():
    return {"message": "pong"}
