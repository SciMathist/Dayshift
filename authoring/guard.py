"""PreToolUse hook that keeps a scenario agent inside its sandbox workspace.

The Claude CLI runs this script before every tool call and sends the call as JSON on
stdin. Exit code 2 blocks the call and returns stderr to the agent.

| Tool | Author | Reviewer |
|---|---|---|
| Read, Glob, Grep | Inside the workspace | Inside the workspace |
| Write, Edit | `scenario/*.yaml` or `scenario/*.md` | Blocked |
| Bash | Only `dsz verify scenario [--seeds N]` | Blocked |
| StructuredOutput | Allowed | Allowed (returns the verdict) |
| Any other tool | Blocked | Blocked |

Environment:
    DSZ_WORKSPACE: absolute path of the workspace.
    DSZ_ROLE: `author` or `reviewer`.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

BLOCK = 2
READ_TOOLS = {"Read", "Glob", "Grep"}
RESULT_TOOLS = {"StructuredOutput"}  # returns the --json-schema verdict; touches no file
WRITE_TOOLS = {"Write", "Edit", "MultiEdit"}
WRITABLE_SUFFIXES = {".yaml", ".yml", ".md"}
VERIFY = re.compile(r"dsz verify scenario/?( --seeds \d+)?")
VERIFY_HINT = "Run exactly: dsz verify scenario   (optionally: --seeds N)"


def inside(path: str, root: Path, cwd: Path) -> bool:
    """Return True if `path` (relative paths resolve against `cwd`) is `root` or below it."""
    target = Path(path)
    target = (target if target.is_absolute() else cwd / target).resolve()
    return Path(os.path.normcase(target)).is_relative_to(Path(os.path.normcase(root.resolve())))


def problem(tool: str, args: dict, role: str, workspace: Path, cwd: Path) -> str | None:
    """Return why the call is not allowed, or None if it is allowed."""
    if tool in RESULT_TOOLS:
        return None
    if tool in READ_TOOLS:
        paths = [args[k] for k in ("file_path", "path") if args.get(k)]
        pattern = args.get("pattern", "")
        if ".." in Path(pattern).parts:
            return f"Read only inside your working folder. Blocked pattern: {pattern}"
        if tool == "Glob" and Path(pattern).is_absolute():
            paths.append(pattern.split("*")[0])
        bad = [p for p in paths if not inside(p, workspace, cwd)]
        return f"Read only inside your working folder. Blocked: {bad[0]}" if bad else None
    if tool in WRITE_TOOLS and role == "author":
        path = args.get("file_path", "")
        if not inside(path, workspace / "scenario", cwd) or Path(path).suffix not in WRITABLE_SUFFIXES:
            return f"Write only scenario/scenario.yaml and scenario/DESIGN.md. Blocked: {path}"
        return None
    if tool == "Bash" and role == "author":
        command = args.get("command", "").strip()
        return None if VERIFY.fullmatch(command) else f"Only the verifier may run. {VERIFY_HINT}. Blocked: {command}"
    return f"The {role} may not use {tool}."


def main() -> int:
    """Read one hook event from stdin and return the hook exit code."""
    event = json.load(sys.stdin)
    workspace = Path(os.environ["DSZ_WORKSPACE"])
    cwd = Path(event.get("cwd") or workspace)
    reason = problem(event.get("tool_name", ""), event.get("tool_input", {}), os.environ["DSZ_ROLE"], workspace, cwd)
    if reason:
        print(reason, file=sys.stderr)
        return BLOCK
    return 0


if __name__ == "__main__":
    sys.exit(main())
