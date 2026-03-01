from __future__ import annotations

from pathlib import Path
from typing import Any, TYPE_CHECKING, cast
import sys

SDK_ROOT = Path(__file__).resolve().parent.parent / "f1-sdk"
SDK_PACKAGE_ROOT = SDK_ROOT / "f1_sdk"
if str(SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_ROOT))
if str(SDK_PACKAGE_ROOT) not in __path__:
    __path__.append(str(SDK_PACKAGE_ROOT))

_sdk: Any | None = None

if TYPE_CHECKING:
    from .resources import (
        CarDataResource,
        DriverResource,
        IntervalResource,
        LapResource,
        LocationResource,
        MeetingResource,
        OvertakeResource,
        PitResource,
        PositionResource,
        RaceControlResource,
        SessionResource,
        SessionResultResource,
        StartingGridResource,
        StintResource,
        TeamRadioResource,
        WeatherResource,
    )


class _ResourceProxy:
    def __init__(self, resource_name: str):
        self._resource_name = resource_name

    def _resource(self):
        return getattr(_ensure_sdk(), self._resource_name)

    def all(self, *args: Any, **kwargs: Any):
        return self._resource().all(*args, **kwargs)

    def list(self, *args: Any, **kwargs: Any):
        return self._resource().list(*args, **kwargs)

    def latest(self, *args: Any, **kwargs: Any):
        return self._resource().latest(*args, **kwargs)

    def __getattr__(self, name: str):
        return getattr(self._resource(), name)


def _build_sdk(config: Any | None = None):
    try:
        from .client import OpenF1SDK
    except ModuleNotFoundError as exc:
        if exc.name == "httpx":
            raise ModuleNotFoundError(
                "Missing dependency 'httpx'. Install dependencies with: pip install -e ./f1-sdk"
            ) from exc
        raise

    return OpenF1SDK(config)


def _ensure_sdk():
    global _sdk
    if _sdk is None:
        _sdk = _build_sdk()
    return _sdk


def configure(config: Any | None = None) -> None:
    global _sdk
    if _sdk is not None:
        _sdk.close()
    _sdk = _build_sdk(config)


def close() -> None:
    global _sdk
    if _sdk is not None:
        _sdk.close()
        _sdk = None


def __getattr__(name: str):
    if name in {"F1Config", "SessionScope", "OpenF1NoDataError"}:
        from .client import F1Config, SessionScope, OpenF1NoDataError

        if name == "F1Config":
            return F1Config
        if name == "OpenF1NoDataError":
            return OpenF1NoDataError
        return SessionScope
    return getattr(_ensure_sdk(), name)


car_data: "CarDataResource" = cast("CarDataResource", _ResourceProxy("car_data"))
driver: "DriverResource" = cast("DriverResource", _ResourceProxy("driver"))
drivers: "DriverResource" = cast("DriverResource", _ResourceProxy("drivers"))
interval: "IntervalResource" = cast("IntervalResource", _ResourceProxy("interval"))
intervals: "IntervalResource" = cast("IntervalResource", _ResourceProxy("intervals"))
lap: "LapResource" = cast("LapResource", _ResourceProxy("lap"))
laps: "LapResource" = cast("LapResource", _ResourceProxy("laps"))
location: "LocationResource" = cast("LocationResource", _ResourceProxy("location"))
meeting: "MeetingResource" = cast("MeetingResource", _ResourceProxy("meeting"))
meetings: "MeetingResource" = cast("MeetingResource", _ResourceProxy("meetings"))
overtake: "OvertakeResource" = cast("OvertakeResource", _ResourceProxy("overtake"))
overtakes: "OvertakeResource" = cast("OvertakeResource", _ResourceProxy("overtakes"))
pit: "PitResource" = cast("PitResource", _ResourceProxy("pit"))
position: "PositionResource" = cast("PositionResource", _ResourceProxy("position"))
race_control: "RaceControlResource" = cast("RaceControlResource", _ResourceProxy("race_control"))
session: "SessionResource" = cast("SessionResource", _ResourceProxy("session"))
sessions: "SessionResource" = cast("SessionResource", _ResourceProxy("sessions"))
session_result: "SessionResultResource" = cast("SessionResultResource", _ResourceProxy("session_result"))
starting_grid: "StartingGridResource" = cast("StartingGridResource", _ResourceProxy("starting_grid"))
stint: "StintResource" = cast("StintResource", _ResourceProxy("stint"))
stints: "StintResource" = cast("StintResource", _ResourceProxy("stints"))
team_radio: "TeamRadioResource" = cast("TeamRadioResource", _ResourceProxy("team_radio"))
weather: "WeatherResource" = cast("WeatherResource", _ResourceProxy("weather"))


__all__ = [
    "F1Config",
    "SessionScope",
    "OpenF1NoDataError",
    "configure",
    "close",
    "car_data",
    "driver",
    "drivers",
    "interval",
    "intervals",
    "lap",
    "laps",
    "location",
    "meeting",
    "meetings",
    "overtake",
    "overtakes",
    "pit",
    "position",
    "race_control",
    "session",
    "sessions",
    "session_result",
    "starting_grid",
    "stint",
    "stints",
    "team_radio",
    "weather",
]
