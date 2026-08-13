from __future__ import annotations

from typing import Any, Mapping

from ..Models import CarData
from ..client.http import HttpClient

from .base import ModelResource


class CarDataResource(ModelResource[CarData]):
    def __init__(self, http: HttpClient):
        super().__init__(http, "/car_data", CarData, latest_by="date", latest_param="session_key")

    def all(
        self,
        *,
        session_key: int | str | None = None,
        meeting_key: int | str | None = None,
        driver_number: int | None = None,
        date: str | None = None,
        n_gear: int | None = None,
        speed: int | None = None,
        params: Mapping[str, Any] | None = None,
        **filters: Any,
    ) -> list[CarData]:
        query = self._compact(
            {
                "session_key": session_key,
                "meeting_key": meeting_key,
                "driver_number": driver_number,
                "date": date,
                "n_gear": n_gear,
                "speed": speed,
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
        date: str | None = None,
        params: Mapping[str, Any] | None = None,
        **filters: Any,
    ) -> CarData:
        query = self._compact(
            {
                "session_key": session_key,
                "meeting_key": meeting_key,
                "driver_number": driver_number,
                "date": date,
            }
        )
        query.update(filters)
        return super().latest(params=params, **query)

