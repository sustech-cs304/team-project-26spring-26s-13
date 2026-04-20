"""
backend/agent/core.py
Agent 单例与 AgentDeps 的定义。

抽离到独立文件以避免 loop.py ↔ tools/*.py 的循环导入：
  - loop.py 需要 import tools 来触发工具注册；
  - tools/*.py 需要 import agent 来使用 @agent.tool 装饰器；
  - 若两者都从 loop.py 导入则形成循环。
  解决方案：AgentDeps 和 agent 实例在本文件定义并完成初始化，
            loop.py 和 tools/*.py 均从这里导入，不再相互依赖。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.postgres import User
from backend.agent.prompt import SYSTEM_PROMPT
from backend.agent.tool_policy import prepare_tools_for_prompt
from backend.config import settings

@dataclass
class AgentDeps:
    """
    注入给所有工具函数的运行时依赖。
    工具通过 ctx.deps 访问这些字段，严禁工具直接持有全局状态。
    """
    db: AsyncSession
    user: User
    session_id: str
    llm_api_key: str          # 解密后的 DeepSeek API Key
    cas_account: str | None   # 解密后的 CAS 账号（爬虫工具使用）
    cas_password: str | None  # 解密后的 CAS 密码（爬虫工具使用）
    
    #[新增] 用于收集 Agent 的状态流转和工具调用轨迹，最终返回给前端 Thought Trace 面板
    trace_log: list[dict[str, Any]] = field(default_factory=list)


# [新增] 强制 LLM 的输出遵循此结构，从而实现自然语言与界面的联动 (Intelligent GUI)
class FinalResponse(BaseModel):
    """强制 LLM 输出的最终数据结构"""
    content: str = Field(
        description="回复给用户的自然语言内容。如果执行了操作，告诉用户结果；如果是提问，给出解答。"
    )
    route: str = Field(
        description="决定前端界面展示侧重哪个面板的路由。严格限于以下四个值: 'chat', 'scheduler', 'encyclopedia', 'os_automation'",
        pattern="^(chat|scheduler|encyclopedia|os_automation)$"
    )


def _make_agent() -> Agent[AgentDeps, FinalResponse]:
    """
    创建 PydanticAI Agent 实例。
    使用占位 API Key 初始化 model；运行时 run_agent() 会用用户自己的 Key 覆盖。
    DeepSeek 兼容 OpenAI API 格式，通过 base_url 切换。
    """
    provider = OpenAIProvider(
        base_url=settings.DEEPSEEK_BASE_URL,
        api_key="placeholder",   # 占位符；实际调用时在 run_agent() 中按用户替换
    )
    model = OpenAIModel(
        model_name=settings.DEEPSEEK_MODEL,
        provider=provider,
    )
    
    return Agent(
        model=model,
        deps_type=AgentDeps,
        output_type=FinalResponse,  # [修改] 从原本的 str 改为强制输出 FinalResponse 结构
        system_prompt=SYSTEM_PROMPT,
        prepare_tools=prepare_tools_for_prompt,
    )

# 模块加载时立即初始化，tools/*.py 的 @agent.tool 装饰器可在导入时正常注册。
agent: Agent[AgentDeps, FinalResponse] = _make_agent()
