from __future__ import annotations

from .f1BaseModel import F1BaseModel


class StartingGrid(F1BaseModel):
    position: int
    driver_number: int
    lap_duration: float
    meeting_key: int
    session_key: int

