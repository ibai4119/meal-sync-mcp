"""Environment-backed configuration for the MCP server."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(slots=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    default_calendar_name: str | None = None
    default_reminder_list: str | None = None


def load_settings() -> Settings:
    """Load server settings from the current process environment."""

    return Settings(
        default_calendar_name=os.getenv("MENU_CALENDARIO_DEFAULT_CALENDAR") or None,
        default_reminder_list=os.getenv("MENU_CALENDARIO_DEFAULT_REMINDER_LIST") or None,
    )
