from __future__ import annotations

from .f1BaseModel import F1BaseModel


class CarData(F1BaseModel):
    brake: int
    date: str
    driver_number: int
    drs: int
    meeting_key: int
    n_gear: int
    rpm: int
    session_key: int
    speed: int
    throttle: int

