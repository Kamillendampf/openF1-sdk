from __future__ import annotations

from collections.abc import Callable
from typing import Any


class F1Config: ...
class SessionScope: ...

class OpenF1NoDataError(Exception): ...
class OpenF1AuthError(Exception): ...
class OpenF1LiveError(Exception): ...

class OpenF1OAuthConfig: ...
class OpenF1OAuthClient: ...
class OpenF1LiveClient: ...


def configure(config: Any | None = None) -> None: ...
def close() -> None: ...
def get_track(session_latest: Any) -> list[dict[str, int]]: ...
def get_track_points(session_latest: Any) -> list[dict[str, int]]: ...
def filter_track_points(
    track_points: list[dict[str, int]],
    jump_factor: float = ...,
    min_segment_size: int = ...,
) -> list[dict[str, int]]: ...
def create_live_race_client(
    *,
    token_provider: Callable[[bool], str | None],
    username: str,
    topics: tuple[str, ...] = ...,
    use_websocket: bool = ...,
) -> OpenF1LiveClient: ...
def create_live_client(
    *,
    token_provider: Callable[[bool], str | None],
    username: str,
    topics: tuple[str, ...] = ...,
    use_websocket: bool = ...,
) -> OpenF1LiveClient: ...

car_data: Any
driver: Any
drivers: Any
interval: Any
intervals: Any
lap: Any
laps: Any
location: Any
meeting: Any
meetings: Any
overtake: Any
overtakes: Any
pit: Any
position: Any
race_control: Any
session: Any
sessions: Any
session_result: Any
starting_grid: Any
stint: Any
stints: Any
team_radio: Any
weather: Any

__all__: list[str]
