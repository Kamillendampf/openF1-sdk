from __future__ import annotations

from dataclasses import dataclass
import logging
from time import sleep
from typing import Any, Callable, Optional

from httpx import HTTPStatusError, Client

from .errors import OpenF1HTTPError
from .query import build_query

TokenProvider = Callable[[bool], Optional[str]]
LOGGER = logging.getLogger("openf1.http")


@dataclass(frozen=True)
class F1Config:
    base_url: str = "https://api.openf1.org/v1"
    timeout: float = 15.0
    rate_limit_enabled: bool = False
    pause_every_requests: int = 3
    pause_seconds: float = 2.0
    access_token: str | None = None
    token_provider: TokenProvider | None = None


class HttpClient:
    def __init__(self, config: F1Config):
        self.config = config
        self._request_count = 0
        self.client = Client(
            base_url=config.base_url,
            timeout=config.timeout,
        )

    def _maybe_wait_before_request(self) -> None:
        if not self.config.rate_limit_enabled:
            return
        if self.config.pause_every_requests <= 0:
            return
        if self.config.pause_seconds <= 0:
            return
        if self._request_count > 0 and self._request_count % self.config.pause_every_requests == 0:
            LOGGER.debug(
                "Rate-limit pause before request (request_count=%d, pause_seconds=%s).",
                self._request_count,
                self.config.pause_seconds,
            )
            sleep(self.config.pause_seconds)

    def close(self):
        self.client.close()

    def _get_access_token(self, force_refresh: bool = False) -> str | None:
        provider = self.config.token_provider
        if provider is not None:
            token = provider(force_refresh)
            return token if token else None

        token = self.config.access_token
        return token if token else None

    def _build_auth_headers(self, force_refresh: bool = False) -> dict[str, str]:
        token = self._get_access_token(force_refresh=force_refresh)
        if not token:
            return {}
        return {"Authorization": f"Bearer {token}"}

    def _send_get(
        self,
        path: str,
        query: dict[str, str],
        headers: dict[str, str],
    ):
        self._maybe_wait_before_request()
        self._request_count += 1
        has_auth = "Authorization" in headers
        LOGGER.debug("HTTP GET %s (auth=%s, params=%d).", path, has_auth, len(query))
        response = self.client.get(path, params=query, headers=headers or None)
        LOGGER.debug("HTTP GET %s -> %d", path, response.status_code)
        return response

    def get_list(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        q = build_query(params)

        headers = self._build_auth_headers(force_refresh=False)
        r = self._send_get(path=path, query=q, headers=headers)

        if r.status_code == 401 and self.config.token_provider is not None:
            LOGGER.warning("HTTP GET %s returned 401, retrying with refreshed token.", path)
            refreshed_headers = self._build_auth_headers(force_refresh=True)
            if refreshed_headers:
                r = self._send_get(path=path, query=q, headers=refreshed_headers)

        try:
            r.raise_for_status()
        except HTTPStatusError as exc:
            LOGGER.error("HTTP GET %s failed with status %d.", path, r.status_code)
            raise OpenF1HTTPError(str(exc), r.status_code, r.request, r) from exc

        data = r.json()
        if not isinstance(data, list):
            raise OpenF1HTTPError(f"Expected list JSON, got {type(data)}", r.status_code, r.request, r)
        LOGGER.debug("HTTP GET %s returned %d rows.", path, len(data))
        return data
