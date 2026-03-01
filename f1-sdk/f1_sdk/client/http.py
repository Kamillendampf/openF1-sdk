from __future__ import annotations

from dataclasses import dataclass
from time import sleep
from typing import Any

from httpx import HTTPStatusError, Client

from .errors import OpenF1HTTPError
from .query import build_query


@dataclass(frozen=True)
class F1Config:
    base_url: str = "https://api.openf1.org/v1"
    timeout: float = 15.0
    rate_limit_enabled: bool = False
    pause_every_requests: int = 3
    pause_seconds: float = 2.0


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
            sleep(self.config.pause_seconds)

    def close(self):
        self.client.close()

    def get_list(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        q = build_query(params)

        self._maybe_wait_before_request()
        self._request_count += 1
        r = self.client.get(path, params=q)
        try:
            r.raise_for_status()
        except HTTPStatusError as exc:
            raise OpenF1HTTPError(str(exc), r.status_code, r.request, r) from exc

        data = r.json()
        if not isinstance(data, list):
            raise OpenF1HTTPError(f"Expected list JSON, got {type(data)}", r.status_code, r.request, r)
        return data
