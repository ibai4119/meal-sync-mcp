from pathlib import Path

import pytest

from menu_calendario_mcp.errors import ConflictError, ValidationError
from menu_calendario_mcp.utils import parse_iso_datetime, require_absolute_path, validate_time_range


def test_parse_iso_datetime_accepts_iso_string() -> None:
    parsed = parse_iso_datetime("2026-03-22T10:00:00", field_name="start_iso")
    assert parsed.year == 2026
    assert parsed.hour == 10


def test_parse_iso_datetime_rejects_invalid_format() -> None:
    with pytest.raises(ValidationError):
        parse_iso_datetime("2026/03/22 10:00", field_name="start_iso")


def test_validate_time_range_requires_end_after_start() -> None:
    with pytest.raises(ConflictError):
        validate_time_range("2026-03-22T10:00:00", "2026-03-22T09:00:00")


def test_require_absolute_path_rejects_relative_paths() -> None:
    with pytest.raises(ValidationError):
        require_absolute_path("docs/file.txt")


def test_require_absolute_path_accepts_absolute_paths() -> None:
    path = require_absolute_path("/tmp/example.txt")
    assert path == Path("/tmp/example.txt")
