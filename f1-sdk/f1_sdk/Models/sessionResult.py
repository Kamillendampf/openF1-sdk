from __future__ import annotations

from .f1BaseModel import F1BaseModel


class SessionResult(F1BaseModel):
    dnf: bool
    dns: bool
    dsq: bool
    driver_number: int
    duration: float
    gap_to_leader: int
    number_of_laps: float
    meeting_key: int
    position: int
    session_key: int

