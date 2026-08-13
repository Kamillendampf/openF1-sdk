from __future__ import annotations

from typing import Any, Mapping

from ..Models import Session
from ..client.http import HttpClient

from .base import ModelResource


class SessionResource(ModelResource[Session]):
    def __init__(self, http: HttpClient):
        super().__init__(http, "/sessions", Session, latest_by="date_start", latest_param="session_key")

    def all(
        self,
        *,
        session_key: int | str | None = None,
        meeting_key: int | str | None = None,
        session_name: str | None = None,
        session_type: str | None = None,
        year: int | None = None,
        country_name: str | None = None,
        location: str | None = None,
        params: Mapping[str, Any] | None = None,
        **filters: Any,
    ) -> list[Session]:
        query = self._compact(
            {
                "session_key": session_key,
                "meeting_key": meeting_key,
                "session_name": session_name,
                "session_type": session_type,
                "year": year,
                "country_name": country_name,
                "location": location,
            }
        )
        query.update(filters)
        return super().all(params=params, **query)

    def latest(
        self,
        *,
        session_key: int | str | None = None,
        meeting_key: int | str | None = None,
        session_name: str | None = None,
        session_type: str | None = None,
        params: Mapping[str, Any] | None = None,
        **filters: Any,
    ) -> Session:
        query = self._compact(
            {
                "session_key": session_key,
                "meeting_key": meeting_key,
                "session_name": session_name,
                "session_type": session_type,
            }
        )
        query.update(filters)
        return super().latest(params=params, **query)


