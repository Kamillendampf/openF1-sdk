from __future__ import annotations

from .f1BaseModel import F1BaseModel


class Location(F1BaseModel):
    date: str
    driver_number: int
    meeting_key: int
    session_key: int
    x: int
    y: int
    z: int

