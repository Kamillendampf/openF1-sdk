from __future__ import annotations

from typing import Any, Mapping

from ..Models import Driver
from ..client.http import HttpClient

from .base import ModelResource


class DriverResource(ModelResource[Driver]):
    def __init__(self, http: HttpClient):
        super().__init__(http, "/drivers", Driver, latest_param="session_key")

    def all(
        self,
        *,
        session_key: int | str | None = None,
        meeting_key: int | str | None = None,
        driver_number: int | None = None,
        name_acronym: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        full_name: str | None = None,
        team_name: str | None = None,
        params: Mapping[str, Any] | None = None,
        **filters: Any,
    ) -> list[Driver]:
        query = self._compact(
            {
                "session_key": session_key,
                "meeting_key": meeting_key,
                "driver_number": driver_number,
                "name_acronym": name_acronym,
                "first_name": first_name,
                "last_name": last_name,
                "full_name": full_name,
                "team_name": team_name,
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
    ) -> Driver:
        query = self._compact(
            {
                "session_key": session_key,
                "meeting_key": meeting_key,
                "driver_number": driver_number,
            }
        )
        query.update(filters)
        return super().latest(params=params, **query)


