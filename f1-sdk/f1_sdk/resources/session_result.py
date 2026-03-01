from __future__ import annotations

from typing import Any, Mapping

from ..Models import SessionResult
from ..client.http import HttpClient

from .base import ModelResource


class SessionResultResource(ModelResource[SessionResult]):
    def __init__(self, http: HttpClient):
        super().__init__(http, "/session_result", SessionResult, latest_param="session_key")

    def all(
        self,
        *,
        session_key: int | str | None = None,
        meeting_key: int | str | None = None,
        driver_number: int | None = None,
        position: int | None = None,
        dnf: bool | None = None,
        dns: bool | None = None,
        dsq: bool | None = None,
        params: Mapping[str, Any] | None = None,
        **filters: Any,
    ) -> list[SessionResult]:
        query = self._compact(
            {
                "session_key": session_key,
                "meeting_key": meeting_key,
                "driver_number": driver_number,
                "position": position,
                "dnf": dnf,
                "dns": dns,
                "dsq": dsq,
            }
        )
        query.update(filters)
        return super().all(params=params, **query)

    def latest(
        self,
        *,
        session_key: int | str | None = None,
        meeting_key: int | str | None = None,
        driver_number: int | None = None,
        params: Mapping[str, Any] | None = None,
        **filters: Any,
    ) -> SessionResult:
        query = self._compact(
            {
                "session_key": session_key,
                "meeting_key": meeting_key,
                "driver_number": driver_number,
            }
        )
        query.update(filters)
        return super().latest(params=params, **query)


