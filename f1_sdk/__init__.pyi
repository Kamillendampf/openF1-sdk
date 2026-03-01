from __future__ import annotations

from typing import Any

from .client import F1Config, OpenF1NoDataError, SessionScope
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

def configure(config: Any | None = None) -> None: ...
def close() -> None: ...

car_data: CarDataResource
driver: DriverResource
drivers: DriverResource
interval: IntervalResource
intervals: IntervalResource
lap: LapResource
laps: LapResource
location: LocationResource
meeting: MeetingResource
meetings: MeetingResource
overtake: OvertakeResource
overtakes: OvertakeResource
pit: PitResource
position: PositionResource
race_control: RaceControlResource
session: SessionResource
sessions: SessionResource
session_result: SessionResultResource
starting_grid: StartingGridResource
stint: StintResource
stints: StintResource
team_radio: TeamRadioResource
weather: WeatherResource

__all__: list[str]
