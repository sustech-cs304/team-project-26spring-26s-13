"""REST client helpers for the Student Productivity Agent desktop Frontend Relevant."""

from __future__ import annotations

import json
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request
from uuid import uuid4


class BackendApiError(RuntimeError):
    """Raised when the REST backend cannot be reached or returns invalid data."""


@dataclass
class BackendApiClient:
    base_url: str | None = None
    timeout: float = 8.0
    token: str | None = None

    @classmethod
    def from_env(cls) -> "BackendApiClient":
        base_url = os.getenv("SPA_API_BASE_URL", "").strip().rstrip("/")
        timeout_text = os.getenv("SPA_API_TIMEOUT", "8").strip()
        token = os.getenv("SPA_API_TOKEN", "").strip()
        try:
            timeout = float(timeout_text)
        except ValueError:
            timeout = 8.0
        return cls(base_url=base_url or None, timeout=timeout, token=token or None)

    @property
    def enabled(self) -> bool:
        return bool(self.base_url)

    @property
    def authenticated(self) -> bool:
        return bool(self.token)

    def set_token(self, token: str) -> None:
        self.token = token.strip() or None

    def clear_token(self) -> None:
        self.token = None

    def login(self, username: str, password: str) -> dict[str, Any]:
        payload = self._request(
            "POST",
            "/api/auth/login",
            json_body={"username": username, "password": password},
        )
        if not isinstance(payload, dict):
            raise BackendApiError("Login response must be a JSON object.")
        token = str(payload.get("token", "")).strip()
        if token:
            self.set_token(token)
        return payload

    def register(self, username: str, password: str, display_name: str, major: str) -> dict[str, Any]:
        payload = self._request(
            "POST",
            "/api/auth/register",
            json_body={
                "username": username,
                "password": password,
                "display_name": display_name,
                "major": major,
            },
        )
        if not isinstance(payload, dict):
            raise BackendApiError("Register response must be a JSON object.")
        token = str(payload.get("token", "")).strip()
        if token:
            self.set_token(token)
        return payload

    def logout(self) -> None:
        if not self.enabled:
            self.clear_token()
            return
        try:
            self._request("POST", "/api/auth/logout", json_body={})
        finally:
            self.clear_token()

    def bootstrap_dashboard(self) -> dict[str, Any]:
        payload = self._request("GET", "/api/dashboard/bootstrap")
        if not isinstance(payload, dict):
            raise BackendApiError("Dashboard bootstrap response must be a JSON object.")
        return payload

    def update_credentials(
        self,
        *,
        cas_account: str | None = None,
        cas_password: str | None = None,
        llm_api_key: str | None = None,
    ) -> None:
        body = {
            "cas_account": cas_account,
            "cas_password": cas_password,
            "llm_api_key": llm_api_key,
        }
        self._request("PUT", "/api/user/credentials", json_body=body)

    def list_materials(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/api/materials")
        if not isinstance(payload, list):
            raise BackendApiError("Materials response must be a JSON array.")
        return [item for item in payload if isinstance(item, dict)]

    def upload_material(self, file_path: str) -> dict[str, Any]:
        file_name = Path(file_path).name
        mime_type = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
        with open(file_path, "rb") as file_obj:
            file_bytes = file_obj.read()
        payload = self._request(
            "POST",
            "/api/materials/upload",
            file_upload={
                "field_name": "file",
                "file_name": file_name,
                "content_type": mime_type,
                "content": file_bytes,
            },
        )
        if not isinstance(payload, dict):
            raise BackendApiError("Upload response must be a JSON object.")
        return payload

    def run_agent(
        self,
        *,
        user_id: str,
        session_id: str,
        message: str,
        attachments: list[dict[str, Any]] | None = None,
        hitl_reply: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = self._request(
            "POST",
            "/api/agent/run",
            json_body={
                "user_id": user_id,
                "session_id": session_id,
                "message": message,
                "attachments": attachments or [],
                "hitl_reply": hitl_reply,
            },
        )
        if not isinstance(payload, dict):
            raise BackendApiError("Agent response must be a JSON object.")
        return payload

    def list_sessions(self) -> list[dict[str, Any]]:
        payload = self._request("GET", "/api/agent/sessions")
        if not isinstance(payload, list):
            raise BackendApiError("Sessions response must be a JSON array.")
        return [item for item in payload if isinstance(item, dict)]

    def delete_session(self, session_id: str) -> None:
        self._request("DELETE", f"/api/agent/sessions/{session_id}")

    def refresh_schedule(self) -> dict[str, Any]:
        payload = self._request("POST", "/api/schedule/refresh", json_body={})
        if not isinstance(payload, dict):
            raise BackendApiError("Schedule response must be a JSON object.")
        return payload

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        file_upload: dict[str, Any] | None = None,
    ) -> Any:
        if not self.enabled or not self.base_url:
            raise BackendApiError("REST backend is disabled. Set SPA_API_BASE_URL to enable it.")

        url = f"{self.base_url}{path}"
        headers = {"Accept": "application/json"}
        if self.authenticated and self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        data: bytes | None = None
        if file_upload is not None:
            content_type, data = self._encode_multipart(file_upload)
            headers["Content-Type"] = content_type
        elif json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = request.Request(url, data=data, headers=headers, method=method)

        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                body = response.read().decode("utf-8", errors="ignore")
        except error.HTTPError as exc:
            detail = self._parse_http_error(exc)
            raise BackendApiError(f"HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise BackendApiError(f"Network error: {exc.reason}") from exc

        if not body.strip():
            return None

        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise BackendApiError("Backend response was not valid JSON.") from exc

    @staticmethod
    def _parse_http_error(exc: error.HTTPError) -> str:
        raw = exc.read().decode("utf-8", errors="ignore").strip()
        if not raw:
            return str(exc.reason)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return raw
        if isinstance(payload, dict):
            detail = payload.get("detail")
            if isinstance(detail, str):
                return detail
            if detail is not None:
                return json.dumps(detail, ensure_ascii=False)
        return raw

    @staticmethod
    def _encode_multipart(file_upload: dict[str, Any]) -> tuple[str, bytes]:
        boundary = f"----SPAFormBoundary{uuid4().hex}"
        field_name = str(file_upload["field_name"])
        file_name = str(file_upload["file_name"])
        content_type = str(file_upload.get("content_type") or "application/octet-stream")
        content = bytes(file_upload["content"])

        parts: list[bytes] = [
            f"--{boundary}\r\n".encode("utf-8"),
            (
                f'Content-Disposition: form-data; name="{field_name}"; filename="{file_name}"\r\n'
            ).encode("utf-8"),
            f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
            content,
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
        return f"multipart/form-data; boundary={boundary}", b"".join(parts)
