from __future__ import annotations

from typing import Any, Mapping

from ..Models import StartingGrid
from ..client.http import HttpClient

from .base import ModelResource


class StartingGridResource(ModelResource[StartingGrid]):
    def __init__(self, http: HttpClient):
        super().__init__(http, "/starting_grid", StartingGrid, latest_param="session_key")

    def all(
        self,
        *,
        session_key: int | str | None = None,
        meeting_key: int | str | None = None,
        driver_number: int | None = None,
        position: int | None = None,
        params: Mapping[str, Any] | None = None,
        **filters: Any,
    ) -> list[StartingGrid]:
        query = self._compact(
            {
                "session_key": session_key,
                "meeting_key": meeting_key,
                "driver_number": driver_number,
                "position": position,
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
    ) -> StartingGrid:
        query = self._compact(
            {
                "session_key": session_key,
                "meeting_key": meeting_key,
                "driver_number": driver_number,
            }
        )
        query.update(filters)
        return super().latest(params=params, **query)


