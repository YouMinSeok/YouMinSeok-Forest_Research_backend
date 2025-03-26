import random
import string
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from app.core.config import settings

def generate_verification_code(length: int = 6) -> str:
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

# FastAPI-Mail ConnectionConfig 생성: 제공자에 따라 TLS/SSL 설정 변경
if settings.EMAIL_PROVIDER == "naver":
    conf = ConnectionConfig(
        MAIL_USERNAME=settings.MAIL_USERNAME,
        MAIL_PASSWORD=settings.MAIL_PASSWORD,
        MAIL_FROM=settings.MAIL_FROM,
        MAIL_PORT=settings.MAIL_PORT,
        MAIL_SERVER=settings.MAIL_SERVER,
        MAIL_STARTTLS=False,    # 네이버는 TLS 사용하지 않음
        MAIL_SSL_TLS=True,      # 네이버는 SSL 사용
        USE_CREDENTIALS=settings.USE_CREDENTIALS,
        TEMPLATE_FOLDER=""
    )
else:
    conf = ConnectionConfig(
        MAIL_USERNAME=settings.MAIL_USERNAME,
        MAIL_PASSWORD=settings.MAIL_PASSWORD,
        MAIL_FROM=settings.MAIL_FROM,
        MAIL_PORT=settings.MAIL_PORT,
        MAIL_SERVER=settings.MAIL_SERVER,
        MAIL_STARTTLS=True,     # Gmail은 TLS 사용
        MAIL_SSL_TLS=False,     # Gmail은 SSL 미사용
        USE_CREDENTIALS=settings.USE_CREDENTIALS,
        TEMPLATE_FOLDER=""
    )

async def send_verification_email(email: str, code: str):
    message = MessageSchema(
        subject="연구의숲 회원가입 인증 코드",
        recipients=[email],
        body=f"안녕하세요.\n인증 코드: [{code}]\n이 코드는 4분 후에 만료됩니다.",
        subtype="plain"
    )
    fm = FastMail(conf)
    await fm.send_message(message)
