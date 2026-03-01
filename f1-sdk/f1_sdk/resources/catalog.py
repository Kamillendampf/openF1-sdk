from __future__ import annotations

from ..client.http import HttpClient

from .car_data import CarDataResource
from .driver import DriverResource
from .interval import IntervalResource
from .lap import LapResource
from .location import LocationResource
from .meeting import MeetingResource
from .overtake import OvertakeResource
from .pit import PitResource
from .position import PositionResource
from .race_control import RaceControlResource
from .session import SessionResource
from .session_result import SessionResultResource
from .starting_grid import StartingGridResource
from .stint import StintResource
from .team_radio import TeamRadioResource
from .weather import WeatherResource


class OpenF1Resources:
    car_data: CarDataResource
    drivers: DriverResource
    intervals: IntervalResource
    laps: LapResource
    location: LocationResource
    meetings: MeetingResource
    overtakes: OvertakeResource
    pit: PitResource
    position: PositionResource
    race_control: RaceControlResource
    sessions: SessionResource
    session_result: SessionResultResource
    starting_grid: StartingGridResource
    stints: StintResource
    team_radio: TeamRadioResource
    weather: WeatherResource

    car: CarDataResource
    driver: DriverResource
    interval: IntervalResource
    lap: LapResource
    meeting: MeetingResource
    overtake: OvertakeResource
    session: SessionResource
    stint: StintResource

    def __init__(self, http: HttpClient):
        self.car_data = CarDataResource(http)
        self.drivers = DriverResource(http)
        self.intervals = IntervalResource(http)
        self.laps = LapResource(http)
        self.location = LocationResource(http)
        self.meetings = MeetingResource(http)
        self.overtakes = OvertakeResource(http)
        self.pit = PitResource(http)
        self.position = PositionResource(http)
        self.race_control = RaceControlResource(http)
        self.sessions = SessionResource(http)
        self.session_result = SessionResultResource(http)
        self.starting_grid = StartingGridResource(http)
        self.stints = StintResource(http)
        self.team_radio = TeamRadioResource(http)
        self.weather = WeatherResource(http)

        self.car = self.car_data
        self.driver = self.drivers
        self.interval = self.intervals
        self.lap = self.laps
        self.meeting = self.meetings
        self.overtake = self.overtakes
        self.session = self.sessions
        self.stint = self.stints

    def names(self) -> tuple[str, ...]:
        return (
            "car_data",
            "drivers",
            "intervals",
            "laps",
            "location",
            "meetings",
            "overtakes",
            "pit",
            "position",
            "race_control",
            "sessions",
            "session_result",
            "starting_grid",
            "stints",
            "team_radio",
            "weather",
        )
