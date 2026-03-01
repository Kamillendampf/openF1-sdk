from __future__ import annotations

from .f1BaseModel import F1BaseModel


class Driver(F1BaseModel):
    broadcast_name: str
    driver_number: int
    first_name: str
    full_name: str
    headshot_url: str
    last_name: str
    meeting_key: int
    name_acronym: str
    session_key: int
    team_colour: str
    team_name: str

