from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

client = AsyncIOMotorClient(settings.MONGO_URI)
db = client[settings.DATABASE_NAME]

async def connect_to_mongo():
    try:
        # MongoDB 연결 테스트 (ping)
        await client.admin.command("ping")
        print("✅ MongoDB 연결 성공!")
    except Exception as e:
        print("❌ MongoDB 연결 실패:", e)

async def close_mongo_connection():
    client.close()
    print("✅ MongoDB 연결 종료!")

# FastAPI 의존성 주입 등에 사용할 수 있도록 반환하는 함수
async def get_database():
    return db
