import json
from pathlib import Path

import pytest

from menu_calendario_mcp.errors import NotFoundError
from menu_calendario_mcp.macos.applescript import AppleScriptRunner
from menu_calendario_mcp.macos.finder import FinderService


class StubRunner(AppleScriptRunner):
    def __init__(self) -> None:
        self.calls: list[str] = []

    def run_json(self, script: str) -> object:
        self.calls.append(script)
        payload = _embedded_payload(script)
        return {"revealed": True, "path": payload["path"]}


def test_finder_list_returns_basic_metadata(tmp_path: Path) -> None:
    folder = tmp_path / "folder"
    folder.mkdir()
    file_path = tmp_path / "file.txt"
    file_path.write_text("hello")
    hidden = tmp_path / ".hidden"
    hidden.write_text("secret")

    service = FinderService(runner=StubRunner())
    items = service.list_items(path=str(tmp_path))

    names = [item.name for item in items]
    assert names == ["file.txt", "folder"]


def test_finder_get_info_missing_path(tmp_path: Path) -> None:
    service = FinderService(runner=StubRunner())
    info = service.get_info(path=str(tmp_path / "missing.txt"))
    assert info.exists is False
    assert info.kind == "missing"


def test_finder_reveal_requires_existing_path(tmp_path: Path) -> None:
    service = FinderService(runner=StubRunner())
    with pytest.raises(NotFoundError):
        service.reveal(path=str(tmp_path / "missing.txt"))


def test_finder_reveal_calls_runner(tmp_path: Path) -> None:
    target = tmp_path / "file.txt"
    target.write_text("hello")
    runner = StubRunner()
    service = FinderService(runner=runner)

    result = service.reveal(path=str(target))

    assert result["revealed"] is True
    assert str(target) in runner.calls[0]


def _embedded_payload(script: str) -> dict[str, object]:
    marker = "const payload = "
    start = script.index(marker) + len(marker)
    end = script.index(";\n\nfunction isoString", start)
    return json.loads(script[start:end])
