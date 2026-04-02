"""Filesystem-backed Finder utilities plus reveal support through JXA."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..errors import NotFoundError
from ..models import FinderInfo, FinderItem, finder_info_from_path
from ..utils import require_absolute_path
from .applescript import AppleScriptRunner, jxa_program


@dataclass(slots=True)
class FinderService:
    """Finder-related operations exposed through MCP tools."""

    runner: AppleScriptRunner

    def list_items(self, *, path: str, include_hidden: bool = False) -> list[FinderItem]:
        """List direct children for a directory path."""

        target = require_absolute_path(path)
        if not target.exists():
            raise NotFoundError(f"Path not found: {target}")
        if not target.is_dir():
            raise NotFoundError(f"Path is not a directory: {target}")

        items: list[FinderItem] = []
        for child in sorted(target.iterdir(), key=lambda item: item.name.lower()):
            hidden = child.name.startswith(".")
            if hidden and not include_hidden:
                continue
            is_dir = child.is_dir()
            is_app = child.suffix.lower() == ".app" and is_dir
            items.append(
                FinderItem(
                    name=child.name,
                    path=str(child),
                    kind="application" if is_app else ("folder" if is_dir else "file"),
                    is_directory=is_dir,
                    is_package=is_app,
                    is_hidden=hidden,
                )
            )
        return items

    def get_info(self, *, path: str) -> FinderInfo:
        """Return normalized metadata for a filesystem path."""

        target = require_absolute_path(path)
        if not target.exists():
            return FinderInfo(
                path=str(target),
                exists=False,
                name=target.name,
                kind="missing",
                is_directory=False,
                is_package=False,
                is_alias=False,
                is_application=False,
                extension=target.suffix[1:] if target.suffix else None,
                size_bytes=None,
                created_iso=None,
                modified_iso=None,
            )
        return finder_info_from_path(target)

    def reveal(self, *, path: str) -> dict[str, object]:
        """Reveal a path in Finder and select it."""

        target = require_absolute_path(path)
        if not target.exists():
            raise NotFoundError(f"Path not found: {target}")

        payload = {"path": str(target)}
        script = jxa_program(
            """
  const finder = Application('Finder');
  finder.activate();
  const item = Path(payload.path);
  finder.select(item);
  return toJson({revealed: true, path: payload.path});
""",
            payload,
        )
        return self.runner.run_json(script)
