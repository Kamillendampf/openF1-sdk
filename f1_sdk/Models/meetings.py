from __future__ import annotations

from .f1BaseModel import F1BaseModel

class Meeting(F1BaseModel):
    circuit_key: int
    circuit_info_url: str
    circuit_image: str
    circuit_short_name: str
    circuit_type: str
    country_code: str
    country_flag:str
    country_key: int
    country_name: str
    date_end: str
    date_start: str
    gmt_offset: str
    location: str
    meeting_key: int
    meeting_name: str
    meeting_official_name: str
    year: int
