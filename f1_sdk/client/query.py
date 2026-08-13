from __future__ import annotations

from typing import Any, Mapping


def _to_str(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def build_query(params: Mapping[str, Any] | None) -> dict[str, str]:
    """
    Convert Python values to query-string values.
    - drops None values
    - list/tuple -> comma-separated values
    """
    out: dict[str, str] = {}
    if not params:
        return out

    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            out[key] = ",".join(_to_str(v) for v in value if v is not None)
            continue
        out[key] = _to_str(value)

    return out
