"""Helpers for executing JavaScript for Automation through `osascript`."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

from ..errors import AutomationPermissionError, McpMacError, NotFoundError, ValidationError


@dataclass(slots=True)
class AppleScriptRunner:
    """Execute JXA scripts and normalize their error handling."""

    executable: str = "osascript"

    def run_json(self, script: str) -> object:
        """Run a script and parse its stdout as JSON."""

        raw = self.run(script=script)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise McpMacError(f"AppleScript returned invalid JSON: {raw}") from exc

    def run(self, script: str) -> str:
        """Run a JXA script and return its raw stdout."""

        completed = subprocess.run(
            [self.executable, "-l", "JavaScript"],
            input=script,
            text=True,
            capture_output=True,
            check=False,
            env=None,
        )
        if completed.returncode != 0:
            raise map_osascript_error(completed.stderr or completed.stdout)
        return completed.stdout.strip()


def map_osascript_error(message: str) -> McpMacError:
    """Map common `osascript` failures onto domain-specific exceptions."""

    normalized = (message or "").strip()
    lowered = normalized.lower()

    if "not authorized" in lowered or "(-1743)" in lowered:
        return AutomationPermissionError(
            "macOS denied Automation access. Grant permission for the client app to control Calendar or Finder."
        )
    if "can't get" in lowered or "can’t get" in lowered or "doesn’t exist" in lowered or "doesn't exist" in lowered:
        return NotFoundError(normalized or "Requested item was not found.")
    if "expected" in lowered or "invalid" in lowered:
        return ValidationError(normalized or "AppleScript rejected the input.")
    return McpMacError(normalized or "AppleScript command failed.")


def jxa_program(body: str, payload: dict[str, object] | None = None) -> str:
    """Wrap a JXA snippet with project helpers and an embedded payload."""

    payload_json = json.dumps(payload or {}, ensure_ascii=False)
    return f"""
ObjC.import('Foundation');
const payload = {payload_json};

function isoString(date) {{
  return date ? date.toISOString() : null;
}}

function toJson(value) {{
  return JSON.stringify(value);
}}

function run() {{
{body}
}}
""".strip()
