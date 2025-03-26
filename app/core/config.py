import os
from dotenv import load_dotenv

load_dotenv()  # .env 파일의 환경변수를 로드합니다.

class Settings:
    API_TITLE = os.getenv("API_TITLE", "My Research Platform API")
    API_VERSION = os.getenv("API_VERSION", "0.1.0")
    DEBUG = os.getenv("DEBUG", "True").lower() in ["true", "1", "yes"]

    # MongoDB 설정
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    DATABASE_NAME = os.getenv("DATABASE_NAME", "research_forest")

    SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key")

    # 이메일 제공자 선택 ("gmail" 또는 "naver")
    EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "gmail").lower()

    # SMTP 설정: 제공자에 따라 선택
    if EMAIL_PROVIDER == "naver":
        MAIL_USERNAME = os.getenv("NAVER_MAIL_USERNAME", "your-naver-email@naver.com")
        MAIL_PASSWORD = os.getenv("NAVER_MAIL_PASSWORD", "your-naver-password")
        MAIL_FROM = os.getenv("NAVER_MAIL_FROM", "your-naver-email@naver.com")
        MAIL_PORT = int(os.getenv("NAVER_MAIL_PORT", "465"))
        MAIL_SERVER = os.getenv("NAVER_MAIL_SERVER", "smtp.naver.com")
        MAIL_TLS = os.getenv("NAVER_MAIL_TLS", "False").lower() in ["true", "1", "yes"]
        MAIL_SSL = os.getenv("NAVER_MAIL_SSL", "True").lower() in ["true", "1", "yes"]
    else:
        MAIL_USERNAME = os.getenv("GMAIL_MAIL_USERNAME", "your-email@gmail.com")
        MAIL_PASSWORD = os.getenv("GMAIL_MAIL_PASSWORD", "your-gmail-app-password")
        MAIL_FROM = os.getenv("GMAIL_MAIL_FROM", "your-email@gmail.com")
        MAIL_PORT = int(os.getenv("GMAIL_MAIL_PORT", "587"))
        MAIL_SERVER = os.getenv("GMAIL_MAIL_SERVER", "smtp.gmail.com")
        MAIL_TLS = os.getenv("GMAIL_MAIL_TLS", "True").lower() in ["true", "1", "yes"]
        MAIL_SSL = os.getenv("GMAIL_MAIL_SSL", "False").lower() in ["true", "1", "yes"]

    USE_CREDENTIALS = True

settings = Settings()
