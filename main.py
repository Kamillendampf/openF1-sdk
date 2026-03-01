
from __future__ import annotations

from datetime import datetime
from math import hypot
from pathlib import Path
from statistics import median
from typing import Any

import f1_sdk as f1
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

f1.configure(
    f1.F1Config(
        rate_limit_enabled=True,
        pause_every_requests=3,
        pause_seconds=1.0,
    )
)

app = FastAPI(title="openF1")
WEB_ROOT = Path(__file__).resolve().parent / "web"
INDEX_HTML = WEB_ROOT / "index.html"


def filter_track_points(
    track_points: list[dict[str, int]],
    jump_factor: float = 15.0,
    min_segment_size: int = 1,
) -> list[dict[str, int]]:
    print("filtering track points")
    if len(track_points) < 3:
        return track_points

    distances = [
        hypot(
            track_points[i + 1]["x"] - track_points[i]["x"],
            track_points[i + 1]["y"] - track_points[i]["y"],
        )
        for i in range(len(track_points) - 1)
    ]
    non_zero_distances = [d for d in distances if d > 0]
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


def get_track_points(session_latest):

    #get event data
    session_type = session_latest.session_type
    session_name = session_latest.session_name
    current_year = session_latest.date_start
    dt = datetime.fromisoformat(current_year)
    last_year = current_year.replace(str(dt.year), str(dt.year -1))
    last_year_formated = datetime.fromisoformat(last_year).strftime("%Y")


    circuit_key = session_latest.circuit_key

    #get driver number
    last_session = f1.session.list(circuit_key=circuit_key, year=last_year_formated, session_type=session_type, session_name=session_name)
    last_session_key = last_session[0].session_key
    driver_number = f1.session_result.list(session_key=last_session_key, position=1)[0].driver_number

    #get driver positions
    locations = f1.location.list(session_key=last_session_key, driver_number=driver_number)
    track_points =  [
        {"x" : location.x, "y" : location.y, "z" : location.z}
        for location in locations
    ]
    track_points = filter_track_points(track_points)
    print(track_points)
    return filter_track_points(track_points)


@app.get("/")
def serve_index() -> FileResponse:
    if not INDEX_HTML.exists():
        raise HTTPException(status_code=404, detail=f"Missing file: {INDEX_HTML}")
    return FileResponse(INDEX_HTML)

@app.get("/api/run")
def run() -> dict[str, Any]:
    try:
        sessions = f1.session.latest()
        track_points = get_track_points(sessions)
        session_type = sessions.session_type
        session_name = sessions.session_name
        current_year = sessions.date_start
        dt = datetime.fromisoformat(current_year)
        last_year = current_year.replace(str(dt.year), str(dt.year - 1))
        last_year_formated = datetime.fromisoformat(last_year).strftime("%Y")

        reference_session = f1.session.list(
            circuit_key=sessions.circuit_key,
            year=last_year_formated,
            session_type=session_type,
            session_name=session_name,
        )[0]
        drivers = f1.driver.list(session_key=reference_session.session_key)

        drivers_payload: list[dict[str, Any]] = []
        for driver in drivers:
            payload = driver.model_dump()
            payload["track_point"] = None

            locations = f1.location.list(
                session_key=reference_session.session_key,
                driver_number=driver.driver_number,
            )
            if locations:
                latest_location = max(locations, key=lambda location: location.date)
                snapped = (
                    min(
                        track_points,
                        key=lambda point: (
                            (point["x"] - latest_location.x) ** 2
                            + (point["y"] - latest_location.y) ** 2
                            + (point["z"] - latest_location.z) ** 2
                        ),
                    )
                    if track_points
                    else {"x": latest_location.x, "y": latest_location.y, "z": latest_location.z}
                )
                payload["track_point"] = {
                    "x": snapped["x"],
                    "y": snapped["y"],
                    "z": snapped["z"],
                    "date": latest_location.date,
                }

            drivers_payload.append(payload)

        return {
            "points": track_points,
            "circuit_name": sessions.circuit_short_name,
            "drivers": drivers_payload,
        }
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
