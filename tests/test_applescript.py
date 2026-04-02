from menu_calendario_mcp.errors import AutomationPermissionError, McpMacError, NotFoundError, ValidationError
from menu_calendario_mcp.macos.applescript import jxa_program, map_osascript_error


def test_jxa_program_embeds_payload_without_breaking_quotes() -> None:
    script = jxa_program("  return toJson(payload);", {"title": 'He said "hello"\nline'})
    assert 'He said \\"hello\\"\\nline' in script


def test_map_osascript_error_permission() -> None:
    err = map_osascript_error("Execution error: Not authorized to send Apple events to Calendar. (-1743)")
    assert isinstance(err, AutomationPermissionError)


def test_map_osascript_error_not_found() -> None:
    err = map_osascript_error("Finder got an error: Can’t get file")
    assert isinstance(err, NotFoundError)


def test_map_osascript_error_validation() -> None:
    err = map_osascript_error("Execution error: Expected end of line but found identifier.")
    assert isinstance(err, ValidationError)


def test_map_osascript_error_fallback() -> None:
    err = map_osascript_error("Something odd happened")
    assert isinstance(err, McpMacError)
