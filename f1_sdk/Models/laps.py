from __future__ import annotations

from typing import Optional

from .f1BaseModel import F1BaseModel


class Laps(F1BaseModel):
    date_start: Optional[str] = None
    driver_number: int
    duration_sector_1: Optional[float] = None
    duration_sector_2: Optional[float] = None
    duration_sector_3: Optional[float] = None
    i1_speed: Optional[int] = None
    i2_speed: Optional[int] = None
    is_pit_out_lap: Optional[bool] = None
    lap_duration: Optional[float] = None
    lap_number: int
    meeting_key: int
    segments_sector_1: Optional[list[Optional[int]]] = None
    segments_sector_2: Optional[list[Optional[int]]] = None
    segments_sector_3: Optional[list[Optional[int]]] = None
    session_key: int
    st_speed: Optional[int] = None

