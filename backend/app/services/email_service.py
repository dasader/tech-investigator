import aiosmtplib
from email.message import EmailMessage
from app.config import settings


async def send_completion_email(to_email: str, job_id: int, pdf_url: str):
    if not settings.smtp_user:
        return
    msg = EmailMessage()
    msg["Subject"] = f"[TechSpec] 분석 완료 — 작업 #{job_id}"
    msg["From"] = settings.smtp_user
    msg["To"] = to_email
    msg.set_content(
        f"요청하신 국가전략기술 Spec 분석이 완료되었습니다.\n\n"
        f"PDF 리포트 다운로드: {pdf_url}\n\n"
        f"(링크는 24시간 유효합니다)"
    )
    await aiosmtplib.send(
        msg,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user,
        password=settings.smtp_password,
        start_tls=True,
    )
