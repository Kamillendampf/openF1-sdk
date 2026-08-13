from __future__ import annotations

from .f1BaseModel import F1BaseModel


class TeamRadio(F1BaseModel):
    date: str
    driver_number: int
    meeting_key: int
    recording_url: str
    session_key: int

