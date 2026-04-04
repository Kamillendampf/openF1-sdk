from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
from math import hypot
from statistics import median
from threading import RLock
from time import monotonic
from time import perf_counter
from typing import TYPE_CHECKING
from typing import Any, Callable, Mapping, TypeVar, cast

from ..Models import CarData, Driver, F1BaseModel, Laps, Meeting, Position, RaceControl, Session, TeamRadio, Weather
from .http import F1Config, HttpClient
from ..resources import OpenF1Resources

CacheValueT = TypeVar("CacheValueT")
LOGGER = logging.getLogger("openf1.sdk")

if TYPE_CHECKING:
    from .live import OpenF1LiveClient


@dataclass(frozen=True)
class SessionScope:
    """
    Helper object with prefilled session/meeting filters.
    """

    sdk: OpenF1SDK
    session_key: int | str = "latest"
    meeting_key: int | str | None = None

    def session(self) -> Session:
        if self.session_key == "latest":
            return self.sdk.latest_session(meeting_key=self.meeting_key or "latest")
        return self.sdk.session.latest(session_key=self.session_key)

    def drivers(self, **filters: Any) -> list[Driver]:
        return self.sdk.drivers_for_session(session_key=self.session_key, **filters)

    def race_control(self, **filters: Any) -> list[RaceControl]:
        return self.sdk.race_control_for_session(session_key=self.session_key, **filters)

    def weather(self, **filters: Any) -> list[Weather]:
        meeting_key = self.meeting_key if self.meeting_key is not None else "latest"
        return self.sdk.weather_for_session(meeting_key=meeting_key, **filters)

    def laps(self, driver_number: int, **filters: Any) -> list[Laps]:
        return self.sdk.laps_for_driver(driver_number=driver_number, session_key=self.session_key, **filters)

    def car_data(self, driver_number: int, **filters: Any) -> list[CarData]:
        return self.sdk.car_data_for_driver(driver_number=driver_number, session_key=self.session_key, **filters)

    def positions(self, driver_number: int, **filters: Any) -> list[Position]:
        return self.sdk.positions_for_driver(driver_number=driver_number, session_key=self.session_key, **filters)

    def team_radio(self, driver_number: int, **filters: Any) -> list[TeamRadio]:
        return self.sdk.team_radio_for_driver(driver_number=driver_number, session_key=self.session_key, **filters)


class OpenF1SDK:
    """
    High-level SDK facade.
    """

    def __init__(self, config: F1Config | None = None):
        self.http = HttpClient(config or F1Config())
        self.resources = OpenF1Resources(self.http)
        self._cache: dict[str, tuple[float, Any]] = {}
        self._cache_lock = RLock()
        LOGGER.debug("OpenF1SDK initialized.")

    def close(self) -> None:
        LOGGER.debug("Closing OpenF1SDK HTTP client.")
        self.http.close()

    def __enter__(self) -> OpenF1SDK:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def __getattr__(self, name: str):
        return getattr(self.resources, name)

    def resource_names(self) -> tuple[str, ...]:
        return self.resources.names()

    def invalidate_cache(self, key: str | None = None) -> None:
        with self._cache_lock:
            if key is None:
                self._cache.clear()
                LOGGER.debug("SDK cache invalidated (all keys).")
            else:
                self._cache.pop(key, None)
                LOGGER.debug("SDK cache invalidated (key=%s).", key)

    def get_or_load_cached(
        self,
        key: str,
        loader: Callable[[], CacheValueT],
        *,
        ttl_seconds: float = 60.0,
        force_refresh: bool = False,
    ) -> CacheValueT:
        ttl = max(0.0, float(ttl_seconds))
        if not force_refresh and ttl > 0:
            now = monotonic()
            with self._cache_lock:
                cached = self._cache.get(key)
            if cached is not None:
                cached_at, cached_value = cached
                if now - cached_at < ttl:
                    LOGGER.debug("SDK cache hit (key=%s, ttl_seconds=%s).", key, ttl)
                    return cast(CacheValueT, cached_value)
                LOGGER.debug("SDK cache stale (key=%s, age_seconds=%.2f, ttl_seconds=%s).", key, now - cached_at, ttl)
            else:
                LOGGER.debug("SDK cache miss (key=%s).", key)
        elif force_refresh:
            LOGGER.debug("SDK cache force refresh (key=%s).", key)

        value = loader()
        with self._cache_lock:
            self._cache[key] = (monotonic(), value)
        LOGGER.debug("SDK cache store (key=%s).", key)
        return value

    def warmup_cache(
        self,
        loaders: Mapping[str, Callable[[], Any]],
        *,
        ttl_seconds: float = 60.0,
        force_refresh: bool = True,
    ) -> dict[str, Any]:
        results: dict[str, Any] = {}
        LOGGER.info("SDK cache warmup started (%d loaders).", len(loaders))
        for key, loader in loaders.items():
            results[key] = self.get_or_load_cached(
                key=key,
                loader=loader,
                ttl_seconds=ttl_seconds,
                force_refresh=force_refresh,
            )
        LOGGER.info("SDK cache warmup completed (%d entries).", len(results))
        return results

    def filter_track_points(
        self,
        track_points: list[dict[str, int]],
        jump_factor: float = 15.0,
        min_segment_size: int = 1,
    ) -> list[dict[str, int]]:
        if len(track_points) < 3:
            return track_points

        distances = [
            hypot(
                track_points[i + 1]["x"] - track_points[i]["x"],
                track_points[i + 1]["y"] - track_points[i]["y"],
            )
            for i in range(len(track_points) - 1)
        ]
        non_zero_distances = [distance for distance in distances if distance > 0]
        if not non_zero_distances:
            return track_points

        threshold = median(non_zero_distances) * jump_factor
        if threshold <= 0:
            return track_points

        segments: list[list[dict[str, int]]] = []
        current_segment = [track_points[0]]

        for i, distance in enumerate(distances):
            next_point = track_points[i + 1]
            if distance > threshold:
                if len(current_segment) >= min_segment_size:
                    segments.append(current_segment)
                current_segment = [next_point]
                continue
            current_segment.append(next_point)

        if len(current_segment) >= min_segment_size:
            segments.append(current_segment)

        if not segments:
            return track_points

        return max(segments, key=len)

    def get_track_points(self, session_latest: Session) -> list[dict[str, int]]:
        started = perf_counter()
        LOGGER.info(
            "Track extraction started (session_key=%s, circuit_key=%s, session=%s/%s).",
            session_latest.session_key,
            session_latest.circuit_key,
            session_latest.session_type,
            session_latest.session_name,
        )
        session_type = session_latest.session_type
        session_name = session_latest.session_name
        current_year = session_latest.date_start
        dt = datetime.fromisoformat(current_year)
        last_year = current_year.replace(str(dt.year), str(dt.year - 1))
        last_year_formated = datetime.fromisoformat(last_year).strftime("%Y")

        circuit_key = session_latest.circuit_key

        last_session = self.session.list(
            circuit_key=circuit_key,
            year=last_year_formated,
            session_type=session_type,
            session_name=session_name,
        )
        if not last_session:
            LOGGER.warning("Track extraction aborted: no reference session found.")
            return []

        last_session_key = last_session[0].session_key
        session_result = self.session_result.list(session_key=last_session_key, position=1)
        if not session_result:
            LOGGER.warning("Track extraction aborted: no session result for position=1 found.")
            return []

        driver_number = session_result[0].driver_number
        locations = self.location.list(session_key=last_session_key, driver_number=driver_number)

        track_points = [
            {"x": location.x, "y": location.y, "z": location.z}
            for location in locations
        ]
        filtered = self.filter_track_points(track_points)
        LOGGER.info(
            "Track extraction completed (raw_points=%d, filtered_points=%d, elapsed_ms=%d).",
            len(track_points),
            len(filtered),
            int((perf_counter() - started) * 1000),
        )
        return filtered

    def get_track(self, session_latest: Session) -> list[dict[str, int]]:
        LOGGER.debug("get_track called (session_key=%s).", session_latest.session_key)
        return self.get_track_points(session_latest)

    def create_live_client(
        self,
        *,
        token_provider: Callable[[bool], str | None],
        username: str,
        topics: tuple[str, ...] = ("v1/position", "v1/laps", "v1/location"),
        use_websocket: bool = False,
    ) -> OpenF1LiveClient:
        from .live import OpenF1LiveClient

        return OpenF1LiveClient(
            self,
            token_provider=token_provider,
            username=username,
            topics=topics,
            use_websocket=use_websocket,
        )

    def create_live_race_client(
        self,
        *,
        token_provider: Callable[[bool], str | None],
        username: str,
        topics: tuple[str, ...] = ("v1/position", "v1/laps", "v1/location"),
        use_websocket: bool = False,
    ) -> OpenF1LiveClient:
        return self.create_live_client(
            token_provider=token_provider,
            username=username,
            topics=topics,
            use_websocket=use_websocket,
        )

    def list_resource(
        self,
        resource_name: str,
        params: Mapping[str, Any] | None = None,
        **filters: Any,
    ) -> list[F1BaseModel]:
        resource = getattr(self.resources, resource_name)
        return resource.list(params=params, **filters)

    def latest_resource(
        self,
        resource_name: str,
        params: Mapping[str, Any] | None = None,
        **filters: Any,
    ) -> F1BaseModel:
        resource = getattr(self.resources, resource_name)
        return resource.latest(params=params, **filters)

    def latest_meeting(self, **filters: Any) -> Meeting:
        return self.meeting.latest(**filters)

    def latest_session(
        self, meeting_key: int | str = "latest", session_name: str | None = None, **filters: Any
    ) -> Session:
        query: dict[str, Any] = {"meeting_key": meeting_key}
        if session_name is not None:
            query["session_name"] = session_name
        query.update(filters)
        return self.session.latest(**query)

    def latest_race_session(self, meeting_key: int | str = "latest", **filters: Any) -> Session:
        return self.latest_session(meeting_key=meeting_key, session_name="Race", **filters)

    def drivers_for_session(self, session_key: int | str = "latest", **filters: Any) -> list[Driver]:
        return self.driver.list(session_key=session_key, **filters)

    def weather_for_session(self, meeting_key: int | str = "latest", **filters: Any) -> list[Weather]:
        return self.weather.list(meeting_key=meeting_key, **filters)

    def race_control_for_session(self, session_key: int | str = "latest", **filters: Any) -> list[RaceControl]:
        return self.race_control.list(session_key=session_key, **filters)

    def laps_for_driver(self, driver_number: int, session_key: int | str = "latest", **filters: Any) -> list[Laps]:
        return self.lap.list(driver_number=driver_number, session_key=session_key, **filters)

    def car_data_for_driver(
        self, driver_number: int, session_key: int | str = "latest", **filters: Any
    ) -> list[CarData]:
        return self.car_data.list(driver_number=driver_number, session_key=session_key, **filters)

    def positions_for_driver(
        self, driver_number: int, session_key: int | str = "latest", **filters: Any
    ) -> list[Position]:
        return self.position.list(driver_number=driver_number, session_key=session_key, **filters)

    def team_radio_for_driver(
        self, driver_number: int, session_key: int | str = "latest", **filters: Any
    ) -> list[TeamRadio]:
        return self.team_radio.list(driver_number=driver_number, session_key=session_key, **filters)

    def session_scope(self, session_key: int | str = "latest", meeting_key: int | str | None = None) -> SessionScope:
        return SessionScope(self, session_key=session_key, meeting_key=meeting_key)
