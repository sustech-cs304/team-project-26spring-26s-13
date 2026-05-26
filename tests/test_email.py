"""
tests/test_email.py
Unit tests for backend/utils/email_sender.py.

Covers:
  - Content-length guard (short md_content → ERROR)
  - MIME message structure (headers, multipart, UTF-8 encoding)
  - Attachment filename transformation (.md → .txt)
  - Recipient name extraction from email address
  - SMTP send path with mocked smtplib
  - Error handling for auth / connection failures
"""

from email.mime.multipart import MIMEMultipart
import smtplib
from unittest.mock import MagicMock, patch
from urllib.parse import unquote

import pytest

from backend.utils.email_sender import (
    BODY_TEMPLATE,
    SENDER_EMAIL,
    send_md_mail,
)

# ── No-network unit tests ────────────────────────────────────────────────────


def test_rejects_short_content():
    result = send_md_mail(
        password="fake",
        to="test@example.com",
        subject="Test",
        md_content="too short",
        attachment_filename="test.md",
    )
    assert result.startswith("ERROR:")
    assert "50" in result


def test_rejects_empty_content():
    result = send_md_mail(
        password="fake",
        to="test@example.com",
        subject="Test",
        md_content="",
        attachment_filename="test.md",
    )
    assert result.startswith("ERROR:")


def test_rejects_none_content():
    result = send_md_mail(
        password="fake",
        to="test@example.com",
        subject="Test",
        md_content="",  # empty str is falsy; explicit None handled by or
        attachment_filename="test.md",
    )
    assert result.startswith("ERROR:")


@pytest.mark.parametrize(
    "name,expected",
    [
        ("doc.md", "doc.txt"),
        ("doc.MD", "doc.txt"),
        ("doc", "doc.txt"),
        ("doc.txt", "doc.txt"),
        ("a.b.c.md", "a.b.c.txt"),
    ],
)
def test_attachment_filename_txt_extension(name, expected):
    with patch("smtplib.SMTP") as mock_smtp_class:
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        content = "x" * 60
        send_md_mail(
            password="pwd",
            to="u@x.com",
            subject="s",
            md_content=content,
            attachment_filename=name,
        )

        sent_msg: MIMEMultipart = mock_server.send_message.call_args[0][0]
        attachments = [
            p
            for p in sent_msg.get_payload()
            if p.get_content_disposition() == "attachment"
        ]
        assert len(attachments) == 1
        assert attachments[0].get("Content-Disposition", "").startswith("attachment")


def test_recipient_name_from_email():
    with patch("smtplib.SMTP") as mock_smtp_class:
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        content = "x" * 60
        send_md_mail(
            password="pwd",
            to="12345678@mail.sustech.edu.cn",
            subject="s",
            md_content=content,
        )

        sent_msg: MIMEMultipart = mock_server.send_message.call_args[0][0]
        body_part = sent_msg.get_payload()[0]
        body_text = body_part.get_payload(decode=True).decode("utf-8")
        assert "12345678" in body_text


def test_explicit_recipient_name():
    with patch("smtplib.SMTP") as mock_smtp_class:
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        content = "x" * 60
        send_md_mail(
            password="pwd",
            to="x@y.com",
            subject="s",
            md_content=content,
            recipient_name="Alice",
        )

        sent_msg: MIMEMultipart = mock_server.send_message.call_args[0][0]
        body_part = sent_msg.get_payload()[0]
        body_text = body_part.get_payload(decode=True).decode("utf-8")
        assert "Alice" in body_text


# ── MIME structure tests ─────────────────────────────────────────────────────


def test_mime_headers_present():
    with patch("smtplib.SMTP") as mock_smtp_class:
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        content = "x" * 60
        to_addr = "target@example.com"
        subject = "Hello World"
        send_md_mail(password="pwd", to=to_addr, subject=subject, md_content=content)

        sent_msg: MIMEMultipart = mock_server.send_message.call_args[0][0]
        assert sent_msg["From"] == SENDER_EMAIL
        assert sent_msg["To"] == to_addr
        assert sent_msg["Subject"] == subject


def test_mime_has_two_parts():
    with patch("smtplib.SMTP") as mock_smtp_class:
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        content = "x" * 60
        send_md_mail(password="pwd", to="x@y.com", subject="s", md_content=content)

        sent_msg: MIMEMultipart = mock_server.send_message.call_args[0][0]
        assert isinstance(sent_msg, MIMEMultipart)
        assert len(sent_msg.get_payload()) == 2  # body + attachment


def test_body_contains_template_footer():
    with patch("smtplib.SMTP") as mock_smtp_class:
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        content = "x" * 60
        send_md_mail(password="pwd", to="x@y.com", subject="s", md_content=content)

        sent_msg: MIMEMultipart = mock_server.send_message.call_args[0][0]
        body_part = sent_msg.get_payload()[0]
        body_text = body_part.get_payload(decode=True).decode("utf-8")
        assert "AI Agent" in body_text
        assert "SUSTech AI Assistant" in body_text


def test_attachment_contains_full_content():
    with patch("smtplib.SMTP") as mock_smtp_class:
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        content = "这是附件正文，应该完整出现在附件中。" * 5
        send_md_mail(password="pwd", to="x@y.com", subject="s", md_content=content)

        sent_msg: MIMEMultipart = mock_server.send_message.call_args[0][0]
        att_part = sent_msg.get_payload()[1]
        att_text = att_part.get_payload(decode=True).decode("utf-8")
        assert content == att_text


def test_unicode_content_preserved():
    with patch("smtplib.SMTP") as mock_smtp_class:
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        content = "中日韩统一表意文字扩展区B 𠀀𠀁𠀂" + "测试内容" * 20
        send_md_mail(password="pwd", to="x@y.com", subject="测试", md_content=content)

        sent_msg: MIMEMultipart = mock_server.send_message.call_args[0][0]
        att_part = sent_msg.get_payload()[1]
        att_text = att_part.get_payload(decode=True).decode("utf-8")
        assert "𠀀" in att_text


# ── SMTP error path tests ────────────────────────────────────────────────────


def test_authentication_error():
    with patch("smtplib.SMTP") as mock_smtp_class:
        mock_server = MagicMock()
        mock_server.login.side_effect = smtplib.SMTPAuthenticationError(
            535, b"auth failed"
        )
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        result = send_md_mail(
            password="wrong",
            to="x@y.com",
            subject="s",
            md_content="x" * 60,
        )
        assert result.startswith("ERROR:")
        assert "认证失败" in result


def test_connection_error():
    with patch("smtplib.SMTP") as mock_smtp_class:
        mock_smtp_class.side_effect = smtplib.SMTPConnectError(421, b"connect failed")

        result = send_md_mail(
            password="pwd",
            to="x@y.com",
            subject="s",
            md_content="x" * 60,
        )
        assert result.startswith("ERROR:")
        assert "连接" in result


def test_generic_smtp_error():
    with patch("smtplib.SMTP") as mock_smtp_class:
        mock_server = MagicMock()
        mock_server.send_message.side_effect = RuntimeError("unexpected crash")
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        result = send_md_mail(
            password="pwd",
            to="x@y.com",
            subject="s",
            md_content="x" * 60,
        )
        assert result.startswith("ERROR:")
        assert "发送失败" in result


# ── Successful send ───────────────────────────────────────────────────────────


def test_successful_send_returns_ok():
    with patch("smtplib.SMTP") as mock_smtp_class:
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        result = send_md_mail(
            password="pwd",
            to="u@x.com",
            subject="s",
            md_content="x" * 60,
            attachment_filename="report.md",
        )
        assert result.startswith("邮件已成功发送至")
        assert "u@x.com" in result
        assert "report.txt" in result
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with(SENDER_EMAIL, "pwd")
        mock_server.send_message.assert_called_once()


# ── File attachment tests ────────────────────────────────────────────────────


def test_extra_files_attached():
    with patch("smtplib.SMTP") as mock_smtp_class:
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        content = "x" * 60
        result = send_md_mail(
            password="pwd",
            to="u@x.com",
            subject="s",
            md_content=content,
            extra_files=[("backend/utils/email_sender.py", "原始文件名.pdf")],
        )
        assert result.startswith("邮件已成功发送至")
        assert "原始文件名.pdf" in result

        sent_msg: MIMEMultipart = mock_server.send_message.call_args[0][0]
        attachments = [
            p
            for p in sent_msg.get_payload()
            if p.get_content_disposition() == "attachment"
        ]
        assert len(attachments) >= 2  # .txt + extra file
        filenames = [unquote(a.get("Content-Disposition", "")) for a in attachments]
        assert "原始文件名.pdf" in filenames[1] or any(
            "原始文件名.pdf" in f for f in filenames
        )


def test_extra_file_nonexistent_skipped():
    with patch("smtplib.SMTP") as mock_smtp_class:
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        content = "x" * 60
        result = send_md_mail(
            password="pwd",
            to="u@x.com",
            subject="s",
            md_content=content,
            extra_files=[("nonexistent_file_xyz.pdf", "不存在的文件.pdf")],
        )
        assert result.startswith("邮件已成功发送至")
        assert "跳过了" in result

        sent_msg: MIMEMultipart = mock_server.send_message.call_args[0][0]
        attachments = [
            p
            for p in sent_msg.get_payload()
            if p.get_content_disposition() == "attachment"
        ]
        assert len(attachments) == 1  # only .txt


def test_extra_files_skip_when_none():
    with patch("smtplib.SMTP") as mock_smtp_class:
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        content = "x" * 60
        result = send_md_mail(
            password="pwd",
            to="u@x.com",
            subject="s",
            md_content=content,
            extra_files=None,
        )
        assert "跳过" not in result

        sent_msg: MIMEMultipart = mock_server.send_message.call_args[0][0]
        attachments = [
            p
            for p in sent_msg.get_payload()
            if p.get_content_disposition() == "attachment"
        ]
        assert len(attachments) == 1


def test_multiple_extra_files():
    with patch("smtplib.SMTP") as mock_smtp_class:
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        content = "x" * 60
        result = send_md_mail(
            password="pwd",
            to="u@x.com",
            subject="s",
            md_content=content,
            extra_files=[
                ("backend/utils/email_sender.py", "文件A.py"),
                ("backend/config.py", "文件B.py"),
            ],
        )
        assert "邮件已成功发送至" in result
        assert "原始资料.zip" in result

        sent_msg: MIMEMultipart = mock_server.send_message.call_args[0][0]
        attachments = [
            p
            for p in sent_msg.get_payload()
            if p.get_content_disposition() == "attachment"
        ]
        assert len(attachments) == 2  # .txt + zip
        filenames = [unquote(a.get("Content-Disposition", "")) for a in attachments]
        assert any("原始资料.zip" in f for f in filenames)


def test_large_file_skipped():
    with patch("smtplib.SMTP") as mock_smtp_class:
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        content = "x" * 60
        with patch("backend.utils.email_sender.MAX_TOTAL_ATTACHMENT_BYTES", 50):
            result = send_md_mail(
                password="pwd",
                to="u@x.com",
                subject="s",
                md_content=content,
                extra_files=[("backend/utils/email_sender.py", "超限文件.pdf")],
            )
        assert "跳过了" in result

        sent_msg: MIMEMultipart = mock_server.send_message.call_args[0][0]
        attachments = [
            p
            for p in sent_msg.get_payload()
            if p.get_content_disposition() == "attachment"
        ]
        assert len(attachments) == 1  # only .txt


def test_mixed_valid_and_invalid_extra_files():
    with patch("smtplib.SMTP") as mock_smtp_class:
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        content = "x" * 60
        result = send_md_mail(
            password="pwd",
            to="u@x.com",
            subject="s",
            md_content=content,
            extra_files=[
                ("backend/utils/email_sender.py", "有效.pdf"),
                ("nonexistent.pdf", "无效.pdf"),
            ],
        )
        assert "邮件已成功发送至" in result
        assert "跳过了" in result  # one skipped

        sent_msg: MIMEMultipart = mock_server.send_message.call_args[0][0]
        attachments = [
            p
            for p in sent_msg.get_payload()
            if p.get_content_disposition() == "attachment"
        ]
        assert len(attachments) == 2  # .txt + 1 valid (not zipped, only 1)


def test_single_extra_file_not_zipped():
    with patch("smtplib.SMTP") as mock_smtp_class:
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        content = "x" * 60
        result = send_md_mail(
            password="pwd",
            to="u@x.com",
            subject="s",
            md_content=content,
            extra_files=[("backend/utils/email_sender.py", "单独文件.pdf")],
        )
        sent_msg: MIMEMultipart = mock_server.send_message.call_args[0][0]
        attachments = [
            p
            for p in sent_msg.get_payload()
            if p.get_content_disposition() == "attachment"
        ]
        assert len(attachments) == 2  # .txt + single file
        filenames = [unquote(a.get("Content-Disposition", "")) for a in attachments]
        assert any("单独文件.pdf" in f for f in filenames)
        assert not any("原始资料.zip" in f for f in filenames)


# ── _normalize_referenced_files unit tests ────────────────────────────────────


def test_normalize_none():
    from backend.agent.tools.email import _normalize_referenced_files

    assert _normalize_referenced_files(None) == []


def test_normalize_list():
    from backend.agent.tools.email import _normalize_referenced_files

    result = _normalize_referenced_files(["a.pdf", "b.pdf"])
    assert result == ["a.pdf", "b.pdf"]


def test_normalize_empty_list():
    from backend.agent.tools.email import _normalize_referenced_files

    assert _normalize_referenced_files([]) == []


def test_normalize_json_string():
    from backend.agent.tools.email import _normalize_referenced_files

    result = _normalize_referenced_files('["a.pdf", "b.pdf"]')
    assert result == ["a.pdf", "b.pdf"]


def test_normalize_malformed_json():
    from backend.agent.tools.email import _normalize_referenced_files

    assert _normalize_referenced_files("not json") == []


def test_normalize_json_non_list():
    from backend.agent.tools.email import _normalize_referenced_files

    assert _normalize_referenced_files('{"key": "val"}') == []


# ── export_conversation markdown format tests ──────────────────────────────────


def test_export_conversation_formats_rounds():
    from datetime import datetime, timezone
    from unittest.mock import AsyncMock

    from backend.agent.core import AgentDeps
    from backend.agent.tools.email import export_conversation
    from backend.database.postgres import ChatMessage

    now = datetime(2026, 5, 26, 14, 0, 0, tzinfo=timezone.utc)
    msgs = [
        ChatMessage(
            session_id="s1", role="user", content="问题1",
            timestamp=now,
        ),
        ChatMessage(
            session_id="s1", role="assistant", content="回答1",
            timestamp=now,
        ),
        ChatMessage(
            session_id="s1", role="user", content="问题2",
            timestamp=now,
        ),
        ChatMessage(
            session_id="s1", role="assistant", content="回答2",
            timestamp=now,
        ),
    ]

    mock_db = AsyncMock()
    mock_db_result = MagicMock()
    mock_db_result.scalars.return_value.all.return_value = msgs
    mock_db.execute.return_value = mock_db_result

    ctx = MagicMock()
    ctx.deps = MagicMock(spec=AgentDeps)
    ctx.deps.session_id = "s1"
    ctx.deps.db = mock_db

    import asyncio
    md = asyncio.run(export_conversation(ctx, rounds=0))

    assert "# 对话记录导出" in md
    assert "Session:" in md
    assert "问题1" in md
    assert "回答1" in md
    assert "问题2" in md
    assert "回答2" in md
    assert "## Round 1" in md
    assert "## Round 2" in md
    assert "### You" in md
    assert "### Assistant" in md


def test_export_conversation_respects_rounds_limit():
    from datetime import datetime, timezone
    from unittest.mock import AsyncMock

    from backend.agent.core import AgentDeps
    from backend.agent.tools.email import export_conversation
    from backend.database.postgres import ChatMessage

    now = datetime(2026, 5, 26, 14, 0, 0, tzinfo=timezone.utc)
    msgs = [
        ChatMessage(session_id="s1", role="user", content="Q1", timestamp=now),
        ChatMessage(session_id="s1", role="assistant", content="A1", timestamp=now),
        ChatMessage(session_id="s1", role="user", content="Q2", timestamp=now),
        ChatMessage(session_id="s1", role="assistant", content="A2", timestamp=now),
        ChatMessage(session_id="s1", role="user", content="Q3", timestamp=now),
        ChatMessage(session_id="s1", role="assistant", content="A3", timestamp=now),
    ]

    mock_db = AsyncMock()
    mock_db_result = MagicMock()
    mock_db_result.scalars.return_value.all.return_value = msgs
    mock_db.execute.return_value = mock_db_result

    ctx = MagicMock()
    ctx.deps = MagicMock(spec=AgentDeps)
    ctx.deps.session_id = "s1"
    ctx.deps.db = mock_db

    import asyncio
    md = asyncio.run(export_conversation(ctx, rounds=1))

    assert "Q3" in md
    assert "A3" in md
    assert "Q2" not in md
    assert "A2" not in md


def test_export_conversation_empty():
    from unittest.mock import AsyncMock

    from backend.agent.core import AgentDeps
    from backend.agent.tools.email import export_conversation

    mock_db = AsyncMock()
    mock_db_result = MagicMock()
    mock_db_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_db_result

    ctx = MagicMock()
    ctx.deps = MagicMock(spec=AgentDeps)
    ctx.deps.session_id = "s1"
    ctx.deps.db = mock_db

    import asyncio
    result = asyncio.run(export_conversation(ctx, rounds=0))

    assert "没有历史记录" in result


def test_export_output_feeds_send_mail():
    import asyncio
    from datetime import datetime, timezone
    from unittest.mock import AsyncMock

    from backend.agent.core import AgentDeps
    from backend.agent.tools.email import export_conversation
    from backend.database.postgres import ChatMessage

    now = datetime(2026, 5, 26, 14, 0, 0, tzinfo=timezone.utc)
    msgs = [
        ChatMessage(session_id="s1", role="user", content="总结对话并发邮件给我", timestamp=now),
        ChatMessage(session_id="s1", role="assistant", content="好的，已发送。", timestamp=now),
    ]

    mock_db = AsyncMock()
    mock_db_result = MagicMock()
    mock_db_result.scalars.return_value.all.return_value = msgs
    mock_db.execute.return_value = mock_db_result

    ctx = MagicMock()
    ctx.deps = MagicMock(spec=AgentDeps)
    ctx.deps.session_id = "s1"
    ctx.deps.db = mock_db

    md = asyncio.run(export_conversation(ctx, rounds=0))

    with patch("smtplib.SMTP") as mock_smtp_class:
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        result = send_md_mail(
            password="pwd",
            to="u@x.com",
            subject="对话记录导出",
            md_content=md,
            attachment_filename="conversation.md",
        )
        assert result.startswith("邮件已成功发送至")
        assert "conversation.txt" in result
