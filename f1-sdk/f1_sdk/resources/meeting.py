from __future__ import annotations

from typing import Any, Mapping

from ..Models import Meeting
from ..client.http import HttpClient

from .base import ModelResource


class MeetingResource(ModelResource[Meeting]):
    def __init__(self, http: HttpClient):
        super().__init__(http, "/meetings", Meeting, latest_by="date_start", latest_param="meeting_key")

    def all(
        self,
        *,
        meeting_key: int | str | None = None,
        year: int | None = None,
        country_name: str | None = None,
        country_code: str | None = None,
        location: str | None = None,
        meeting_name: str | None = None,
        circuit_key: int | None = None,
        params: Mapping[str, Any] | None = None,
        **filters: Any,
    ) -> list[Meeting]:
        query = self._compact(
            {
                "meeting_key": meeting_key,
                "year": year,
                "country_name": country_name,
                "country_code": country_code,
                "location": location,
                "meeting_name": meeting_name,
                "circuit_key": circuit_key,
            }
        )
        query.update(filters)
        return super().all(params=params, **query)

    def latest(
        self,
        *,
        meeting_key: int | str | None = None,
        year: int | None = None,
        country_name: str | None = None,
        params: Mapping[str, Any] | None = None,
        **filters: Any,
    ) -> Meeting:
        query = self._compact(
            {
                "meeting_key": meeting_key,
                "year": year,
                "country_name": country_name,
            }
        )
        query.update(filters)
        return super().latest(params=params, **query)


