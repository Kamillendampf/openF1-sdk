from __future__ import annotations

from .f1BaseModel import F1BaseModel


class Pit(F1BaseModel):
    date: str
    driver_number: int
    lane_duration: float
    lap_number: int
    meeting_key: int
    pit_duration: float
    session_key: int
    stop_duration: float

