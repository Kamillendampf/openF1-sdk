
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Optional

from f1_sdk import OpenF1AuthError, OpenF1LiveClient, OpenF1LiveError, OpenF1OAuthClient, OpenF1OAuthConfig
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

import f1_sdk as f1

# WEB_ROOT = Path(__file__).resolve().parent / "web"
# INDEX_HTML = WEB_ROOT / "index.html"
# APP_JS = WEB_ROOT / "app.js"
ANGULAR_DIST_ROOT = Path(__file__).resolve().parent / "angular-frontend" / "dist" / "frontend" / "browser"
ANGULAR_INDEX_HTML = ANGULAR_DIST_ROOT / "index.html"
AUTH_CONFIG_PATH = Path(__file__).resolve().parent / "config" / "openf1.auth.ini"
TRACK_CACHE_TTL_SECONDS = 900.0

_auth_client: OpenF1OAuthClient | None = None
_live_client: OpenF1LiveClient | None = None
_live_username: str | None = None
_mqtt_oauth_ready: bool = False
_history_replay_cache: dict[int, dict[str, Any]] = {}
_live_track_preload: dict[str, Any] | None = None
LOGGER = logging.getLogger("openf1.app")


def _is_truthy_env(var_name: str) -> bool:
    return os.getenv(var_name, "").strip().lower() in {"1", "true", "yes", "on"}


def _mask_email(value: str | None) -> str:
    if not value:
        return "<empty>"
    if "@" not in value:
        return "***"
    local, domain = value.split("@", 1)
    if not local:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"


def _email_for_logs(value: str | None) -> str:
    if LOGGER.isEnabledFor(logging.DEBUG) and _is_truthy_env("OPENF1_LOG_PII"):
        return value or "<empty>"
    return _mask_email(value)


def _configure_logging() -> None:
    level_name = os.getenv("OPENF1_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        )
    else:
        root_logger.setLevel(level)

    logging.getLogger("openf1").setLevel(level)


def _cors_origins_from_env() -> list[str]:
    raw_origins = os.getenv("OPENF1_CORS_ORIGINS", "").strip()
    if raw_origins:
        return [value.strip() for value in raw_origins.split(",") if value.strip()]
    return [
        "http://localhost:4200",
        "http://127.0.0.1:4200",
    ]


def _track_cache_key(session_latest: Any) -> str:
    return (
        f"track:{session_latest.circuit_key}:"
        f"{session_latest.session_type}:{session_latest.session_name}:{session_latest.year}"
    )


def _session_key_str(value: Any) -> str:
    return str(value) if value is not None else ""


def _update_live_track_preload(
    *,
    session_latest: Any,
    track_key: str,
    track_points: list[dict[str, int]],
    source: str,
) -> None:
    global _live_track_preload
    _live_track_preload = {
        "session_key": _session_key_str(getattr(session_latest, "session_key", None)),
        "track_key": track_key,
        "track_points": track_points,
        "session_name": session_latest.session_name,
        "session_type": session_latest.session_type,
        "year": session_latest.year,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    LOGGER.info(
        "Live track preload updated (source=%s, session_key=%s, cache_key=%s, points=%d).",
        source,
        session_latest.session_key,
        track_key,
        len(track_points),
    )


def _resolve_live_track_points(session_latest: Any) -> tuple[list[dict[str, int]], str]:
    track_key = _track_cache_key(session_latest)
    cached = _live_track_preload
    current_session_key = _session_key_str(getattr(session_latest, "session_key", None))

    if (
        cached is not None
        and cached.get("track_key") == track_key
    ):
        cached_points = cached.get("track_points")
        if isinstance(cached_points, list):
            cached_session_key = _session_key_str(cached.get("session_key"))
            if cached_session_key != current_session_key:
                LOGGER.info(
                    "Using preloaded live track with changed session_key (previous=%s, current=%s, cache_key=%s).",
                    cached_session_key,
                    current_session_key,
                    track_key,
                )
            LOGGER.info(
                "Using preloaded live track (session_key=%s, cache_key=%s, points=%d, updated_at=%s).",
                current_session_key,
                track_key,
                len(cached_points),
                cached.get("updated_at"),
            )
            return cached_points, track_key

    if cached is None:
        LOGGER.info(
            "Live track preload unavailable. Loading track for current session (session_key=%s, cache_key=%s).",
            current_session_key,
            track_key,
        )
    else:
        LOGGER.info(
            "Live track key changed. Refreshing preloaded track (previous_session_key=%s, new_session_key=%s, previous_cache_key=%s, new_cache_key=%s).",
            cached.get("session_key"),
            current_session_key,
            cached.get("track_key"),
            track_key,
        )

    track_points = f1.get_or_load_cached(
        key=track_key,
        loader=lambda: f1.get_track(session_latest),
        ttl_seconds=TRACK_CACHE_TTL_SECONDS,
        force_refresh=False,
    )
    _update_live_track_preload(
        session_latest=session_latest,
        track_key=track_key,
        track_points=track_points,
        source="runtime_refresh",
    )
    return track_points, track_key


def _to_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return None
    return None


def _utc_now_iso_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _weather_condition(weather_row: Any) -> str:
    rainfall = _to_int(getattr(weather_row, "rainfall", None)) or 0
    humidity = _to_int(getattr(weather_row, "humidity", None)) or 0
    track_temp = getattr(weather_row, "track_temperature", None)

    if rainfall > 0:
        return "rain"
    if humidity >= 85:
        return "cloudy"
    if isinstance(track_temp, (int, float)) and track_temp >= 42:
        return "hot"
    return "clear"


def _weather_icon(condition: str) -> str:
    if condition == "rain":
        return "rain"
    if condition == "cloudy":
        return "cloud"
    if condition == "hot":
        return "sun-high"
    return "sun"


def _weather_row_payload(weather_row: Any) -> dict[str, Any]:
    condition = _weather_condition(weather_row)
    return {
        "date": getattr(weather_row, "date", None),
        "air_temperature": getattr(weather_row, "air_temperature", None),
        "track_temperature": getattr(weather_row, "track_temperature", None),
        "humidity": getattr(weather_row, "humidity", None),
        "pressure": getattr(weather_row, "pressure", None),
        "wind_speed": getattr(weather_row, "wind_speed", None),
        "wind_direction": getattr(weather_row, "wind_direction", None),
        "rainfall": getattr(weather_row, "rainfall", None),
        "condition": condition,
        "icon": _weather_icon(condition),
    }


def _snap_to_track_point(track_points: list[dict[str, int]], x: int, y: int, z: int) -> dict[str, int]:
    if not track_points:
        return {"x": x, "y": y, "z": z}
    return min(
        track_points,
        key=lambda point: (
            (point["x"] - x) ** 2
            + (point["y"] - y) ** 2
            + (point["z"] - z) ** 2
        ),
    )


def _load_position_rows(session_key: int | str) -> list[Any]:
    try:
        return f1.position.list(session_key=session_key)
    except Exception as exc:  # noqa: BLE001
        status_code = getattr(exc, "status_code", None)
        if status_code == 404:
            LOGGER.warning(
                "Position endpoint returned 404 (session_key=%s). Continuing without position rows.",
                session_key,
            )
            return []
        raise


def _build_position_rows_by_driver(session_key: int | str) -> dict[int, list[Any]]:
    rows = _load_position_rows(session_key)
    rows_by_driver: dict[int, list[Any]] = {}
    for row in rows:
        driver_number = _to_int(getattr(row, "driver_number", None))
        if driver_number is None:
            continue
        rows_by_driver.setdefault(driver_number, []).append(row)

    for driver_rows in rows_by_driver.values():
        driver_rows.sort(key=lambda item: item.date)
    return rows_by_driver


def _position_rows_in_window(
    position_rows: list[Any],
    *,
    start: str | None = None,
    end: str | None = None,
) -> list[Any]:
    if not position_rows:
        return []

    filtered: list[Any] = []
    for row in position_rows:
        date = getattr(row, "date", None)
        if not isinstance(date, str):
            continue
        if start and date < start:
            continue
        if end and date >= end:
            continue
        filtered.append(row)
    return filtered


def _latest_row_before(position_rows: list[Any], before: str) -> Any | None:
    latest: Any | None = None
    for row in position_rows:
        date = getattr(row, "date", None)
        if not isinstance(date, str):
            continue
        if date >= before:
            break
        latest = row
    return latest


def _load_driver_position_rows(
    session_key: int | str,
    driver_number: int,
    *,
    start: str | None = None,
    end: str | None = None,
) -> list[Any]:
    params: dict[str, Any] = {}
    if start:
        params["date>"] = start
    if end:
        params["date<"] = end

    try:
        return f1.position.list(
            session_key=session_key,
            driver_number=driver_number,
            params=params if params else None,
        )
    except Exception as exc:  # noqa: BLE001
        status_code = getattr(exc, "status_code", None)
        if status_code == 404:
            return []
        LOGGER.warning(
            "Position query failed (session_key=%s, driver_number=%s, start=%s, end=%s): %s",
            session_key,
            driver_number,
            start,
            end,
            exc,
        )
        return []


def _latest_position_before(
    session_key: int | str,
    driver_number: int,
    before: str,
    *,
    position_rows_by_driver: dict[int, list[Any]] | None = None,
) -> Any | None:
    if position_rows_by_driver is not None:
        return _latest_row_before(position_rows_by_driver.get(driver_number, []), before)

    try:
        rows = f1.position.list(
            session_key=session_key,
            driver_number=driver_number,
            params={"date<": before},
        )
    except Exception:
        return None
    if not rows:
        return None
    rows.sort(key=lambda row: row.date)
    return _latest_row_before(rows, before)


def _latest_location_for_driver(
    session_key: int | str,
    driver_number: int,
    *,
    before: str | None = None,
) -> Any | None:
    params: dict[str, Any] | None = None
    if before:
        params = {"date<": before}
    try:
        rows = f1.location.list(
            session_key=session_key,
            driver_number=driver_number,
            params=params,
        )
    except Exception:
        return None
    if not rows:
        return None
    return max(rows, key=lambda row: row.date)


def _build_drivers_payload(
    session_key: int | str,
    track_points: list[dict[str, int]],
) -> tuple[list[dict[str, Any]], int, int]:
    drivers = f1.driver.list(session_key=session_key)
    position_rows = _load_position_rows(session_key)

    latest_position_by_driver: dict[int, Any] = {}
    for row in position_rows:
        previous = latest_position_by_driver.get(row.driver_number)
        if previous is None or row.date > previous.date:
            latest_position_by_driver[row.driver_number] = row

    drivers_payload: list[dict[str, Any]] = []
    location_query_count = 0
    for driver in drivers:
        payload = driver.model_dump()
        payload["track_point"] = None
        payload["current_position"] = None
        payload["position_date"] = None

        position_row = latest_position_by_driver.get(driver.driver_number)
        if position_row is not None:
            payload["current_position"] = position_row.position
            payload["position_date"] = position_row.date

        try:
            locations = f1.location.list(
                session_key=session_key,
                driver_number=driver.driver_number,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning(
                "Location query failed (session_key=%s, driver_number=%s): %s",
                session_key,
                driver.driver_number,
                exc,
            )
            locations = []
        location_query_count += 1
        if locations:
            latest_location = max(locations, key=lambda location: location.date)
            snapped = _snap_to_track_point(track_points, latest_location.x, latest_location.y, latest_location.z)
            payload["track_point"] = {
                "x": snapped["x"],
                "y": snapped["y"],
                "z": snapped["z"],
                "date": latest_location.date,
            }

        drivers_payload.append(payload)

    drivers_payload.sort(
        key=lambda driver_row: (
            driver_row["current_position"] is None,
            driver_row["current_position"] if driver_row["current_position"] is not None else 999,
            driver_row.get("driver_number", 999),
        )
    )
    return drivers_payload, len(position_rows), location_query_count


def _build_driver_metadata_payload(
    session_key: int | str,
    track_points: list[dict[str, int]] | None = None,
    position_rows_by_driver: dict[int, list[Any]] | None = None,
    include_location_seed: bool = True,
) -> tuple[list[dict[str, Any]], int]:
    drivers = f1.driver.list(session_key=session_key)
    if position_rows_by_driver is None:
        position_rows_by_driver = _build_position_rows_by_driver(session_key)
    position_row_count = sum(len(rows) for rows in position_rows_by_driver.values())

    first_position_by_driver: dict[int, Any] = {}
    for driver_number, rows in position_rows_by_driver.items():
        if rows:
            first_position_by_driver[driver_number] = rows[0]

    drivers_payload: list[dict[str, Any]] = []
    for driver in drivers:
        payload = driver.model_dump()
        payload["track_point"] = None
        payload["current_position"] = None
        payload["position_date"] = None
        payload["current_lap"] = 1
        payload["lap_date"] = None

        start_position_row = first_position_by_driver.get(driver.driver_number)
        if start_position_row is not None:
            payload["current_position"] = start_position_row.position
            payload["position_date"] = start_position_row.date

        if include_location_seed:
            latest_location = _latest_location_for_driver(session_key, driver.driver_number)
            if latest_location is not None:
                if track_points:
                    snapped = _snap_to_track_point(track_points, latest_location.x, latest_location.y, latest_location.z)
                    payload["track_point"] = {
                        "x": snapped["x"],
                        "y": snapped["y"],
                        "z": snapped["z"],
                        "date": latest_location.date,
                    }
                else:
                    payload["track_point"] = {
                        "x": latest_location.x,
                        "y": latest_location.y,
                        "z": latest_location.z,
                        "date": latest_location.date,
                    }

        drivers_payload.append(payload)

    drivers_payload.sort(
        key=lambda driver_row: (
            driver_row["current_position"] is None,
            driver_row["current_position"] if driver_row["current_position"] is not None else 999,
            driver_row.get("driver_number", 999),
        )
    )
    return drivers_payload, position_row_count


def _session_lap_payload(session_key: int | str) -> dict[str, Any]:
    lap_max: int | None = None
    try:
        result_rows = f1.session_result.list(session_key=session_key, position=1)
        if result_rows:
            lap_max = _to_int(result_rows[0].number_of_laps)
    except Exception as exc:  # noqa: BLE001
        LOGGER.debug("Could not read lap summary for session_key=%s: %s", session_key, exc)

    lap_current = lap_max
    lap_display = f"{lap_current}/{lap_max}" if lap_current is not None and lap_max is not None else None
    return {
        "current": lap_current,
        "max": lap_max,
        "display": lap_display,
    }


def _build_history_playback_events(
    session_key: int,
    track_points: list[dict[str, int]],
    driver_numbers: list[int],
    sample_step: int = 1,
    position_rows_by_driver: dict[int, list[Any]] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    lap_rows = f1.lap.list(session_key=session_key)
    lap_starts_by_driver: dict[int, list[tuple[str, int]]] = {}
    for row in lap_rows:
        if not row.date_start:
            continue
        lap_num = _to_int(row.lap_number)
        if lap_num is None:
            continue
        lap_starts_by_driver.setdefault(row.driver_number, []).append((row.date_start, lap_num))

    for starts in lap_starts_by_driver.values():
        starts.sort(key=lambda item: item[0])

    events: list[dict[str, Any]] = []
    location_query_count = 0
    safe_step = max(1, int(sample_step))

    for driver_number in driver_numbers:
        location_query_count += 1
        try:
            locations = f1.location.list(session_key=session_key, driver_number=driver_number)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning(
                "Playback location query failed (session_key=%s, driver_number=%s): %s",
                session_key,
                driver_number,
                exc,
            )
            locations = []
        if not locations:
            continue

        if position_rows_by_driver is not None:
            position_rows = position_rows_by_driver.get(driver_number, [])
        else:
            position_rows = _load_driver_position_rows(session_key, driver_number)
            position_rows.sort(key=lambda row: row.date)
        position_idx = 0
        current_position: int | None = None
        current_position_date: str | None = None

        lap_starts = lap_starts_by_driver.get(driver_number, [])
        lap_index = 0
        current_lap = 1
        last_idx = len(locations) - 1

        for idx, location in enumerate(locations):
            while lap_index < len(lap_starts) and lap_starts[lap_index][0] <= location.date:
                current_lap = lap_starts[lap_index][1]
                lap_index += 1
            while position_idx < len(position_rows) and position_rows[position_idx].date <= location.date:
                current_position = _to_int(position_rows[position_idx].position)
                current_position_date = position_rows[position_idx].date
                position_idx += 1

            if safe_step > 1 and idx != last_idx and idx % safe_step != 0:
                continue

            snapped = _snap_to_track_point(track_points, location.x, location.y, location.z)
            events.append(
                {
                    "date": location.date,
                    "driver_number": driver_number,
                    "x": snapped["x"],
                    "y": snapped["y"],
                    "z": snapped["z"],
                    "lap_number": current_lap,
                    "position": current_position,
                    "position_date": current_position_date,
                }
            )

    events.sort(key=lambda item: item["date"])
    return events, location_query_count


def _build_lap_window_map(session_key: int) -> tuple[dict[int, tuple[str, Optional[str]]], list[int]]:
    lap_rows = f1.lap.list(session_key=session_key)
    first_start_by_lap: dict[int, str] = {}
    for row in lap_rows:
        if not row.date_start:
            continue
        lap_num = _to_int(row.lap_number)
        if lap_num is None or lap_num <= 0:
            continue
        previous = first_start_by_lap.get(lap_num)
        if previous is None or row.date_start < previous:
            first_start_by_lap[lap_num] = row.date_start

    lap_numbers = sorted(first_start_by_lap.keys())
    windows: dict[int, tuple[str, Optional[str]]] = {}
    for idx, lap_number in enumerate(lap_numbers):
        start = first_start_by_lap[lap_number]
        end: Optional[str] = None
        if idx + 1 < len(lap_numbers):
            end = first_start_by_lap[lap_numbers[idx + 1]]
        windows[lap_number] = (start, end)

    return windows, lap_numbers


def _build_lap_events_for_window(
    session_key: int,
    track_points: list[dict[str, int]],
    driver_numbers: list[int],
    lap_number: int,
    start: str,
    end: Optional[str],
    sample_step: int,
    position_rows_by_driver: dict[int, list[Any]] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    events: list[dict[str, Any]] = []
    location_query_count = 0
    safe_step = max(1, int(sample_step))

    for driver_number in driver_numbers:
        query_params: dict[str, Any] = {"date>": start}
        if end:
            query_params["date<"] = end

        if position_rows_by_driver is not None:
            driver_position_rows = position_rows_by_driver.get(driver_number, [])
            position_rows = _position_rows_in_window(
                driver_position_rows,
                start=start,
                end=end,
            )
            seed_position_row = _latest_row_before(driver_position_rows, start)
        else:
            position_rows = _load_driver_position_rows(
                session_key,
                driver_number,
                start=start,
                end=end,
            )
            position_rows.sort(key=lambda row: row.date)
            seed_position_row = _latest_position_before(session_key, driver_number, start)
        position_idx = 0
        current_position = _to_int(seed_position_row.position) if seed_position_row is not None else None
        current_position_date = seed_position_row.date if seed_position_row is not None else None

        location_query_count += 1
        try:
            locations = f1.location.list(
                session_key=session_key,
                driver_number=driver_number,
                params=query_params,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning(
                "Lap location query failed (session_key=%s, lap=%s, driver_number=%s): %s",
                session_key,
                lap_number,
                driver_number,
                exc,
            )
            locations = []

        if not locations:
            inclusive_query_params: dict[str, Any] = {"date>=": start}
            if end:
                inclusive_query_params["date<"] = end
            try:
                locations = f1.location.list(
                    session_key=session_key,
                    driver_number=driver_number,
                    params=inclusive_query_params,
                )
            except Exception:
                locations = []

        if not locations:
            seed_location = _latest_location_for_driver(
                session_key=session_key,
                driver_number=driver_number,
                before=start,
            )
            if seed_location is None:
                seed_location = _latest_location_for_driver(
                    session_key=session_key,
                    driver_number=driver_number,
                )
            if seed_location is None:
                continue

            snapped_seed = _snap_to_track_point(track_points, seed_location.x, seed_location.y, seed_location.z)
            events.append(
                {
                    "date": start,
                    "driver_number": driver_number,
                    "x": snapped_seed["x"],
                    "y": snapped_seed["y"],
                    "z": snapped_seed["z"],
                    "lap_number": lap_number,
                    "position": current_position,
                    "position_date": current_position_date,
                }
            )
            continue

        last_idx = len(locations) - 1
        for idx, location in enumerate(locations):
            while position_idx < len(position_rows) and position_rows[position_idx].date <= location.date:
                current_position = _to_int(position_rows[position_idx].position)
                current_position_date = position_rows[position_idx].date
                position_idx += 1
            if safe_step > 1 and idx != last_idx and idx % safe_step != 0:
                continue

            snapped = _snap_to_track_point(track_points, location.x, location.y, location.z)
            events.append(
                {
                    "date": location.date,
                    "driver_number": driver_number,
                    "x": snapped["x"],
                    "y": snapped["y"],
                    "z": snapped["z"],
                    "lap_number": lap_number,
                    "position": current_position,
                    "position_date": current_position_date,
                }
            )

    events.sort(key=lambda item: item["date"])
    return events, location_query_count


def _ensure_history_replay_context(session_key: int) -> dict[str, Any]:
    cached = _history_replay_cache.get(session_key)
    if cached is not None:
        return cached

    rows = f1.session.list(session_key=session_key)
    if not rows:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_key}")
    session = rows[0]

    track_key = _track_cache_key(session)
    track_points = f1.get_or_load_cached(
        key=track_key,
        loader=lambda: f1.get_track(session),
        ttl_seconds=TRACK_CACHE_TTL_SECONDS,
    )
    position_rows_by_driver = _build_position_rows_by_driver(session.session_key)
    drivers_payload, position_row_count = _build_driver_metadata_payload(
        session.session_key,
        track_points=track_points,
        position_rows_by_driver=position_rows_by_driver,
        include_location_seed=False,
    )
    driver_numbers = [
        row["driver_number"]
        for row in drivers_payload
        if isinstance(row.get("driver_number"), int)
    ]
    lap_windows, lap_numbers = _build_lap_window_map(session.session_key)
    lap_payload = _session_lap_payload(session.session_key)
    if lap_numbers and not isinstance(lap_payload.get("max"), int):
        lap_payload["max"] = lap_numbers[-1]

    context = {
        "session": session,
        "track_points": track_points,
        "drivers_payload": drivers_payload,
        "driver_numbers": driver_numbers,
        "lap_windows": lap_windows,
        "lap_numbers": lap_numbers,
        "lap_payload": lap_payload,
        "position_row_count": position_row_count,
        "position_rows_by_driver": position_rows_by_driver,
    }
    _history_replay_cache[session_key] = context
    return context


def _build_token_provider() -> Callable[[bool], str | None] | None:
    global _auth_client, _live_username

    LOGGER.info("Loading OAuth config from %s", AUTH_CONFIG_PATH)
    try:
        oauth_config = OpenF1OAuthConfig.from_ini(AUTH_CONFIG_PATH)
    except OpenF1AuthError as exc:
        LOGGER.error("OAuth config is invalid: %s", exc)
        _live_username = None
        _auth_client = None
        return None
    LOGGER.info(
        "OAuth config loaded (auth_required=%s, token_url=%s, timeout=%ss).",
        oauth_config.auth_required,
        oauth_config.token_url,
        oauth_config.timeout,
    )
    LOGGER.debug(
        "OAuth config details (user_email=%s, pii_debug=%s).",
        _email_for_logs(oauth_config.user_email),
        _is_truthy_env("OPENF1_LOG_PII"),
    )
    if not oauth_config.auth_required:
        LOGGER.info("OAuth is disabled. Running in historical/public mode.")
        _live_username = None
        _auth_client = None
        return None

    LOGGER.info("OAuth is enabled. Initializing OAuth client.")
    _live_username = oauth_config.user_email or "openf1-user"
    _auth_client = OpenF1OAuthClient(oauth_config)
    LOGGER.debug("OAuth client initialized (live_username=%s).", _email_for_logs(_live_username))

    def token_provider(force_refresh: bool = False) -> str | None:
        LOGGER.debug("OAuth token provider called (force_refresh=%s).", force_refresh)
        if _auth_client is None:
            LOGGER.debug("OAuth token provider skipped: auth client not initialized.")
            return None
        try:
            token = _auth_client.get_token(force_refresh=force_refresh)
        except OpenF1AuthError as exc:
            LOGGER.warning("OAuth token fetch failed (force_refresh=%s): %s", force_refresh, exc)
            return None
        LOGGER.debug("OAuth token provider returned token (length=%d).", len(token.access_token))
        return token.access_token

    return token_provider


def system_init() -> None:
    global _live_client, _mqtt_oauth_ready, _live_track_preload

    _configure_logging()
    LOGGER.info("System init started.")
    token_provider = _build_token_provider()
    _mqtt_oauth_ready = False
    if token_provider is not None and _live_username:
        LOGGER.info("Performing OAuth pre-authentication for MQTT startup.")
        startup_token = token_provider(force_refresh=True)
        _mqtt_oauth_ready = bool(startup_token)
        if _mqtt_oauth_ready:
            LOGGER.info("OAuth pre-authentication succeeded for MQTT startup.")
            LOGGER.debug("OAuth startup token acquired (length=%d).", len(startup_token))
        else:
            LOGGER.warning("OAuth pre-authentication failed: no access token available for MQTT startup.")
    LOGGER.info(
        "OAuth runtime state (token_provider_ready=%s, live_username_present=%s).",
        token_provider is not None,
        bool(_live_username),
    )
    LOGGER.debug("OAuth runtime details (live_username=%s).", _email_for_logs(_live_username))
    f1.configure(
        f1.F1Config(
            rate_limit_enabled=True,
            pause_every_requests=6,
            pause_seconds=1.0,
            token_provider=token_provider,
        )
    )
    LOGGER.info("OpenF1 SDK configured (rate_limit_enabled=%s, pause_every_requests=%s, pause_seconds=%s).", True, 6, 1.0)
    try:
        preload_started = perf_counter()
        latest_session = f1.session.latest()
        track_key = _track_cache_key(latest_session)
        LOGGER.info(
            "Track preload started (circuit=%s, session=%s, cache_key=%s).",
            latest_session.circuit_short_name,
            latest_session.session_name,
            track_key,
        )
        track_points = f1.get_or_load_cached(
            key=track_key,
            loader=lambda: f1.get_track(latest_session),
            ttl_seconds=TRACK_CACHE_TTL_SECONDS,
            force_refresh=True,
        )
        _update_live_track_preload(
            session_latest=latest_session,
            track_key=track_key,
            track_points=track_points,
            source="startup",
        )
        LOGGER.info(
            "Track preload completed (points=%d, elapsed_ms=%d).",
            len(track_points),
            int((perf_counter() - preload_started) * 1000),
        )
    except Exception as exc:  # noqa: BLE001
        _live_track_preload = None
        LOGGER.warning("Track preload failed during startup: %s", exc)

    if token_provider is not None and _live_username and _mqtt_oauth_ready:
        use_websocket = os.getenv("OPENF1_LIVE_USE_WEBSOCKET", "false").strip().lower() == "true"
        LOGGER.info(
            "Initializing MQTT live client (transport=%s, username=%s).",
            "wss" if use_websocket else "mqtts",
            _email_for_logs(_live_username),
        )
        try:
            live_client = f1.create_live_client(
                token_provider=token_provider,
                username=_live_username,
                use_websocket=use_websocket,
            )
            live_client.start()
            _live_client = live_client
            LOGGER.info("MQTT live client started successfully.")
        except OpenF1LiveError as exc:
            _live_client = None
            LOGGER.warning("MQTT live client could not be started: %s", exc)
        except Exception as exc:  # noqa: BLE001
            _live_client = None
            LOGGER.exception("Unexpected error during MQTT live client startup: %s", exc)
    else:
        LOGGER.warning(
            "MQTT live client is disabled (token_provider_ready=%s, live_username_present=%s, mqtt_oauth_ready=%s).",
            token_provider is not None,
            bool(_live_username),
            _mqtt_oauth_ready,
        )
    LOGGER.info(
        "System init completed (server_ready=%s, auth_client_ready=%s, mqtt_oauth_ready=%s, live_client_ready=%s, track_preload_ready=%s).",
        True,
        _auth_client is not None,
        _mqtt_oauth_ready,
        _live_client is not None,
        _live_track_preload is not None,
    )


def system_shutdown() -> None:
    global _auth_client, _live_client, _history_replay_cache, _mqtt_oauth_ready, _live_track_preload

    LOGGER.info("System shutdown started.")
    if _live_client is not None:
        LOGGER.info("Stopping MQTT live client.")
        _live_client.stop()
        _live_client = None
    if _auth_client is not None:
        LOGGER.info("Closing OAuth client.")
        _auth_client.close()
        _auth_client = None
    _mqtt_oauth_ready = False
    _live_track_preload = None
    _history_replay_cache.clear()
    f1.close()
    LOGGER.info("System shutdown completed (server_ready=%s).", False)


@asynccontextmanager
async def lifespan(_: FastAPI):
    system_init()
    LOGGER.info(
        "Application startup complete (server_running=%s, auth_client_ready=%s, mqtt_oauth_ready=%s, live_client_ready=%s, track_preload_ready=%s).",
        True,
        _auth_client is not None,
        _mqtt_oauth_ready,
        _live_client is not None,
        _live_track_preload is not None,
    )
    try:
        yield
    finally:
        LOGGER.info("Application shutdown started (server_running=%s).", True)
        system_shutdown()
        LOGGER.info("Application shutdown complete (server_running=%s).", False)


app = FastAPI(title="openF1", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins_from_env(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# @app.get("/")
# def serve_index() -> FileResponse:
#     if not INDEX_HTML.exists():
#         raise HTTPException(status_code=404, detail=f"Missing file: {INDEX_HTML}")
#     return FileResponse(INDEX_HTML)
#
#
# @app.get("/app.js")
# def serve_app_js() -> FileResponse:
#     if not APP_JS.exists():
#         raise HTTPException(status_code=404, detail=f"Missing file: {APP_JS}")
#     return FileResponse(APP_JS, media_type="application/javascript")


def _serve_angular_index() -> FileResponse:
    if not ANGULAR_INDEX_HTML.exists():
        raise HTTPException(status_code=404, detail=f"Missing Angular build file: {ANGULAR_INDEX_HTML}")
    return FileResponse(ANGULAR_INDEX_HTML)


@app.get("/")
def serve_angular_index() -> FileResponse:
    return _serve_angular_index()

@app.get("/api/run")
def run() -> dict[str, Any]:
    request_started = perf_counter()
    LOGGER.info("GET /api/run started.")
    try:
        sessions = f1.session.latest()
        track_points, track_key = _resolve_live_track_points(sessions)
        drivers_payload, position_row_count, location_query_count = _build_drivers_payload(
            session_key=sessions.session_key,
            track_points=track_points,
        )

        payload = {
            "mode": "bootstrap",
            "session_key": sessions.session_key,
            "session_name": sessions.session_name,
            "session_type": sessions.session_type,
            "points": track_points,
            "circuit_name": sessions.circuit_short_name,
            "drivers": drivers_payload,
            "lap": _session_lap_payload(sessions.session_key),
        }
        LOGGER.info(
            "GET /api/run completed (circuit=%s, points=%d, drivers=%d, cache_key=%s, elapsed_ms=%d).",
            payload["circuit_name"],
            len(track_points),
            len(drivers_payload),
            track_key,
            int((perf_counter() - request_started) * 1000),
        )
        LOGGER.debug(
            "Aggregated rows (positions=%d), location queries=%d.",
            position_row_count,
            location_query_count,
        )
        return payload
    except HTTPException:
        LOGGER.exception("GET /api/run failed with HTTPException.")
        raise
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("GET /api/run failed with unexpected exception.")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/live")
def live() -> dict[str, Any]:
    LOGGER.info("GET /api/live started.")
    if _live_client is None:
        LOGGER.warning(
            "GET /api/live rejected: live client unavailable (auth_client_ready=%s, mqtt_oauth_ready=%s, live_username=%s).",
            _auth_client is not None,
            _mqtt_oauth_ready,
            _email_for_logs(_live_username),
        )
        raise HTTPException(
            status_code=503,
            detail="Live MQTT client is not available. Configure OAuth and restart the service.",
        )

    try:
        snapshot = _live_client.get_snapshot()
        LOGGER.info(
            "GET /api/live completed (session_key=%s, drivers=%d, lap=%s).",
            snapshot.get("session_key"),
            len(snapshot.get("drivers", [])),
            snapshot.get("lap", {}).get("display") if isinstance(snapshot.get("lap"), dict) else None,
        )
        return snapshot
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("GET /api/live failed.")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/insights/weather")
def insights_weather(
    history_limit: int = Query(default=20, ge=1, le=120),
) -> dict[str, Any]:
    request_started = perf_counter()
    LOGGER.info("GET /api/insights/weather started (history_limit=%s).", history_limit)
    try:
        session = f1.session.latest(meeting_key="latest", session_key="latest")
        cache_key = f"insights:weather:{session.session_key}"
        weather_rows = f1.get_or_load_cached(
            key=cache_key,
            loader=lambda: f1.weather.list(session_key=session.session_key),
            ttl_seconds=3.0,
        )
        if not weather_rows:
            raise HTTPException(status_code=404, detail="No weather data available for current session.")

        sorted_rows = sorted(weather_rows, key=lambda row: row.date)
        latest = sorted_rows[-1]
        history = [_weather_row_payload(row) for row in sorted_rows[-history_limit:]]

        payload = {
            "session_key": session.session_key,
            "meeting_key": session.meeting_key,
            "session_name": session.session_name,
            "session_type": session.session_type,
            "circuit_name": session.circuit_short_name,
            "latest": _weather_row_payload(latest),
            "history": history,
            "generated_at": _utc_now_iso_z(),
        }
        LOGGER.info(
            "GET /api/insights/weather completed (session_key=%s, rows=%d, elapsed_ms=%d).",
            session.session_key,
            len(history),
            int((perf_counter() - request_started) * 1000),
        )
        return payload
    except HTTPException:
        LOGGER.exception("GET /api/insights/weather failed with HTTPException.")
        raise
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("GET /api/insights/weather failed.")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/insights/team-radio")
def insights_team_radio(
    limit: int = Query(default=30, ge=1, le=150),
) -> dict[str, Any]:
    request_started = perf_counter()
    LOGGER.info("GET /api/insights/team-radio started (limit=%s).", limit)
    try:
        session = f1.session.latest(meeting_key="latest", session_key="latest")
        cache_key = f"insights:team_radio:{session.session_key}"
        rows = f1.get_or_load_cached(
            key=cache_key,
            loader=lambda: f1.team_radio.list(session_key=session.session_key),
            ttl_seconds=5.0,
        )
        sorted_rows = sorted(rows, key=lambda row: row.date, reverse=True)
        selected = sorted_rows[:limit]

        drivers = f1.get_or_load_cached(
            key=f"insights:drivers:{session.session_key}",
            loader=lambda: f1.driver.list(session_key=session.session_key),
            ttl_seconds=60.0,
        )
        drivers_by_number: dict[int, dict[str, Any]] = {}
        for driver in drivers:
            drivers_by_number[driver.driver_number] = driver.model_dump()

        events = []
        for row in selected:
            driver_meta = drivers_by_number.get(row.driver_number, {})
            full_name = (
                driver_meta.get("full_name")
                or f"{driver_meta.get('first_name', '')} {driver_meta.get('last_name', '')}".strip()
                or driver_meta.get("name_acronym")
            )
            events.append(
                {
                    "date": row.date,
                    "driver_number": row.driver_number,
                    "driver_name": full_name,
                    "team_name": driver_meta.get("team_name"),
                    "team_colour": driver_meta.get("team_colour"),
                    "recording_url": row.recording_url,
                }
            )

        payload = {
            "session_key": session.session_key,
            "meeting_key": session.meeting_key,
            "session_name": session.session_name,
            "session_type": session.session_type,
            "circuit_name": session.circuit_short_name,
            "events": events,
            "count": len(events),
            "generated_at": _utc_now_iso_z(),
        }
        LOGGER.info(
            "GET /api/insights/team-radio completed (session_key=%s, events=%d, elapsed_ms=%d).",
            session.session_key,
            len(events),
            int((perf_counter() - request_started) * 1000),
        )
        return payload
    except HTTPException:
        LOGGER.exception("GET /api/insights/team-radio failed with HTTPException.")
        raise
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("GET /api/insights/team-radio failed.")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/history/sessions")
def history_sessions(
    year: Optional[int] = Query(default=None),
    limit: int = Query(default=80, ge=1, le=400),
) -> dict[str, Any]:
    LOGGER.info("GET /api/history/sessions started (year=%s, limit=%s).", year, limit)
    try:
        filters: dict[str, Any] = {}
        if year is not None:
            filters["year"] = year
        session_rows = f1.session.list(**filters)
        sorted_rows = sorted(session_rows, key=lambda row: row.date_start, reverse=True)
        selected_rows = sorted_rows[:limit]

        payload = [
            {
                "session_key": row.session_key,
                "meeting_key": row.meeting_key,
                "year": row.year,
                "session_name": row.session_name,
                "session_type": row.session_type,
                "circuit_name": row.circuit_short_name,
                "country_name": row.country_name,
                "location": row.location,
                "date_start": row.date_start,
            }
            for row in selected_rows
        ]
        LOGGER.info("GET /api/history/sessions completed (count=%d).", len(payload))
        return {"sessions": payload}
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("GET /api/history/sessions failed.")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/history")
def history(session_key: int = Query(...)) -> dict[str, Any]:
    request_started = perf_counter()
    LOGGER.info("GET /api/history started (session_key=%s).", session_key)
    try:
        rows = f1.session.list(session_key=session_key)
        if not rows:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_key}")
        session = rows[0]
        track_key = _track_cache_key(session)
        track_points = f1.get_or_load_cached(
            key=track_key,
            loader=lambda: f1.get_track(session),
            ttl_seconds=TRACK_CACHE_TTL_SECONDS,
        )
        drivers_payload, position_row_count, location_query_count = _build_drivers_payload(
            session_key=session.session_key,
            track_points=track_points,
        )
        lap_payload = _session_lap_payload(session.session_key)
        position_timestamp = max(
            (
                row.get("position_date")
                for row in drivers_payload
                if isinstance(row.get("position_date"), str)
            ),
            default=None,
        )

        payload = {
            "mode": "historical",
            "session_key": session.session_key,
            "meeting_key": session.meeting_key,
            "session_name": session.session_name,
            "session_type": session.session_type,
            "circuit_name": session.circuit_short_name,
            "date_start": session.date_start,
            "track": track_points,
            "drivers": drivers_payload,
            "lap": lap_payload,
            "position_timestamp": position_timestamp,
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        LOGGER.info(
            "GET /api/history completed (session_key=%s, points=%d, drivers=%d, elapsed_ms=%d).",
            session_key,
            len(track_points),
            len(drivers_payload),
            int((perf_counter() - request_started) * 1000),
        )
        LOGGER.debug(
            "Historical aggregate (positions=%d, location_queries=%d).",
            position_row_count,
            location_query_count,
        )
        return payload
    except HTTPException:
        LOGGER.exception("GET /api/history failed with HTTPException.")
        raise
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("GET /api/history failed.")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/history/playback")
def history_playback(
    session_key: int = Query(...),
    sample_step: int = Query(default=1, ge=1, le=25),
) -> dict[str, Any]:
    request_started = perf_counter()
    LOGGER.info(
        "GET /api/history/playback started (session_key=%s, sample_step=%s).",
        session_key,
        sample_step,
    )
    try:
        rows = f1.session.list(session_key=session_key)
        if not rows:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_key}")
        session = rows[0]
        track_key = _track_cache_key(session)
        track_points = f1.get_or_load_cached(
            key=track_key,
            loader=lambda: f1.get_track(session),
            ttl_seconds=TRACK_CACHE_TTL_SECONDS,
        )
        position_rows_by_driver = _build_position_rows_by_driver(session.session_key)
        drivers_payload, position_row_count = _build_driver_metadata_payload(
            session_key=session.session_key,
            track_points=track_points,
            position_rows_by_driver=position_rows_by_driver,
            include_location_seed=False,
        )

        driver_numbers = [
            driver_row["driver_number"]
            for driver_row in drivers_payload
            if isinstance(driver_row.get("driver_number"), int)
        ]
        events, location_query_count = _build_history_playback_events(
            session_key=session.session_key,
            track_points=track_points,
            driver_numbers=driver_numbers,
            sample_step=sample_step,
            position_rows_by_driver=position_rows_by_driver,
        )
        lap_payload = _session_lap_payload(session.session_key)
        if events:
            lap_payload["current"] = 1
            if isinstance(lap_payload.get("max"), int):
                lap_payload["display"] = f"1/{lap_payload['max']}"
            else:
                lap_payload["display"] = "1/-"

        payload = {
            "mode": "historical_playback",
            "session_key": session.session_key,
            "meeting_key": session.meeting_key,
            "session_name": session.session_name,
            "session_type": session.session_type,
            "circuit_name": session.circuit_short_name,
            "date_start": session.date_start,
            "track": track_points,
            "drivers": drivers_payload,
            "lap": lap_payload,
            "playback": {
                "sample_step": sample_step,
                "event_count": len(events),
                "started_at": events[0]["date"] if events else None,
                "ended_at": events[-1]["date"] if events else None,
                "events": events,
            },
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        LOGGER.info(
            "GET /api/history/playback completed (session_key=%s, events=%d, drivers=%d, elapsed_ms=%d).",
            session_key,
            len(events),
            len(drivers_payload),
            int((perf_counter() - request_started) * 1000),
        )
        LOGGER.debug(
            "History playback aggregate (positions=%d, location_queries=%d).",
            position_row_count,
            location_query_count,
        )
        return payload
    except HTTPException:
        LOGGER.exception("GET /api/history/playback failed with HTTPException.")
        raise
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("GET /api/history/playback failed.")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/history/replay/init")
def history_replay_init(session_key: int = Query(...)) -> dict[str, Any]:
    request_started = perf_counter()
    LOGGER.info("GET /api/history/replay/init started (session_key=%s).", session_key)
    try:
        context = _ensure_history_replay_context(session_key=session_key)
        session = context["session"]
        lap_numbers: list[int] = context["lap_numbers"]
        lap_payload = dict(context["lap_payload"])
        first_lap = lap_numbers[0] if lap_numbers else 1
        lap_max = lap_payload.get("max") if isinstance(lap_payload.get("max"), int) else None
        lap_payload["current"] = first_lap
        lap_payload["display"] = f"{first_lap}/{lap_max if lap_max is not None else '-'}"

        payload = {
            "mode": "historical_replay",
            "session_key": session.session_key,
            "meeting_key": session.meeting_key,
            "session_name": session.session_name,
            "session_type": session.session_type,
            "circuit_name": session.circuit_short_name,
            "date_start": session.date_start,
            "track": context["track_points"],
            "drivers": context["drivers_payload"],
            "lap": lap_payload,
            "replay": {
                "lap_numbers": lap_numbers,
                "first_lap": first_lap,
                "last_lap": lap_numbers[-1] if lap_numbers else first_lap,
            },
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        LOGGER.info(
            "GET /api/history/replay/init completed (session_key=%s, laps=%d, drivers=%d, elapsed_ms=%d).",
            session_key,
            len(lap_numbers),
            len(context["drivers_payload"]),
            int((perf_counter() - request_started) * 1000),
        )
        return payload
    except HTTPException:
        LOGGER.exception("GET /api/history/replay/init failed with HTTPException.")
        raise
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("GET /api/history/replay/init failed.")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/history/replay/lap")
def history_replay_lap(
    session_key: int = Query(...),
    lap_number: int = Query(..., ge=1),
    sample_step: int = Query(default=1, ge=1, le=25),
) -> dict[str, Any]:
    request_started = perf_counter()
    LOGGER.info(
        "GET /api/history/replay/lap started (session_key=%s, lap_number=%s, sample_step=%s).",
        session_key,
        lap_number,
        sample_step,
    )
    try:
        context = _ensure_history_replay_context(session_key=session_key)
        lap_windows: dict[int, tuple[str, Optional[str]]] = context["lap_windows"]
        if lap_number not in lap_windows:
            raise HTTPException(status_code=404, detail=f"Lap not found: {lap_number}")
        start, end = lap_windows[lap_number]

        events, location_query_count = _build_lap_events_for_window(
            session_key=session_key,
            track_points=context["track_points"],
            driver_numbers=context["driver_numbers"],
            lap_number=lap_number,
            start=start,
            end=end,
            sample_step=sample_step,
            position_rows_by_driver=context.get("position_rows_by_driver"),
        )

        lap_payload = dict(context["lap_payload"])
        lap_max = lap_payload.get("max") if isinstance(lap_payload.get("max"), int) else None
        lap_payload["current"] = lap_number
        lap_payload["display"] = f"{lap_number}/{lap_max if lap_max is not None else '-'}"

        payload = {
            "mode": "historical_replay_lap",
            "session_key": session_key,
            "lap": lap_payload,
            "playback": {
                "lap_number": lap_number,
                "sample_step": sample_step,
                "event_count": len(events),
                "started_at": events[0]["date"] if events else start,
                "ended_at": events[-1]["date"] if events else end,
                "events": events,
            },
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        LOGGER.info(
            "GET /api/history/replay/lap completed (session_key=%s, lap=%s, events=%d, location_queries=%d, elapsed_ms=%d).",
            session_key,
            lap_number,
            len(events),
            location_query_count,
            int((perf_counter() - request_started) * 1000),
        )
        return payload
    except HTTPException:
        LOGGER.exception("GET /api/history/replay/lap failed with HTTPException.")
        raise
    except Exception as exc:  # noqa: BLE001
        LOGGER.exception("GET /api/history/replay/lap failed.")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/{asset_path:path}")
def serve_angular_asset(asset_path: str) -> FileResponse:
    if not asset_path or asset_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")

    candidate_path = (ANGULAR_DIST_ROOT / asset_path).resolve()
    try:
        candidate_path.relative_to(ANGULAR_DIST_ROOT.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid asset path") from exc

    if candidate_path.is_file():
        return FileResponse(candidate_path)
    return _serve_angular_index()


if __name__ == "__main__":
    import uvicorn

    LOGGER.info("Starting uvicorn server (entrypoint=main.py).")
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
