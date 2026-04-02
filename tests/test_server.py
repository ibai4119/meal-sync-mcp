import anyio
import pytest

from menu_calendario_mcp.server import build_services, call_tool


@pytest.mark.anyio
async def test_unknown_tool_returns_error() -> None:
    result = await call_tool("does_not_exist", {})
    assert result.isError is True
    assert "Unknown tool" in result.content[0].text


@pytest.mark.anyio
async def test_list_tools_includes_reminders_tools() -> None:
    from menu_calendario_mcp.server import list_tools

    tools = await list_tools()
    names = {tool.name for tool in tools}
    assert "calendar_create_calendar" in names
    assert "calendar_update_calendar" in names
    assert "calendar_delete_calendar" in names
    assert "reminders_list_lists" in names
    assert "reminders_list_items" in names
    assert "reminders_create_item" in names
    assert "reminders_complete_item" in names


def test_build_services_reads_current_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MENU_CALENDARIO_DEFAULT_CALENDAR", "Home")
    monkeypatch.setenv("MENU_CALENDARIO_DEFAULT_REMINDER_LIST", "Inbox")
    services = build_services()

    assert services.calendar.default_calendar_name == "Home"
    assert services.reminders.default_list_name == "Inbox"

    monkeypatch.setenv("MENU_CALENDARIO_DEFAULT_CALENDAR", "Work")
    monkeypatch.setenv("MENU_CALENDARIO_DEFAULT_REMINDER_LIST", "Today")
    services = build_services()

    assert services.calendar.default_calendar_name == "Work"
    assert services.reminders.default_list_name == "Today"
