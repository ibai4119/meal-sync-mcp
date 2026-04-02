import json

import pytest

from menu_calendario_mcp.errors import ConflictError, NotFoundError, ValidationError
from menu_calendario_mcp.macos.applescript import AppleScriptRunner
from menu_calendario_mcp.macos.calendar import CalendarService


class StubCalendarRunner(AppleScriptRunner):
    def __init__(self) -> None:
        self.calls: list[str] = []

    def run_json(self, script: str) -> object:
        self.calls.append(script)
        data = _embedded_payload(script)
        if "deleted" in script:
            return {"deleted": True, "event_id": data["event_id"]}
        if "calendars().map" in script:
            return [{"name": "Home", "color": "red", "is_default": True}]
        if "const events = [];" in script:
            return [
                {
                    "event_id": "abc123",
                    "calendar_name": "Home",
                    "title": "Meeting",
                    "start_iso": "2026-03-22T10:00:00",
                    "end_iso": "2026-03-22T11:00:00",
                    "all_day": False,
                    "location": None,
                    "notes": None,
                }
            ]
        return {
            "event_id": data.get("event_id", "abc123"),
            "calendar_name": data.get("calendar_name", "Home"),
            "title": data.get("title", "Meeting"),
            "start_iso": data.get("start_iso", "2026-03-22T10:00:00"),
            "end_iso": data.get("end_iso", "2026-03-22T11:00:00"),
            "all_day": bool(data.get("all_day", False)),
            "location": data.get("location"),
            "notes": data.get("notes"),
        }


def test_list_calendars_returns_models() -> None:
    service = CalendarService(runner=StubCalendarRunner())
    calendars = service.list_calendars()
    assert calendars[0].name == "Home"
    assert calendars[0].is_default is True


def test_list_events_uses_overlap_filter_in_script() -> None:
    runner = StubCalendarRunner()
    service = CalendarService(runner=runner)

    service.list_events(start_iso="2026-03-22T10:00:00", end_iso="2026-03-22T11:00:00")

    script = runner.calls[0]
    assert "eventStart < endDate && eventEnd > startDate" in script
    assert '"calendar_name": null' in script
    assert '"query": ""' in script
    assert '"start_iso": "2026-03-22T10:00:00' in script
    assert '"end_iso": "2026-03-22T11:00:00' in script


def test_create_event_requires_title() -> None:
    service = CalendarService(runner=StubCalendarRunner(), default_calendar_name="Home")
    with pytest.raises(ValidationError):
        service.create_event(title="", start_iso="2026-03-22T10:00:00", end_iso="2026-03-22T11:00:00")


def test_create_event_requires_calendar_when_no_default() -> None:
    service = CalendarService(runner=StubCalendarRunner())
    with pytest.raises(ValidationError):
        service.create_event(
            title="Meeting",
            start_iso="2026-03-22T10:00:00",
            end_iso="2026-03-22T11:00:00",
        )


def test_update_event_requires_fields() -> None:
    service = CalendarService(runner=StubCalendarRunner())
    with pytest.raises(ValidationError):
        service.update_event(event_id="abc123")


def test_update_event_requires_both_dates() -> None:
    service = CalendarService(runner=StubCalendarRunner())
    with pytest.raises(ConflictError):
        service.update_event(event_id="abc123", start_iso="2026-03-22T10:00:00")


def test_delete_event_returns_confirmation() -> None:
    service = CalendarService(runner=StubCalendarRunner())
    result = service.delete_event(event_id="abc123")
    assert result == {"deleted": True, "event_id": "abc123"}


def _embedded_payload(script: str) -> dict[str, object]:
    marker = "const payload = "
    start = script.index(marker) + len(marker)
    end = script.index(";\n\nfunction isoString", start)
    return json.loads(script[start:end])
