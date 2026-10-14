"""Shared anonymous async HTTP client for the Tapsi Food API.

Every tool goes through `fetch`, which performs a plain GET against
https://api.tapsi.food, caps concurrency and turns HTTP failures into
`ApiError` messages the model can act on. No auth, cookies, signed headers
or extra client params are sent.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

import httpx
from mcp.server.mcpserver.exceptions import ToolError

API_BASE = "https://api.tapsi.food"
API_HOST = "api.tapsi.food"

HEADERS = {
    "User-Agent": "tapsi-food-mcp (anonymous read-only client)",
    "Accept": "application/json",
}

TIMEOUT = 20.0
MAX_CONCURRENCY = 4

_transport: httpx.AsyncBaseTransport | None = None
_client: httpx.AsyncClient | None = None
_limit: asyncio.Semaphore | None = None


class ApiError(ToolError):
    """A failed upstream call. `status` is the HTTP status, or None for network errors."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def set_transport(transport: httpx.AsyncBaseTransport | None) -> None:
    """Swap the transport (tests use httpx.MockTransport). Drops the current client."""
    global _transport, _client, _limit
    _transport, _client, _limit = transport, None, None


def _get_client() -> tuple[httpx.AsyncClient, asyncio.Semaphore]:
    global _client, _limit
    if _client is None:
        _client = httpx.AsyncClient(
            transport=_transport,
            headers=HEADERS,
            timeout=TIMEOUT,
            follow_redirects=True,
        )
        _limit = asyncio.Semaphore(MAX_CONCURRENCY)
    assert _limit is not None
    return _client, _limit


async def fetch(path: str, *, params: Mapping[str, object] | None = None) -> Any:
    """GET a path relative to the Tapsi Food API base and return the decoded JSON body.

    `None` param values are dropped so unset optionals stay out of the query
    string. The envelope is returned unchanged; each tool normalizes its own
    response. GET is the only method; there is no login, cart or order API here.
    """
    client, limit = _get_client()
    url = API_BASE + (path if path.startswith("/") else "/" + path)
    query: dict[str, Any] = {k: v for k, v in (params or {}).items() if v is not None}
    try:
        async with limit:
            r = await client.get(url, params=query)
    except httpx.TimeoutException as e:
        raise ApiError(f"{API_HOST} did not answer in time. Try again in a moment.") from e
    except httpx.RequestError as e:
        raise ApiError(f"Could not reach {API_HOST} ({type(e).__name__}). Check the internet connection.") from e

    if r.status_code >= 400:
        raise ApiError(_status_message(r), r.status_code)
    try:
        body = r.json()
    except ValueError as e:
        raise ApiError(f"{API_HOST} returned a non-JSON response (HTTP {r.status_code}).", r.status_code) from e
    if isinstance(body, dict) and body.get("status") is False:
        raise ApiError(f"{API_HOST} rejected the request: {_error_text(body)}", r.status_code)
    return body


def _status_message(r: httpx.Response) -> str:
    code = r.status_code
    if code == 404:
        return (
            f"Not found at {API_HOST} (HTTP 404). The catalog page or item does not exist "
            "at these coordinates: the point may be outside Tapsi Food's served coverage "
            "(Tehran, Mashhad and Shiraz observed 2026-10-14). Do not treat this as an empty list."
        )
    if code == 429:
        return f"{API_HOST} is rate limiting requests (HTTP 429). Wait a minute before retrying; do not fan out."
    if code >= 500:
        return f"{API_HOST} had a server error (HTTP {code}). Try again later."
    try:
        detail = _error_text(r.json())
    except ValueError:
        detail = r.text[:200]
    return f"{API_HOST} rejected the request (HTTP {code}): {detail}"


def _error_text(body: Any) -> str:
    if isinstance(body, dict):
        err = body.get("error") or body.get("message") or body.get("errors") or body
        if isinstance(err, dict):
            err = err.get("message") or err.get("msg") or err
        return str(err)[:300]
    return str(body)[:300]
