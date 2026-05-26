"""
backend/agent/tools/email.py
邮件工具：发送 Markdown 附件邮件 + 导出对话记录。
"""

import json
from pathlib import Path

from pydantic_ai import RunContext
from sqlalchemy import select

from backend.agent.core import AgentDeps, agent
from backend.config import settings
from backend.database.postgres import ChatMessage
from backend.utils.email_sender import send_md_mail


@agent.tool
async def send_email(
    ctx: RunContext[AgentDeps],
    subject: str,
    md_content: str,
    attachment_filename: str = "summary.md",
) -> str:
    """
    发送邮件到用户的学校邮箱。

    调用条件（以下任一触发）：
      - 用户说"发邮件""用邮件""email me""mail to me""以邮件形式""via email"
      - 用户说"发送给我""send to me" 且对话涉及总结、课程信息、文件内容

    工作流程：
      1. LLM 先用其他工具（query_rag、scheduler 等）生成完整回答
      2. 将完整回答整理为文字内容，传给 md_content
      3. 邮件正文自动提取前 400 字作为摘要预览
      4. 完整内容以纯文本附件 (.txt) 发送

    Args:
        subject:  邮件主题（中英文均可，如"中国C9高校名单"）
        md_content: 【重要】你刚刚生成给用户的完整回答。
                    不要只写标题或一行摘要，必须包含全部内容。
                    这就是邮件附件的全部正文。最少 50 字。
        attachment_filename: 附件文件名，如 "C9高校名单.md"

    Returns:
        "邮件已成功发送至 xxx@mail.sustech.edu.cn" 或 "ERROR: ..."
    """
    password = settings.GMAIL_APP_PASSWORD
    if not password:
        return (
            "ERROR: Gmail App Password 未配置。"
            "请联系管理员在服务器环境变量中设置 GMAIL_APP_PASSWORD。"
        )

    cas_id = (ctx.deps.user.cas_account or "").strip()
    if not cas_id:
        return (
            "ERROR: 未找到您的学号（CAS 账号）。"
            "请先在设置页面绑定 CAS 账号后再使用邮件功能。"
        )

    to = f"{cas_id}@mail.sustech.edu.cn"
    if not attachment_filename.endswith(".md"):
        attachment_filename = attachment_filename + ".md"

    result = send_md_mail(
        password=password,
        to=to,
        subject=subject,
        md_content=md_content,
        attachment_filename=attachment_filename,
        recipient_name=cas_id,
    )
    return result


@agent.tool
async def export_conversation(
    ctx: RunContext[AgentDeps],
    rounds: int = 0,
) -> str:
    """
    导出当前对话记录为 Markdown 文本。

    调用条件：
      - 用户说"导出对话""导出聊天""export conversation""导出所有对话"
      - 用户说"把刚才的对话发给我"
      - 配合 send_email 使用

    Args:
        rounds: 导出最近几轮对话。0 或负数表示导出全部。
               每轮 = user 消息 + assistant 回复。

    Returns:
        格式化的 Markdown 字符串，每轮对话格式为：

        ## Round N
        ### You
        用户消息内容
        ### Assistant
        助手回复内容
    """
    session_id = ctx.deps.session_id
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.timestamp.asc())
    )
    result = await ctx.deps.db.execute(stmt)
    messages = list(result.scalars().all())

    if not messages:
        return "当前对话没有历史记录。"

    user_msgs: list[tuple[int, str]] = []
    assistant_msgs: list[tuple[int, str]] = []
    for m in messages:
        if m.role == "user":
            user_msgs.append((len(user_msgs) + 1, m.content))
        elif m.role == "assistant":
            assistant_msgs.append((len(assistant_msgs) + 1, m.content))

    total_rounds = min(len(user_msgs), len(assistant_msgs))
    if rounds <= 0:
        export_start = 0
    else:
        export_start = max(0, total_rounds - rounds)

    md_lines: list[str] = [
        "# 对话记录导出",
        "",
        f"- Session: {session_id[:16]}...",
        f"- 总轮数: {total_rounds}",
        f"- 导出轮数: {total_rounds - export_start}",
        "",
    ]

    for idx in range(export_start, total_rounds):
        round_num = idx + 1
        u_content = user_msgs[idx][1] if idx < len(user_msgs) else "(缺失)"
        a_content = assistant_msgs[idx][1] if idx < len(assistant_msgs) else "(缺失)"
        md_lines.append(f"## Round {round_num}")
        md_lines.append("### You")
        md_lines.append(u_content)
        md_lines.append("")
        md_lines.append("### Assistant")
        md_lines.append(a_content)
        md_lines.append("")

    return "\n".join(md_lines)
