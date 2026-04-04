from __future__ import annotations

from typing import List, Optional, Union

from .f1BaseModel import F1BaseModel


class SessionResult(F1BaseModel):
    dnf: bool
    dns: bool
    dsq: bool
    driver_number: int
    duration: Optional[Union[float, List[float]]]
    gap_to_leader: Optional[Union[float, List[float]]]
    number_of_laps: Optional[int]
    meeting_key: int
    position: int
    session_key: int

