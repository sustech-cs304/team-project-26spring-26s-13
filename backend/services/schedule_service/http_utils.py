import asyncio

import httpx

from .log_utils import _bb_sink_add, get_trace_id, is_diag_mode, logger

_HTTP_TIMEOUT = 60.0


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
    timeout: float | None = None,
) -> httpx.Response:
    import time as _time

    _t0 = _time.monotonic()
    max_attempts = 3
    tid = get_trace_id()
    effective_timeout = timeout or _HTTP_TIMEOUT
    for attempt in range(1, max_attempts + 1):
        try:
            response = await asyncio.wait_for(
                client.request(
                    method, url, headers=headers, content=content, data=data
                ),
                timeout=effective_timeout,
            )
        except asyncio.TimeoutError:
            logger.error(
                "bb.http: timeout attempt=%d/%d method=%s url=%s label=%s timeout=%.0fs trace=%s",
                attempt,
                max_attempts,
                method,
                url,
                label,
                effective_timeout,
                tid,
            )
            if attempt >= max_attempts:
                raise httpx.TimeoutException(
                    f"Request timeout after {attempt} attempts ({effective_timeout}s each)"
                )
            await asyncio.sleep(_backoff_seconds(attempt))
            continue
        except httpx.HTTPError as exc:
            logger.exception(
                "bb.http: error attempt=%d/%d method=%s url=%s label=%s err=%s trace=%s",
                attempt,
                max_attempts,
                method,
                url,
                label,
                _request_error_summary(exc),
                tid,
            )
            if attempt >= max_attempts:
                raise
            await asyncio.sleep(_backoff_seconds(attempt))
            continue

        if label:
            _bb_sink_add(label, response)

        elapsed = _time.monotonic() - _t0
        if elapsed > 3.0:
            logger.debug(
                "bb.http: slow_req method=%s url=%s label=%s elapsed=%.1fs status=%d size=%d trace=%s",
                method,
                url[:120],
                label,
                elapsed,
                response.status_code,
                len(response.content),
                tid,
            )

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
