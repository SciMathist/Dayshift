"""Tests for the sandbox guard hook. Run: `python -m pytest authoring` from the repository root."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from guard import problem

GUARD = Path(__file__).resolve().parent / "guard.py"


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    """Return a workspace with a scenario folder."""
    (tmp_path / "scenario").mkdir()
    return tmp_path


def _check(ws: Path, tool: str, role: str = "author", **args) -> str | None:
    """Return the guard's objection to one call made from the workspace."""
    return problem(tool, args, role, ws, ws)


def test_reads_stay_in_the_workspace(ws):
    """Reads inside the workspace pass; reads outside it or via '..' are blocked."""
    assert _check(ws, "Read", file_path="SPEC.md") is None
    assert _check(ws, "Grep", pattern="CR3") is None
    assert _check(ws, "Glob", pattern="**/*.md") is None
    assert _check(ws, "Read", file_path=str(ws.parent / "secret.txt"))
    assert _check(ws, "Read", file_path="../secret.txt")
    assert _check(ws, "Grep", pattern="x", path=str(ws.parent))
    assert _check(ws, "Glob", pattern="../**/*.py")
    assert _check(ws, "Glob", pattern=str(ws.parent / "*.py"))


def test_author_writes_only_yaml_and_markdown_in_scenario(ws):
    """The author may write scenario/*.yaml and scenario/*.md only."""
    assert _check(ws, "Write", file_path="scenario/scenario.yaml") is None
    assert _check(ws, "Edit", file_path=str(ws / "scenario" / "DESIGN.md")) is None
    assert _check(ws, "Write", file_path="scenario/oracle.py")
    assert _check(ws, "Write", file_path="SPEC.md")
    assert _check(ws, "Write", file_path="../scenario.yaml")


def test_author_shell_is_only_the_verifier(ws):
    """Only `dsz verify scenario [--seeds N]` may run."""
    assert _check(ws, "Bash", command="dsz verify scenario") is None
    assert _check(ws, "Bash", command="dsz verify scenario/ --seeds 3") is None
    for command in ("dsz vocab", "cat ../x", "dsz verify scenario && cat /etc/passwd", "dsz verify ..", "ls"):
        assert _check(ws, "Bash", command=command), command


def test_reviewer_is_read_only(ws):
    """The reviewer can read but not write or run commands."""
    assert _check(ws, "Read", role="reviewer", file_path="scenario/DESIGN.md") is None
    assert _check(ws, "Write", role="reviewer", file_path="scenario/DESIGN.md")
    assert _check(ws, "Bash", role="reviewer", command="dsz verify scenario")


def test_reviewer_can_return_its_verdict(ws):
    """StructuredOutput carries the --json-schema verdict, so the guard lets it through."""
    assert _check(ws, "StructuredOutput", role="reviewer", decision="pass", summary="", findings=[]) is None


def test_unknown_tools_are_blocked(ws):
    """Any tool the guard does not know is blocked."""
    assert _check(ws, "WebFetch", url="https://example.com")
    assert _check(ws, "Agent", prompt="read the repo")


def test_hook_exit_codes(ws):
    """The script exits 2 with a reason on stderr to block, and 0 to allow."""
    env = {**os.environ, "DSZ_WORKSPACE": str(ws), "DSZ_ROLE": "author"}

    def run(tool: str, args: dict) -> subprocess.CompletedProcess:
        """Send one hook event to the guard script."""
        event = json.dumps({"tool_name": tool, "tool_input": args, "cwd": str(ws)})
        return subprocess.run([sys.executable, str(GUARD)], input=event, env=env, capture_output=True, text=True)

    assert run("Read", {"file_path": "SPEC.md"}).returncode == 0
    blocked = run("Bash", {"command": "ls"})
    assert blocked.returncode == 2 and "dsz verify scenario" in blocked.stderr
