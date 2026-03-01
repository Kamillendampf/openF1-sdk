from __future__ import annotations

from typing import Any, Mapping

from ..Models import Stints
from ..client.http import HttpClient

from .base import ModelResource


class StintResource(ModelResource[Stints]):
    def __init__(self, http: HttpClient):
        super().__init__(http, "/stints", Stints, latest_param="session_key")

    def all(
        self,
        *,
        session_key: int | str | None = None,
        meeting_key: int | str | None = None,
        driver_number: int | None = None,
        stint_number: int | None = None,
        compound: str | None = None,
        lap_start: int | None = None,
        lap_end: int | None = None,
        params: Mapping[str, Any] | None = None,
        **filters: Any,
    ) -> list[Stints]:
        query = self._compact(
            {
                "session_key": session_key,
                "meeting_key": meeting_key,
                "driver_number": driver_number,
                "stint_number": stint_number,
                "compound": compound,
                "lap_start": lap_start,
                "lap_end": lap_end,
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
        stint_number: int | None = None,
        params: Mapping[str, Any] | None = None,
        **filters: Any,
    ) -> Stints:
        query = self._compact(
            {
                "session_key": session_key,
                "meeting_key": meeting_key,
                "driver_number": driver_number,
                "stint_number": stint_number,
            }
        )
        query.update(filters)
        return super().latest(params=params, **query)


