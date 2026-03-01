from __future__ import annotations

from .f1BaseModel import F1BaseModel


class Position(F1BaseModel):
    date: str
    driver_number: int
    meeting_key: int
    position: int
    session_key: int

