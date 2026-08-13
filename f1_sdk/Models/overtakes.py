from __future__ import annotations

from .f1BaseModel import F1BaseModel


class Overtakes(F1BaseModel):
    date: str
    meeting_key: int
    overtaken_driver_number: int
    overtaking_driver_number: int
    position: int
    session_key: int

