from __future__ import annotations
from typing import Optional

from .f1BaseModel import F1BaseModel


class RaceControl(F1BaseModel):
    category: str
    date: str
    driver_number: int
    flag: str
    lap_number: int
    meeting_key: int
    message: str
    qualifying_phase: Optional[int] = None
    scope: str
    sector: Optional[int] = None
    session_key: int

