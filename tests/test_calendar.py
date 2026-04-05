import json

import pytest

from menu_calendario_mcp.errors import ConflictError, NotFoundError, ValidationError
from menu_calendario_mcp.macos.applescript import AppleScriptRunner
from menu_calendario_mcp.macos.calendar import CalendarService
from menu_calendario_mcp.models import CalendarSourceInfo


class StubCalendarRunner(AppleScriptRunner):
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.calendars = [{"name": "Home", "color": "red"}]

    def run_json(self, script: str) -> object:
        self.calls.append(script)
        data = _embedded_payload(script)
        if "const result = calendar.calendars().map" in script:
            return list(self.calendars)
        if "const calendar = app.Calendar({name: payload.name});" in script:
            row = {"name": data["name"], "color": "blue"}
            self.calendars.append(row)
            return {
                "name": row["name"],
                "color": row["color"],
            }
        if "deleted" in script:
            if "calendar_index" in data:
                del self.calendars[data["calendar_index"]]
                return {"deleted": True, "calendar_id": data["calendar_index"]}
            return {"deleted": True, "event_id": data["event_id"]}
        if "calendar.no longer matches" in script or "currentName !== payload.expected_name" in script:
            self.calendars[data["calendar_index"]]["name"] = data["new_name"]
            return {
                "name": self.calendars[data["calendar_index"]]["name"],
                "color": self.calendars[data["calendar_index"]]["color"],
            }
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


class StubEventKitManager:
    def __init__(self, runner: StubCalendarRunner | None = None) -> None:
        self.create_calls: list[tuple[str, str]] = []
        self.runner = runner

    def list_sources(self) -> list[CalendarSourceInfo]:
        return [
            CalendarSourceInfo(
                source_id="icloud",
                title="iCloud",
                source_type="caldav",
                allows_calendar_creation=True,
            )
        ]

    def create_calendar(self, *, name: str, source_id: str) -> None:
        self.create_calls.append((name, source_id))
        if self.runner is not None:
            self.runner.calendars.append({"name": name, "color": "blue"})


def test_list_calendars_returns_models() -> None:
    service = CalendarService(runner=StubCalendarRunner(), default_calendar_name="Home")
    calendars = service.list_calendars()
    assert calendars[0].name == "Home"
    assert calendars[0].is_default is True
    assert calendars[0].calendar_id


def test_create_calendar_requires_name() -> None:
    service = CalendarService(runner=StubCalendarRunner())
    with pytest.raises(ValidationError):
        service.create_calendar(name="")


def test_update_calendar_requires_name() -> None:
    service = CalendarService(runner=StubCalendarRunner())
    with pytest.raises(ValidationError):
        service.update_calendar(calendar_id="", new_name="Renamed")


def test_update_calendar_requires_fields() -> None:
    service = CalendarService(runner=StubCalendarRunner())
    with pytest.raises(ValidationError):
        service.update_calendar(calendar_id="bad", new_name=None)


def test_delete_calendar_requires_name() -> None:
    service = CalendarService(runner=StubCalendarRunner())
    with pytest.raises(ValidationError):
        service.delete_calendar(calendar_id="")


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


def test_create_calendar_returns_info() -> None:
    service = CalendarService(runner=StubCalendarRunner())
    result = service.create_calendar(name="Travel")
    assert result.name == "Travel"
    assert result.calendar_id


def test_list_sources_delegates_to_eventkit() -> None:
    manager = StubEventKitManager()
    service = CalendarService(runner=StubCalendarRunner(), eventkit=manager)

    result = service.list_sources()

    assert result == [
        CalendarSourceInfo(
            source_id="icloud",
            title="iCloud",
            source_type="caldav",
            allows_calendar_creation=True,
        )
    ]


def test_create_calendar_uses_source_id_when_provided() -> None:
    runner = StubCalendarRunner()
    manager = StubEventKitManager(runner=runner)
    service = CalendarService(runner=runner, eventkit=manager)

    result = service.create_calendar(name="Travel", source_id="icloud")

    assert manager.create_calls == [("Travel", "icloud")]
    assert result.name == "Travel"
    assert result.calendar_id
    assert all("app.Calendar({name: payload.name})" not in call for call in runner.calls)


def test_update_calendar_returns_info() -> None:
    service = CalendarService(runner=StubCalendarRunner())
    created = service.create_calendar(name="Travel")
    result = service.update_calendar(calendar_id=created.calendar_id, new_name="Trips")
    assert result.name == "Trips"
    assert result.calendar_id != created.calendar_id


def test_delete_calendar_returns_confirmation() -> None:
    service = CalendarService(runner=StubCalendarRunner())
    created = service.create_calendar(name="Travel")
    result = service.delete_calendar(calendar_id=created.calendar_id)
    assert result == {"deleted": True, "calendar_id": 1}


def _embedded_payload(script: str) -> dict[str, object]:
    marker = "const payload = "
    start = script.index(marker) + len(marker)
    end = script.index(";\n\nfunction isoString", start)
    return json.loads(script[start:end])
