import asyncio

import httpx

from .log_utils import _bb_sink_add, logger


def _is_retryable_status(status_code: int) -> bool:
    return status_code == 429 or 500 <= status_code <= 599


def _backoff_seconds(attempt: int) -> float:
    return 0.5 * (2 ** (attempt - 1))


def _request_error_summary(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


async def _request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    content: str | bytes | None = None,
    data: dict | None = None,
    label: str = "",
) -> httpx.Response:
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            response = await client.request(method, url, headers=headers, content=content, data=data)
        except httpx.HTTPError as exc:
            logger.exception(
                "bb.http: error attempt=%d/%d method=%s url=%s label=%s err=%s",
                attempt,
                max_attempts,
                method,
                url,
                label,
                _request_error_summary(exc),
            )
            if attempt >= max_attempts:
                raise
            await asyncio.sleep(_backoff_seconds(attempt))
            continue

        if label:
            _bb_sink_add(label, response)

        if _is_retryable_status(response.status_code):
            logger.warning(
                "bb.http: retry attempt=%d/%d status=%d method=%s url=%s label=%s",
                attempt,
                max_attempts,
                response.status_code,
                method,
                url,
                label,
            )
            if attempt >= max_attempts:
                return response
            await asyncio.sleep(_backoff_seconds(attempt))
            continue

        return response

    raise RuntimeError("unreachable")
