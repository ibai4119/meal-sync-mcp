"""Validation and serialization helpers shared across the project."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .errors import ConflictError, ValidationError


def parse_iso_datetime(value: str, *, field_name: str) -> datetime:
    """Parse an ISO datetime string and reject malformed values."""

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError(
            f"'{field_name}' must be a valid ISO datetime like 2026-03-22T10:00:00"
        ) from exc
    if parsed.tzinfo is None:
        return parsed.astimezone()
    return parsed


def validate_time_range(start_iso: str, end_iso: str) -> tuple[datetime, datetime]:
    """Parse and validate an ordered start/end datetime pair."""

    start = parse_iso_datetime(start_iso, field_name="start_iso")
    end = parse_iso_datetime(end_iso, field_name="end_iso")
    if end <= start:
        raise ConflictError("'end_iso' must be later than 'start_iso'")
    return start, end


def require_absolute_path(path: str) -> Path:
    """Expand a path and ensure it is absolute."""

    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        raise ValidationError("'path' must be an absolute path")
    return candidate


def json_text(payload: object) -> str:
    """Render payloads as deterministic pretty JSON for text responses."""

    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
