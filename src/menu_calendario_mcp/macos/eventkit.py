"""EventKit helpers for calendar source inspection and targeted calendar creation."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

from ..errors import McpMacError, ValidationError
from ..models import CalendarSourceInfo

try:
    from EventKit import EKCalendar, EKEntityTypeEvent, EKEventStore
except ImportError as exc:  # pragma: no cover - exercised only when dependency is missing
    EKCalendar = None  # type: ignore[assignment]
    EKEntityTypeEvent = None  # type: ignore[assignment]
    EKEventStore = None  # type: ignore[assignment]
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


SOURCE_TYPE_NAMES = {
    0: "local",
    1: "exchange",
    2: "caldav",
    3: "mobileme",
    4: "subscribed",
    5: "birthdays",
}


def _require_eventkit() -> None:
    """Raise a helpful error when EventKit bindings are unavailable."""

    if _IMPORT_ERROR is not None:
        raise McpMacError(
            "EventKit bindings are not installed. Add pyobjc EventKit support to use calendar sources."
        ) from _IMPORT_ERROR


@dataclass(slots=True)
class EventKitCalendarManager:
    """Thin wrapper around EventKit for source-aware calendar operations."""

    _store: Any = field(init=False, repr=False)
    _access_checked: bool = field(init=False, default=False, repr=False)

    def __post_init__(self) -> None:
        _require_eventkit()
        self._store = EKEventStore.alloc().init()

    def _ensure_access(self) -> None:
        """Request full Calendar access when needed before source-aware operations."""

        if self._access_checked:
            return

        done = threading.Event()
        result: dict[str, object] = {"granted": False, "error": None}

        def handler(granted: bool, error: object) -> None:
            result["granted"] = bool(granted)
            result["error"] = None if error is None else str(error)
            done.set()

        if self._store.respondsToSelector_("requestFullAccessToEventsWithCompletion:"):
            self._store.requestFullAccessToEventsWithCompletion_(handler)
        else:  # pragma: no cover - fallback for older macOS/EventKit runtimes
            self._store.requestAccessToEntityType_completion_(EKEntityTypeEvent, handler)

        if not done.wait(10):  # pragma: no cover - timeout is environment-specific
            raise McpMacError("Timed out while requesting Calendar access from EventKit.")

        self._access_checked = True
        if not result["granted"]:
            detail = f" EventKit detail: {result['error']}" if result["error"] else ""
            raise McpMacError(
                "Calendar full access is required to inspect sources or create calendars in a specific account. "
                "Grant access to the app running this server in System Settings > Privacy & Security > Calendars."
                f"{detail}"
            )

    def list_sources(self) -> list[CalendarSourceInfo]:
        """List visible calendar sources and whether they claim to allow calendar creation."""

        self._ensure_access()
        sources = []
        for source in list(self._store.sources()):
            source_id = source.sourceIdentifier()
            title = source.title()
            if not source_id or not title:
                continue
            allows_creation = bool(getattr(source, "allowsCalendarAddDeleteModify", lambda: False)())
            source_type = SOURCE_TYPE_NAMES.get(int(source.sourceType()), f"unknown:{int(source.sourceType())}")
            sources.append(
                CalendarSourceInfo(
                    source_id=str(source_id),
                    title=str(title),
                    source_type=source_type,
                    allows_calendar_creation=allows_creation,
                )
            )
        return sources

    def create_calendar(self, *, name: str, source_id: str) -> None:
        """Create a new calendar in the specified source, or raise a clear error."""

        self._ensure_access()
        source = next((item for item in list(self._store.sources()) if item.sourceIdentifier() == source_id), None)
        if source is None:
            raise ValidationError(f"Unknown calendar source: {source_id}")

        calendar = EKCalendar.calendarForEntityType_eventStore_(EKEntityTypeEvent, self._store)
        calendar.setTitle_(name)
        calendar.setSource_(source)
        ok, error = self._store.saveCalendar_commit_error_(calendar, True, None)
        if not ok:
            description = str(error) if error is not None else "Calendar source rejected the new calendar."
            raise McpMacError(description)
