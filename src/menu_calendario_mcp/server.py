"""MCP server wiring for the macOS Calendar, Reminders, and Finder tools."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from importlib.metadata import version
from typing import Any

import mcp.server.stdio
import mcp.types as types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from .config import load_settings
from .errors import McpMacError
from .macos import CalendarService, FinderService, RemindersService
from .macos.applescript import AppleScriptRunner
from .utils import json_text

SERVER_NAME = "menu-calendario-mcp"
SERVER_VERSION = version("menu-calendario-mcp")

server = Server(
    SERVER_NAME,
    version=SERVER_VERSION,
    instructions=(
        "Local macOS MCP server for Calendar, Reminders and Finder. "
        "Calendar changes should use exact event IDs for updates and deletions. "
        "Reminder changes should use exact reminder IDs for completions. "
        "Finder operations are limited to read and reveal flows."
    ),
)

@dataclass(slots=True)
class ServiceContainer:
    """Concrete service instances used to satisfy a tool call."""

    calendar: CalendarService
    finder: FinderService
    reminders: RemindersService


def build_services() -> ServiceContainer:
    """Create service instances using the current environment configuration."""

    settings = load_settings()
    return ServiceContainer(
        calendar=CalendarService(
            runner=AppleScriptRunner(),
            default_calendar_name=settings.default_calendar_name,
        ),
        finder=FinderService(runner=AppleScriptRunner()),
        reminders=RemindersService(
            runner=AppleScriptRunner(),
            default_list_name=settings.default_reminder_list,
        ),
    )


def _success(payload: Any) -> types.CallToolResult:
    """Wrap a successful tool payload as both text and structured MCP content."""

    structured = payload if isinstance(payload, dict) else {"items": payload}
    text = json_text(payload)
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=text)],
        structuredContent=structured,
        isError=False,
    )


def _error(exc: Exception) -> types.CallToolResult:
    """Convert an exception into a structured MCP tool error response."""

    return types.CallToolResult(
        content=[types.TextContent(type="text", text=str(exc))],
        structuredContent={"error": str(exc), "type": exc.__class__.__name__},
        isError=True,
    )


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """Return the tool catalog exposed by this server."""

    return [
        types.Tool(
            name="calendar_list_calendars",
            description="List macOS Calendar calendars and mark the default calendar when available.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="calendar_create_calendar",
            description="Create a macOS Calendar calendar using an exact name.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                },
                "required": ["name"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="calendar_update_calendar",
            description="Update a macOS Calendar calendar using its opaque calendar_id from calendar_list_calendars.",
            inputSchema={
                "type": "object",
                "properties": {
                    "calendar_id": {"type": "string"},
                    "new_name": {"type": "string"},
                },
                "required": ["calendar_id"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="calendar_delete_calendar",
            description="Delete a macOS Calendar calendar using its opaque calendar_id from calendar_list_calendars.",
            inputSchema={
                "type": "object",
                "properties": {
                    "calendar_id": {"type": "string"},
                },
                "required": ["calendar_id"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="calendar_list_events",
            description="List Calendar events inside a bounded time range, optionally filtering by calendar and text query.",
            inputSchema={
                "type": "object",
                "properties": {
                    "calendar_name": {"type": "string"},
                    "start_iso": {"type": "string"},
                    "end_iso": {"type": "string"},
                    "query": {"type": "string"},
                },
                "required": ["start_iso", "end_iso"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="calendar_create_event",
            description="Create a Calendar event in a specific calendar or in the configured default calendar.",
            inputSchema={
                "type": "object",
                "properties": {
                    "calendar_name": {"type": "string"},
                    "title": {"type": "string"},
                    "start_iso": {"type": "string"},
                    "end_iso": {"type": "string"},
                    "all_day": {"type": "boolean"},
                    "location": {"type": "string"},
                    "notes": {"type": "string"},
                },
                "required": ["title", "start_iso", "end_iso"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="calendar_update_event",
            description="Update a Calendar event using its exact event_id.",
            inputSchema={
                "type": "object",
                "properties": {
                    "event_id": {"type": "string"},
                    "title": {"type": "string"},
                    "start_iso": {"type": "string"},
                    "end_iso": {"type": "string"},
                    "all_day": {"type": "boolean"},
                    "location": {"type": "string"},
                    "notes": {"type": "string"},
                },
                "required": ["event_id"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="calendar_delete_event",
            description="Delete a Calendar event using its exact event_id.",
            inputSchema={
                "type": "object",
                "properties": {"event_id": {"type": "string"}},
                "required": ["event_id"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="finder_list",
            description="List direct children of an absolute macOS path.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "include_hidden": {"type": "boolean"},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="reminders_list_lists",
            description="List macOS Reminders lists and mark the configured default list when available.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="reminders_list_items",
            description="List Reminders items, optionally filtering by list, completion status, and free-text query.",
            inputSchema={
                "type": "object",
                "properties": {
                    "list_name": {"type": "string"},
                    "include_completed": {"type": "boolean"},
                    "query": {"type": "string"},
                },
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="reminders_create_item",
            description="Create a Reminder item in a specific list or in the configured default reminder list.",
            inputSchema={
                "type": "object",
                "properties": {
                    "list_name": {"type": "string"},
                    "title": {"type": "string"},
                    "due_iso": {"type": "string"},
                    "notes": {"type": "string"},
                },
                "required": ["title"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="reminders_complete_item",
            description="Mark a Reminder as completed using its exact reminder_id.",
            inputSchema={
                "type": "object",
                "properties": {"reminder_id": {"type": "string"}},
                "required": ["reminder_id"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="finder_get_info",
            description="Inspect metadata for an absolute macOS path.",
            inputSchema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
        ),
        types.Tool(
            name="finder_reveal",
            description="Reveal and select a file or folder in Finder using an absolute path.",
            inputSchema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
                "additionalProperties": False,
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> types.CallToolResult:
    """Dispatch a tool call to the corresponding macOS service."""

    services = build_services()
    try:
        match name:
            case "calendar_list_calendars":
                items = [item.to_dict() for item in services.calendar.list_calendars()]
                return _success(items)
            case "calendar_create_calendar":
                calendar = services.calendar.create_calendar(name=arguments["name"])
                return _success(calendar.to_dict())
            case "calendar_update_calendar":
                calendar = services.calendar.update_calendar(
                    calendar_id=arguments["calendar_id"],
                    new_name=arguments.get("new_name"),
                )
                return _success(calendar.to_dict())
            case "calendar_delete_calendar":
                return _success(services.calendar.delete_calendar(calendar_id=arguments["calendar_id"]))
            case "calendar_list_events":
                items = [
                    item.to_dict()
                    for item in services.calendar.list_events(
                        calendar_name=arguments.get("calendar_name"),
                        start_iso=arguments["start_iso"],
                        end_iso=arguments["end_iso"],
                        query=arguments.get("query"),
                    )
                ]
                return _success(items)
            case "calendar_create_event":
                event = services.calendar.create_event(
                    calendar_name=arguments.get("calendar_name"),
                    title=arguments["title"],
                    start_iso=arguments["start_iso"],
                    end_iso=arguments["end_iso"],
                    all_day=arguments.get("all_day", False),
                    location=arguments.get("location"),
                    notes=arguments.get("notes"),
                )
                return _success(event.to_dict())
            case "calendar_update_event":
                event = services.calendar.update_event(
                    event_id=arguments["event_id"],
                    title=arguments.get("title"),
                    start_iso=arguments.get("start_iso"),
                    end_iso=arguments.get("end_iso"),
                    all_day=arguments.get("all_day"),
                    location=arguments.get("location"),
                    notes=arguments.get("notes"),
                )
                return _success(event.to_dict())
            case "calendar_delete_event":
                return _success(services.calendar.delete_event(event_id=arguments["event_id"]))
            case "finder_list":
                items = [
                    item.to_dict()
                    for item in services.finder.list_items(
                        path=arguments["path"],
                        include_hidden=arguments.get("include_hidden", False),
                    )
                ]
                return _success(items)
            case "reminders_list_lists":
                items = [item.to_dict() for item in services.reminders.list_lists()]
                return _success(items)
            case "reminders_list_items":
                items = [
                    item.to_dict()
                    for item in services.reminders.list_items(
                        list_name=arguments.get("list_name"),
                        include_completed=arguments.get("include_completed", False),
                        query=arguments.get("query"),
                    )
                ]
                return _success(items)
            case "reminders_create_item":
                item = services.reminders.create_item(
                    list_name=arguments.get("list_name"),
                    title=arguments["title"],
                    due_iso=arguments.get("due_iso"),
                    notes=arguments.get("notes"),
                )
                return _success(item.to_dict())
            case "reminders_complete_item":
                item = services.reminders.complete_item(reminder_id=arguments["reminder_id"])
                return _success(item.to_dict())
            case "finder_get_info":
                info = services.finder.get_info(path=arguments["path"])
                return _success(info.to_dict())
            case "finder_reveal":
                return _success(services.finder.reveal(path=arguments["path"]))
            case _:
                raise McpMacError(f"Unknown tool: {name}")
    except Exception as exc:
        return _error(exc)


async def run() -> None:
    """Run the MCP server over stdio transport."""

    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name=SERVER_NAME,
                server_version=SERVER_VERSION,
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
                instructions=server.instructions,
            ),
        )


def main() -> None:
    """Synchronous entrypoint used by the console script."""

    asyncio.run(run())
