"""
backend/utils/email_sender.py
Gmail SMTP 发信模块。
通过 App Password 认证发送邮件，正文为简短引导语，完整内容以纯文本附件发送。
支持附带知识库中的原始资料文件（PDF 等）。
"""

import io
import logging
import smtplib
import zipfile
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from urllib.parse import quote

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "fasheng087@gmail.com"
MAX_TOTAL_ATTACHMENT_BYTES = 25 * 1024 * 1024  # Gmail 限制 25 MB

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
    extra_files: list[tuple[str, str]] | None = None,
) -> str:
    if not md_content or len(md_content.strip()) < 50:
        return "ERROR: md_content 太短（少于50字）。请将完整的回答内容传入 md_content 参数，而非只写标题。"

    recipient = recipient_name or to.split("@")[0]

    safe_filename = attachment_filename
    if not safe_filename.endswith(".txt"):
        safe_filename = attachment_filename.rsplit(".", 1)[0] + ".txt"

    attached_files: list[str] = [safe_filename]
    skipped_files: list[str] = []
    valid_extra: list[tuple[Path, str]] = []
    total_bytes = len(md_content.encode("utf-8"))

    if extra_files:
        for fp_str, display_name in extra_files:
            fp = Path(fp_str)
            if not fp.is_file():
                logger.warning("email: file_not_found path=%s", fp_str)
                skipped_files.append(display_name)
                continue
            fsize = fp.stat().st_size
            if total_bytes + fsize > MAX_TOTAL_ATTACHMENT_BYTES:
                logger.warning(
                    "email: file_too_large name=%s size=%d", display_name, fsize
                )
                skipped_files.append(display_name)
                continue
            total_bytes += fsize
            valid_extra.append((fp, display_name))

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
        "Content-Disposition",
        f"attachment; filename*=UTF-8''{quote(safe_filename.encode('utf-8'))}",
    )
    msg.attach(att)

    if len(valid_extra) >= 2:
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for fp, display_name in valid_extra:
                zf.write(str(fp), display_name)
        zip_bytes = zip_buf.getvalue()
        zip_display = "原始资料.zip"
        mime_extra = MIMEApplication(zip_bytes, _subtype="octet-stream")
        mime_extra.add_header(
            "Content-Disposition",
            f"attachment; filename*=UTF-8''{quote(zip_display.encode('utf-8'))}",
        )
        msg.attach(mime_extra)
        attached_files.append(zip_display)
    else:
        for fp, display_name in valid_extra:
            mime_extra = MIMEApplication(fp.read_bytes(), _subtype="octet-stream")
            mime_extra.add_header(
                "Content-Disposition",
                f"attachment; filename*=UTF-8''{quote(display_name.encode('utf-8'))}",
            )
            msg.attach(mime_extra)
            attached_files.append(display_name)

    skipped_note = ""
    if skipped_files:
        skipped_note = f"（跳过了 {len(skipped_files)} 个过大或不存在的文件）"

    logger.info(
        "email: sending to=%s subject=%s attachments=%d size=%d%s",
        to,
        subject,
        len(attached_files),
        total_bytes,
        f" skipped={len(skipped_files)}" if skipped_files else "",
    )
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=60) as server:
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
    result = f"邮件已成功发送至 {to}，附件: {', '.join(attached_files)}"
    if skipped_note:
        result += f" {skipped_note}"
    return result
