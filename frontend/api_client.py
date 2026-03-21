"""REST client helpers for the Student Productivity Agent desktop frontend."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib import error, parse, request


class BackendApiError(RuntimeError):
    """Raised when the REST backend cannot be reached or returns invalid data."""


@dataclass
class BackendApiClient:
    base_url: str | None = None
    timeout: float = 8.0
    api_key: str | None = None

    @classmethod
    def from_env(cls) -> "BackendApiClient":
        base_url = os.getenv("SPA_API_BASE_URL", "").strip().rstrip("/")
        api_key = os.getenv("SPA_API_KEY", "").strip()
        timeout_text = os.getenv("SPA_API_TIMEOUT", "8").strip()
        try:
            timeout = float(timeout_text)
        except ValueError:
            timeout = 8.0
        return cls(base_url=base_url or None, timeout=timeout, api_key=api_key or None)

    @property
    def enabled(self) -> bool:
        return bool(self.base_url)

    def bootstrap_dashboard(self, user_id: str) -> dict[str, Any]:
        return self._request("GET", "/api/dashboard/bootstrap", params={"user_id": user_id})

    def run_agent(
        self,
        *,
        user_id: str,
        session_id: str,
        message: str,
        active_tab: str,
        selected_feature: str,
        attachments: list[dict[str, Any]] | None = None,
        hitl_reply: dict[str, Any] | None = None,
        connection_settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "user_id": user_id,
            "session_id": session_id,
            "message": message,
            "attachments": attachments or [],
            "context": {
                "active_tab": active_tab,
                "selected_feature": selected_feature,
            },
            "hitl_reply": hitl_reply,
            "connection_settings": connection_settings,
        }
        return self._request("POST", "/api/agent/run", json_body=payload)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.enabled or not self.base_url:
            raise BackendApiError("REST backend is disabled. Set SPA_API_BASE_URL to enable it.")

        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{parse.urlencode(params)}"

        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        data: bytes | None = None
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = request.Request(url, data=data, headers=headers, method=method)

        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                body = response.read().decode("utf-8") or "{}"
        except error.HTTPError as exc:
            message = exc.read().decode("utf-8", errors="ignore").strip()
            detail = message or exc.reason
            raise BackendApiError(f"HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise BackendApiError(f"Network error: {exc.reason}") from exc

        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise BackendApiError("Backend response was not valid JSON.") from exc

        if not isinstance(payload, dict):
            raise BackendApiError("Backend response must be a JSON object.")
        return payload
