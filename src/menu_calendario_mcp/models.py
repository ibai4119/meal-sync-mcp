"""Typed response models shared across macOS services and the MCP server."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


@dataclass(slots=True)
class CalendarInfo:
    """Metadata describing an available Calendar calendar."""

    name: str
    color: str | None = None
    is_default: bool = False

    def to_dict(self) -> dict[str, object]:
        """Serialize the model to a plain dictionary for MCP responses."""

        return asdict(self)


@dataclass(slots=True)
class CalendarEvent:
    """Normalized representation of a Calendar event."""

    event_id: str
    calendar_name: str
    title: str
    start_iso: str
    end_iso: str
    all_day: bool
    location: str | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize the model to a plain dictionary for MCP responses."""

        return asdict(self)


@dataclass(slots=True)
class FinderItem:
    """Directory entry returned by Finder-style listing operations."""

    name: str
    path: str
    kind: str
    is_directory: bool
    is_package: bool
    is_hidden: bool

    def to_dict(self) -> dict[str, object]:
        """Serialize the model to a plain dictionary for MCP responses."""

        return asdict(self)


@dataclass(slots=True)
class FinderInfo:
    """Detailed metadata for a single filesystem path."""

    path: str
    exists: bool
    name: str
    kind: str
    is_directory: bool
    is_package: bool
    is_alias: bool
    is_application: bool
    extension: str | None
    size_bytes: int | None
    created_iso: str | None
    modified_iso: str | None

    def to_dict(self) -> dict[str, object]:
        """Serialize the model to a plain dictionary for MCP responses."""

        return asdict(self)


@dataclass(slots=True)
class ReminderListInfo:
    """Metadata describing an available Reminders list."""

    name: str
    is_default: bool = False

    def to_dict(self) -> dict[str, object]:
        """Serialize the model to a plain dictionary for MCP responses."""

        return asdict(self)


@dataclass(slots=True)
class ReminderItem:
    """Normalized representation of a reminder item."""

    reminder_id: str
    list_name: str
    title: str
    is_completed: bool
    due_iso: str | None = None
    notes: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize the model to a plain dictionary for MCP responses."""

        return asdict(self)


def finder_info_from_path(path: Path) -> FinderInfo:
    """Build a `FinderInfo` instance from an existing filesystem path."""

    stat = path.stat()
    is_dir = path.is_dir()
    is_app = path.suffix.lower() == ".app" and is_dir
    is_package = is_app
    ext = path.suffix[1:] if path.suffix else None
    return FinderInfo(
        path=str(path),
        exists=True,
        name=path.name,
        kind="folder" if is_dir else "file",
        is_directory=is_dir,
        is_package=is_package,
        is_alias=path.is_symlink(),
        is_application=is_app,
        extension=ext,
        size_bytes=None if is_dir else stat.st_size,
        created_iso=datetime.fromtimestamp(stat.st_ctime).astimezone().isoformat(),
        modified_iso=datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(),
    )
