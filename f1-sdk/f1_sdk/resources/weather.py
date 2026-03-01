from __future__ import annotations

from typing import Any, Mapping

from ..Models import Weather
from ..client.http import HttpClient

from .base import ModelResource


class WeatherResource(ModelResource[Weather]):
    def __init__(self, http: HttpClient):
        super().__init__(http, "/weather", Weather, latest_by="date", latest_param="meeting_key")

    def all(
        self,
        *,
        meeting_key: int | str | None = None,
        session_key: int | str | None = None,
        date: str | None = None,
        humidity: int | None = None,
        rainfall: int | None = None,
        params: Mapping[str, Any] | None = None,
        **filters: Any,
    ) -> list[Weather]:
        query = self._compact(
            {
                "meeting_key": meeting_key,
                "session_key": session_key,
                "date": date,
                "humidity": humidity,
                "rainfall": rainfall,
            }
        )
        query.update(filters)
        return super().all(params=params, **query)

    def latest(
        self,
        *,
        meeting_key: int | str | None = None,
        session_key: int | str | None = None,
        date: str | None = None,
        params: Mapping[str, Any] | None = None,
        **filters: Any,
    ) -> Weather:
        query = self._compact(
            {
                "meeting_key": meeting_key,
                "session_key": session_key,
                "date": date,
            }
        )
        query.update(filters)
        return super().latest(params=params, **query)


