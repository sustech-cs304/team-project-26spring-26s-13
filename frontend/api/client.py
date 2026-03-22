"""
frontend/api/client.py
封装所有后端 HTTP 调用，集中管理 API URL、认证 token 和错误处理。
所有网络调用必须通过此模块，不得在 widget/view 中直接使用 requests。
"""

import requests
from typing import Any

from frontend.config import API_BASE_URL


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
        self._token: str | None = None
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json"})

    def set_token(self, token: str) -> None:
        """登录成功后调用，设置 Bearer token。"""
        self._token = token
        self._session.headers.update({"Authorization": f"Bearer {token}"})

    def clear_token(self) -> None:
        """登出时调用，清除 token。"""
        self._token = None
        self._session.headers.pop("Authorization", None)

    # ── Auth ─────────────────────────────────────────────────────────────────

    def register(self, username: str, password: str, display_name: str, major: str) -> dict:
        """
        POST /api/auth/register

        Returns:
            dict with keys: user_id, display_name, major, token

        Raises:
            APIError: 400 username 已存在
        """
        # TODO: return self._post("/api/auth/register", {...})
        raise NotImplementedError

    def login(self, username: str, password: str) -> dict:
        """
        POST /api/auth/login
        登录成功后自动调用 set_token()。

        Returns:
            dict with keys: user_id, display_name, major, token

        Raises:
            APIError: 401 认证失败
        """
        # TODO:
        # resp = self._post("/api/auth/login", {"username": username, "password": password})
        # self.set_token(resp["token"])
        # return resp
        raise NotImplementedError

    def logout(self) -> None:
        """POST /api/auth/logout，然后清除本地 token。"""
        # TODO: self._post("/api/auth/logout", {}); self.clear_token()
        raise NotImplementedError

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
        # TODO: return self._get("/api/dashboard/bootstrap")
        raise NotImplementedError

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
        # TODO: return self._post("/api/agent/run", {...})
        raise NotImplementedError

    # ── Materials ────────────────────────────────────────────────────────────

    def list_materials(self) -> list[dict]:
        """GET /api/materials，返回用户教材列表。"""
        # TODO: return self._get("/api/materials")
        raise NotImplementedError

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
        # TODO:
        # with open(file_path, "rb") as f:
        #     return self._post_file("/api/materials/upload", f)
        raise NotImplementedError

    def delete_material(self, file_id: str) -> None:
        """DELETE /api/materials/{file_id}"""
        # TODO: self._delete(f"/api/materials/{file_id}")
        raise NotImplementedError

    # ── Schedule ─────────────────────────────────────────────────────────────

    def refresh_schedule(self) -> dict:
        """
        POST /api/schedule/refresh
        触发重新爬取日程，返回最新 ScheduleData。

        Returns:
            dict with keys: events, conflicts
        """
        # TODO: return self._post("/api/schedule/refresh", {})
        raise NotImplementedError

    # ── 内部 HTTP 方法 ────────────────────────────────────────────────────────

    def _get(self, path: str, params: dict | None = None) -> Any:
        resp = self._session.get(f"{API_BASE_URL}{path}", params=params)
        return self._handle(resp)

    def _post(self, path: str, body: dict) -> Any:
        resp = self._session.post(f"{API_BASE_URL}{path}", json=body)
        return self._handle(resp)

    def _post_file(self, path: str, file_obj) -> Any:
        headers = {k: v for k, v in self._session.headers.items() if k != "Content-Type"}
        resp = requests.post(f"{API_BASE_URL}{path}", files={"file": file_obj}, headers=headers)
        return self._handle(resp)

    def _delete(self, path: str) -> None:
        resp = self._session.delete(f"{API_BASE_URL}{path}")
        self._handle(resp)

    @staticmethod
    def _handle(resp: requests.Response) -> Any:
        if not resp.ok:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            raise APIError(resp.status_code, detail)
        if resp.status_code == 204:
            return None
        return resp.json()


# 全局单例，所有 widget/worker 直接 import 此对象
api_client = APIClient()
