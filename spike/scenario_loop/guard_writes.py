"""PreToolUse hook that keeps a headless scenario author inside its own folder.

The Claude CLI runs this script before each matched tool call and sends the call
as JSON on stdin. Exit code 2 blocks the call and returns stderr to the agent.

Environment:
    DSZ_LOOP_SCENARIOS: absolute path of ``day_shift_zero/scenarios``.
    DSZ_LOOP_PROTECTED: ``os.pathsep``-separated scenario folders that existed
        before the run. The author must not change them.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

BLOCK = 2
GIT_MUTATION = re.compile(
    r"\bgit\s+(commit|push|reset|checkout|switch|rebase|merge|stash|clean|add|rm|restore|tag)\b"
)


def write_target(tool_input: dict) -> str | None:
    """Return the file path that a file-writing tool call targets, if any."""
    return tool_input.get("file_path") or tool_input.get("notebook_path")


def write_problem(target: str, scenarios: Path, protected: list[Path]) -> str | None:
    """Return why a write to ``target`` is not allowed, or None if it is allowed."""
    path = Path(target).resolve()
    if not path.is_relative_to(scenarios) or path.parent == scenarios:
        return f"Write only inside your own folder day_shift_zero/scenarios/<id>/. Blocked: {path}"
    for folder in protected:
        if path.is_relative_to(folder):
            return f"Do not change an existing scenario ({folder.name}). Blocked: {path}"
    return None


def bash_problem(command: str) -> str | None:
    """Return why a shell command is not allowed, or None if it is allowed."""
    if GIT_MUTATION.search(command):
        return "Do not change git state. A person reviews and commits your folder."
    return None


def main() -> int:
    """Read one hook event from stdin and return the hook exit code."""
    event = json.load(sys.stdin)
    scenarios = Path(os.environ["DSZ_LOOP_SCENARIOS"]).resolve()
    protected = [
        Path(p).resolve() for p in os.environ.get("DSZ_LOOP_PROTECTED", "").split(os.pathsep) if p
    ]
    tool_input = event.get("tool_input", {})
    if event.get("tool_name") == "Bash":
        problem = bash_problem(tool_input.get("command", ""))
    else:
        target = write_target(tool_input)
        problem = write_problem(target, scenarios, protected) if target else None
    if problem:
        print(problem, file=sys.stderr)
        return BLOCK
    return 0


if __name__ == "__main__":
    sys.exit(main())
