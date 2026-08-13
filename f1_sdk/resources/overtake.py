from __future__ import annotations

from typing import Any, Mapping

from ..Models import Overtakes
from ..client.http import HttpClient

from .base import ModelResource


class OvertakeResource(ModelResource[Overtakes]):
    def __init__(self, http: HttpClient):
        super().__init__(http, "/overtakes", Overtakes, latest_by="date", latest_param="session_key")

    def all(
        self,
        *,
        session_key: int | str | None = None,
        meeting_key: int | str | None = None,
        overtaking_driver_number: int | None = None,
        overtaken_driver_number: int | None = None,
        date: str | None = None,
        params: Mapping[str, Any] | None = None,
        **filters: Any,
    ) -> list[Overtakes]:
        query = self._compact(
            {
                "session_key": session_key,
                "meeting_key": meeting_key,
                "overtaking_driver_number": overtaking_driver_number,
                "overtaken_driver_number": overtaken_driver_number,
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
        overtaking_driver_number: int | None = None,
        overtaken_driver_number: int | None = None,
        params: Mapping[str, Any] | None = None,
        **filters: Any,
    ) -> Overtakes:
        query = self._compact(
            {
                "session_key": session_key,
                "meeting_key": meeting_key,
                "overtaking_driver_number": overtaking_driver_number,
                "overtaken_driver_number": overtaken_driver_number,
            }
        )
        query.update(filters)
        return super().latest(params=params, **query)


