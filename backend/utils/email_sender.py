"""
backend/utils/email_sender.py
Gmail SMTP 发信模块。
通过 App Password 认证发送邮件，正文为简短引导语，完整内容以纯文本附件发送。
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "fasheng087@gmail.com"

BODY_TEMPLATE = """Hi {recipient_name}，

AI Assistant 已根据您的问题生成了一份内容摘要，详见附件「{attachment_name}」。

---

此邮件由 AI Agent 自动发送。如有疑问，请直接回复此邮箱。
SUSTech AI Assistant
"""


def send_md_mail(
    password: str,
    to: str,
    subject: str,
    md_content: str,
    attachment_filename: str = "summary.md",
    recipient_name: str = "",
) -> str:
    if not md_content or len(md_content.strip()) < 50:
        return "ERROR: md_content 太短（少于50字）。请将完整的回答内容传入 md_content 参数，而非只写标题。"

    recipient = recipient_name or to.split("@")[0]

    safe_filename = attachment_filename
    if not safe_filename.endswith(".txt"):
        safe_filename = attachment_filename.rsplit(".", 1)[0] + ".txt"

    body = BODY_TEMPLATE.format(
        recipient_name=recipient,
        attachment_name=safe_filename,
    )

    msg = MIMEMultipart()
    msg["From"] = SENDER_EMAIL
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    att = MIMEText(md_content, "plain", "utf-8")
    att.add_header(
        "Content-Disposition", f"attachment; filename*=UTF-8''{safe_filename}"
    )
    msg.attach(att)

    logger.info(
        "email: sending to=%s subject=%s attachment=%s size=%d",
        to,
        subject,
        safe_filename,
        len(md_content),
    )
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.starttls()
            server.login(SENDER_EMAIL, password)
            server.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        return "ERROR: Gmail 认证失败，请检查 App Password 是否正确配置"
    except smtplib.SMTPConnectError:
        return "ERROR: 无法连接 Gmail SMTP 服务器 (smtp.gmail.com:587)，请检查网络"
    except Exception as e:
        logger.exception("email: send_failed to=%s", to)
        return f"ERROR: 邮件发送失败: {str(e)}"

    logger.info("email: sent to=%s", to)
    return f"邮件已成功发送至 {to}，附件: {safe_filename}"
