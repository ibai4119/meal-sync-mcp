import json

import pytest

from menu_calendario_mcp.errors import ConflictError, ValidationError
from menu_calendario_mcp.macos.applescript import AppleScriptRunner
from menu_calendario_mcp.macos.reminders import RemindersService


class StubRemindersRunner(AppleScriptRunner):
    def __init__(self) -> None:
        self.calls: list[str] = []

    def run_json(self, script: str) -> object:
        self.calls.append(script)
        payload = _embedded_payload(script)
        if "lists().map" in script:
            return [{"name": "Inbox", "is_default": True}]
        return {
            "reminder_id": payload.get("reminder_id", "rem-123"),
            "list_name": payload.get("list_name", "Inbox"),
            "title": payload.get("title", "Comprar pan"),
            "is_completed": "completed = true" in script or payload.get("is_completed", False),
            "due_iso": payload.get("due_iso"),
            "notes": payload.get("notes"),
        }


def test_list_lists_returns_models() -> None:
    service = RemindersService(runner=StubRemindersRunner(), default_list_name="Inbox")
    lists = service.list_lists()
    assert lists[0].name == "Inbox"
    assert lists[0].is_default is True


def test_create_item_requires_title() -> None:
    service = RemindersService(runner=StubRemindersRunner(), default_list_name="Inbox")
    with pytest.raises(ValidationError):
        service.create_item(title="")


def test_create_item_requires_list_when_no_default() -> None:
    service = RemindersService(runner=StubRemindersRunner())
    with pytest.raises(ValidationError):
        service.create_item(title="Comprar leche")


def test_complete_item_marks_completed() -> None:
    service = RemindersService(runner=StubRemindersRunner())
    item = service.complete_item(reminder_id="rem-123")
    assert item.is_completed is True
    assert item.reminder_id == "rem-123"


def _embedded_payload(script: str) -> dict[str, object]:
    marker = "const payload = "
    start = script.index(marker) + len(marker)
    end = script.index(";\n\nfunction isoString", start)
    return json.loads(script[start:end])
