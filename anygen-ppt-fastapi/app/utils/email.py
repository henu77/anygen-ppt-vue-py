"""邮件发送工具"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import settings
from loguru import logger


def send_email(subject: str, body: str, to: str = None) -> bool:
    """发送邮件

    Args:
        subject: 邮件主题
        body: 邮件正文（HTML）
        to: 收件人，默认使用配置中的 SMTP_TO

    Returns:
        是否发送成功
    """
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
        logger.warning("邮件未配置 SMTP_USER/SMTP_PASSWORD，跳过发送")
        return False

    to = to or settings.SMTP_TO
    if not to:
        logger.warning("未配置收件人，跳过发送")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_USER
    msg["To"] = to
    msg.attach(MIMEText(body, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_USER, [to], msg.as_string())
        logger.info(f"邮件发送成功: {subject} -> {to}")
        return True
    except Exception as e:
        logger.error(f"邮件发送失败: {e}")
        return False
