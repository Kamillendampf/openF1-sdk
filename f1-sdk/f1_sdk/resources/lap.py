from __future__ import annotations

from typing import Any, Mapping

from ..Models import Laps
from ..client.http import HttpClient

from .base import ModelResource


class LapResource(ModelResource[Laps]):
    def __init__(self, http: HttpClient):
        super().__init__(http, "/laps", Laps, latest_by="date_start", latest_param="session_key")

    def all(
        self,
        *,
        session_key: int | str | None = None,
        meeting_key: int | str | None = None,
        driver_number: int | None = None,
        lap_number: int | None = None,
        date_start: str | None = None,
        is_pit_out_lap: bool | None = None,
        params: Mapping[str, Any] | None = None,
        **filters: Any,
    ) -> list[Laps]:
        query = self._compact(
            {
                "session_key": session_key,
                "meeting_key": meeting_key,
                "driver_number": driver_number,
                "lap_number": lap_number,
                "date_start": date_start,
                "is_pit_out_lap": is_pit_out_lap,
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
        lap_number: int | None = None,
        params: Mapping[str, Any] | None = None,
        **filters: Any,
    ) -> Laps:
        query = self._compact(
            {
                "session_key": session_key,
                "meeting_key": meeting_key,
                "driver_number": driver_number,
                "lap_number": lap_number,
            }
        )
        query.update(filters)
        return super().latest(params=params, **query)


