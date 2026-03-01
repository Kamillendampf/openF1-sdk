from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..Models import CarData, Driver, F1BaseModel, Laps, Meeting, Position, RaceControl, Session, TeamRadio, Weather
from .http import F1Config, HttpClient
from ..resources import OpenF1Resources


@dataclass(frozen=True)
class SessionScope:
    """
    Helper object with prefilled session/meeting filters.
    """

    sdk: OpenF1SDK
    session_key: int | str = "latest"
    meeting_key: int | str | None = None

    def session(self) -> Session:
        if self.session_key == "latest":
            return self.sdk.latest_session(meeting_key=self.meeting_key or "latest")
        return self.sdk.session.latest(session_key=self.session_key)

    def drivers(self, **filters: Any) -> list[Driver]:
        return self.sdk.drivers_for_session(session_key=self.session_key, **filters)

    def race_control(self, **filters: Any) -> list[RaceControl]:
        return self.sdk.race_control_for_session(session_key=self.session_key, **filters)

    def weather(self, **filters: Any) -> list[Weather]:
        meeting_key = self.meeting_key if self.meeting_key is not None else "latest"
        return self.sdk.weather_for_session(meeting_key=meeting_key, **filters)

    def laps(self, driver_number: int, **filters: Any) -> list[Laps]:
        return self.sdk.laps_for_driver(driver_number=driver_number, session_key=self.session_key, **filters)

    def car_data(self, driver_number: int, **filters: Any) -> list[CarData]:
        return self.sdk.car_data_for_driver(driver_number=driver_number, session_key=self.session_key, **filters)

    def positions(self, driver_number: int, **filters: Any) -> list[Position]:
        return self.sdk.positions_for_driver(driver_number=driver_number, session_key=self.session_key, **filters)

    def team_radio(self, driver_number: int, **filters: Any) -> list[TeamRadio]:
        return self.sdk.team_radio_for_driver(driver_number=driver_number, session_key=self.session_key, **filters)


class OpenF1SDK:
    """
    High-level SDK facade.
    """

    def __init__(self, config: F1Config | None = None):
        self.http = HttpClient(config or F1Config())
        self.resources = OpenF1Resources(self.http)

    def close(self) -> None:
        self.http.close()

    def __enter__(self) -> OpenF1SDK:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def __getattr__(self, name: str):
        return getattr(self.resources, name)

    def resource_names(self) -> tuple[str, ...]:
        return self.resources.names()

    def list_resource(
        self,
        resource_name: str,
        params: Mapping[str, Any] | None = None,
        **filters: Any,
    ) -> list[F1BaseModel]:
        resource = getattr(self.resources, resource_name)
        return resource.list(params=params, **filters)

    def latest_resource(
        self,
        resource_name: str,
        params: Mapping[str, Any] | None = None,
        **filters: Any,
    ) -> F1BaseModel:
        resource = getattr(self.resources, resource_name)
        return resource.latest(params=params, **filters)

    def latest_meeting(self, **filters: Any) -> Meeting:
        return self.meeting.latest(**filters)

    def latest_session(
        self, meeting_key: int | str = "latest", session_name: str | None = None, **filters: Any
    ) -> Session:
        query: dict[str, Any] = {"meeting_key": meeting_key}
        if session_name is not None:
            query["session_name"] = session_name
        query.update(filters)
        return self.session.latest(**query)

    def latest_race_session(self, meeting_key: int | str = "latest", **filters: Any) -> Session:
        return self.latest_session(meeting_key=meeting_key, session_name="Race", **filters)

    def drivers_for_session(self, session_key: int | str = "latest", **filters: Any) -> list[Driver]:
        return self.driver.list(session_key=session_key, **filters)

    def weather_for_session(self, meeting_key: int | str = "latest", **filters: Any) -> list[Weather]:
        return self.weather.list(meeting_key=meeting_key, **filters)

    def race_control_for_session(self, session_key: int | str = "latest", **filters: Any) -> list[RaceControl]:
        return self.race_control.list(session_key=session_key, **filters)

    def laps_for_driver(self, driver_number: int, session_key: int | str = "latest", **filters: Any) -> list[Laps]:
        return self.lap.list(driver_number=driver_number, session_key=session_key, **filters)

    def car_data_for_driver(
        self, driver_number: int, session_key: int | str = "latest", **filters: Any
    ) -> list[CarData]:
        return self.car_data.list(driver_number=driver_number, session_key=session_key, **filters)

    def positions_for_driver(
        self, driver_number: int, session_key: int | str = "latest", **filters: Any
    ) -> list[Position]:
        return self.position.list(driver_number=driver_number, session_key=session_key, **filters)

    def team_radio_for_driver(
        self, driver_number: int, session_key: int | str = "latest", **filters: Any
    ) -> list[TeamRadio]:
        return self.team_radio.list(driver_number=driver_number, session_key=session_key, **filters)

    def session_scope(self, session_key: int | str = "latest", meeting_key: int | str | None = None) -> SessionScope:
        return SessionScope(self, session_key=session_key, meeting_key=meeting_key)
