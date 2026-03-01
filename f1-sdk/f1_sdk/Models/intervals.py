from __future__ import annotations

from .f1BaseModel import F1BaseModel


class Interval(F1BaseModel):
    date: str
    driver_number: int
    gap_to_leader: float
    interval: float
    meeting_key: int
    session_key: int

