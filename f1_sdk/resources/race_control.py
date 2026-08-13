from __future__ import annotations

from typing import Any, Mapping

from ..Models import RaceControl
from ..client.http import HttpClient

from .base import ModelResource


class RaceControlResource(ModelResource[RaceControl]):
    def __init__(self, http: HttpClient):
        super().__init__(http, "/race_control", RaceControl, latest_by="date", latest_param="session_key")

    def all(
        self,
        *,
        session_key: int | str | None = None,
        meeting_key: int | str | None = None,
        driver_number: int | None = None,
        category: str | None = None,
        flag: str | None = None,
        lap_number: int | None = None,
        scope: str | None = None,
        date: str | None = None,
        params: Mapping[str, Any] | None = None,
        **filters: Any,
    ) -> list[RaceControl]:
        query = self._compact(
            {
                "session_key": session_key,
                "meeting_key": meeting_key,
                "driver_number": driver_number,
                "category": category,
                "flag": flag,
                "lap_number": lap_number,
                "scope": scope,
                "date": date,
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
        category: str | None = None,
        params: Mapping[str, Any] | None = None,
        **filters: Any,
    ) -> RaceControl:
        query = self._compact(
            {
                "session_key": session_key,
                "meeting_key": meeting_key,
                "driver_number": driver_number,
                "category": category,
            }
        )
        query.update(filters)
        return super().latest(params=params, **query)


