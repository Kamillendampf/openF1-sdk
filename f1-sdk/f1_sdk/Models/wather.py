from __future__ import annotations

from .f1BaseModel import F1BaseModel


class Weather(F1BaseModel):
    air_temperature: float
    date: str
    humidity: int
    meeting_key: int
    pressure: float
    rainfall: int
    session_key: int
    track_temperature: float
    wind_direction: int
    wind_speed: float

