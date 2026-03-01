from __future__ import annotations

from typing import Any, Mapping

from ..Models import Pit
from ..client.http import HttpClient

from .base import ModelResource


class PitResource(ModelResource[Pit]):
    def __init__(self, http: HttpClient):
        super().__init__(http, "/pit", Pit, latest_by="date", latest_param="session_key")

    def all(
        self,
        *,
        session_key: int | str | None = None,
        meeting_key: int | str | None = None,
        driver_number: int | None = None,
        lap_number: int | None = None,
        date: str | None = None,
        params: Mapping[str, Any] | None = None,
        **filters: Any,
    ) -> list[Pit]:
        query = self._compact(
            {
                "session_key": session_key,
                "meeting_key": meeting_key,
                "driver_number": driver_number,
                "lap_number": lap_number,
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
        lap_number: int | None = None,
        params: Mapping[str, Any] | None = None,
        **filters: Any,
    ) -> Pit:
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


