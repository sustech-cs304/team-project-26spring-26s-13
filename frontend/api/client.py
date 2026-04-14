"""
Frontend Relevant/api/client.py
封装所有后端 HTTP 调用，集中管理 API URL、认证 token 和错误处理。
所有网络调用必须通过此模块，不得在 widget/view 中直接使用 requests。
"""

from typing import Any

from frontend.api_client import BackendApiClient, BackendApiError


class APIError(Exception):
    """后端返回非 2xx 时抛出，携带 HTTP 状态码和错误信息。"""
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"API Error {status_code}: {detail}")


class APIClient:
    """
    同步 HTTP 客户端（适配 QThread 使用）。
    token 在登录后通过 set_token() 注入，后续请求自动附带 Authorization header。
    """

    def __init__(self) -> None:
        self._client = BackendApiClient.from_env()
        self._token: str | None = self._client.token

    def set_token(self, token: str) -> None:
        """登录成功后调用，设置 Bearer token。"""
        self._token = token
        self._client.set_token(token)

    def clear_token(self) -> None:
        """登出时调用，清除 token。"""
        self._token = None
        self._client.clear_token()

    # ── Auth ─────────────────────────────────────────────────────────────────

    def register(self, username: str, password: str, display_name: str, major: str) -> dict:
        """
        POST /api/auth/register

        Returns:
            dict with keys: user_id, display_name, major, token

        Raises:
            APIError: 400 username 已存在
        """
        return self._wrap_error(
            lambda: self._client.register(
                username=username,
                password=password,
                display_name=display_name,
                major=major,
            )
        )

    def login(self, username: str, password: str) -> dict:
        """
        POST /api/auth/login
        登录成功后自动调用 set_token()。

        Returns:
            dict with keys: user_id, display_name, major, token

        Raises:
            APIError: 401 认证失败
        """
        response = self._wrap_error(lambda: self._client.login(username=username, password=password))
        token = str(response.get("token", "")).strip()
        if token:
            self.set_token(token)
        return response

    def logout(self) -> None:
        """POST /api/auth/logout，然后清除本地 token。"""
        self._wrap_error(self._client.logout)
        self.clear_token()

    # ── Dashboard ────────────────────────────────────────────────────────────

    def get_bootstrap(self) -> dict:
        """
        GET /api/dashboard/bootstrap
        返回主界面初始化数据。

        Returns:
            dict with keys: user_profile, chat_history, materials, local_schedule

        Raises:
            APIError: 401 未认证
        """
        return self._wrap_error(self._client.bootstrap_dashboard)

    # ── Agent ────────────────────────────────────────────────────────────────

    def agent_run(
        self,
        session_id: str,
        user_id: str,
        message: str,
        attachments: list[dict] | None = None,
        hitl_reply: dict | None = None,
    ) -> dict:
        """
        POST /api/agent/run
        发送用户消息或 HITL 审批回传。

        Args:
            session_id:  当前会话 ID
            user_id:     当前用户 ID
            message:     用户消息（HITL 审批时可为空字符串）
            attachments: 附件引用列表（可选）
            hitl_reply:  HITL 审批结果（可选，格式 {"request_id": str, "approved": bool}）

        Returns:
            AgentResponse dict（含 assistant_message, trace, route, ui_payload,
                                hitl_request, error）

        Raises:
            APIError: 4xx/5xx
        """
        return self._wrap_error(
            lambda: self._client.run_agent(
                session_id=session_id,
                user_id=user_id,
                message=message,
                attachments=attachments or [],
                hitl_reply=hitl_reply,
            )
        )

    # ── Materials ────────────────────────────────────────────────────────────

    def list_materials(self) -> list[dict]:
        """GET /api/materials，返回用户教材列表。"""
        return self._wrap_error(self._client.list_materials)

    def upload_material(self, file_path: str) -> dict:
        """
        POST /api/materials/upload（multipart/form-data）
        上传并向量化教材文件。

        Args:
            file_path: 本地文件绝对路径

        Returns:
            MaterialInfo dict

        Raises:
            APIError: 400 不支持的格式，413 文件过大
        """
        return self._wrap_error(lambda: self._client.upload_material(file_path))

    def delete_material(self, file_id: str) -> None:
        """DELETE /api/materials/{file_id}"""
        self._wrap_error(lambda: self._client._request("DELETE", f"/api/materials/{file_id}"))

    # ── Schedule ─────────────────────────────────────────────────────────────

    def refresh_schedule(self) -> dict:
        """
        POST /api/schedule/refresh
        触发重新爬取日程，返回最新 ScheduleData。

        Returns:
            dict with keys: events, conflicts
        """
        return self._wrap_error(self._client.refresh_schedule)

    @staticmethod
    def _wrap_error(fn) -> Any:
        try:
            return fn()
        except BackendApiError as exc:
            message = str(exc)
            if message.startswith("HTTP "):
                prefix, _, detail = message.partition(": ")
                try:
                    status_code = int(prefix.split()[1])
                except (IndexError, ValueError):
                    status_code = 500
                raise APIError(status_code, detail or message) from exc
            raise APIError(500, message) from exc


# 全局单例，所有 widget/worker 直接 import 此对象
api_client = APIClient()
