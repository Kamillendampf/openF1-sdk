from __future__ import annotations

from .f1BaseModel import F1BaseModel


class Session(F1BaseModel):
    circuit_key: int
    circuit_short_name: str
    country_code: str
    country_key: int
    country_name: str
    date_end: str
    date_start: str
    gmt_offset: str
    location: str
    meeting_key: int
    session_key: int
    session_name: str
    session_type: str
    year: int

