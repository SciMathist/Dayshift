"""Run the scenario author/reviewer loop headless through the Claude CLI.

One run:
  1. The author (one CLI session, resumed each round) writes a new scenario
     with ``day_shift_zero/scenarios/AGENTS.md`` as its instructions.
  2. This script runs the parse and compile check itself (stages S1, S2).
  3. If the check passes, a fresh read-only reviewer session gives a JSON
     verdict with ``REVIEWER.md`` as its instructions.
  4. The loop stops on a passed check plus a ``pass`` verdict, or after N rounds.
     Otherwise the check output and the verdict go back to the author.

A PreToolUse hook (``guard_writes.py``) keeps the author inside its own folder.
After each author turn the script also checks ``git status`` for stray changes.
Every call's JSON goes to ``runs/scenario_loop/<UTC time>/`` (git-ignored).

Usage, from the repository root:
    python spike/scenario_loop/loop.py --rounds 4 --brief "optional idea"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from guard_writes import write_problem

REPO = Path(__file__).resolve().parents[2]
DSZ = REPO / "day_shift_zero"
SCENARIOS = DSZ / "scenarios"
HOOK = Path(__file__).resolve().parent / "guard_writes.py"
RUNS = REPO / "runs" / "scenario_loop"

AUTHOR_TOOLS = ["Read", "Grep", "Glob", "Write", "Edit", "Bash"]
REVIEWER_TOOLS = ["Read", "Grep", "Glob"]
REVIEWER_DENIED = ["Write", "Edit", "NotebookEdit", "Bash"]

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["pass", "improve", "discard"]},
        "summary": {"type": "string"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "rule": {"type": "string"},
                    "severity": {"type": "string", "enum": ["blocker", "major", "minor"]},
                    "location": {"type": "string"},
                    "problem": {"type": "string"},
                    "fix": {"type": "string"},
                },
                "required": ["rule", "severity", "location", "problem", "fix"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["decision", "summary", "findings"],
    "additionalProperties": False,
}

COMPILE_SNIPPET = (
    "import sys; from dsz.scenario.spec import load_spec; "
    "from dsz.scenario.compiler import compile_spec; "
    "compile_spec(load_spec(sys.argv[1])); print('OK')"
)


@dataclass(frozen=True)
class LoopConfig:
    """Settings for one loop run."""

    claude_bin: str
    rounds: int
    author_model: str | None
    reviewer_model: str | None
    budget_usd: float | None
    timeout_s: int
    brief: str


@dataclass(frozen=True)
class VerifyResult:
    """Outcome of the parse and compile check on one scenario folder."""

    ok: bool
    output: str


@dataclass
class RunLog:
    """Writes each step's output to the run directory and keeps the summary."""

    directory: Path
    summary: dict = field(default_factory=dict)

    def write(self, name: str, content: dict | str) -> None:
        """Write one step's output as JSON or text."""
        path = self.directory / name
        text = content if isinstance(content, str) else json.dumps(content, indent=2)
        path.write_text(text)

    def flush(self) -> None:
        """Write the summary file."""
        self.write("summary.json", self.summary)


def find_claude_bin() -> str:
    """Return the Claude CLI path: $CLAUDE_BIN, PATH, or the newest VS Code bundle."""
    if os.environ.get("CLAUDE_BIN"):
        return os.environ["CLAUDE_BIN"]
    on_path = shutil.which("claude")
    if on_path:
        return on_path
    bundles = sorted(
        Path.home().glob(".vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude"),
        key=lambda p: tuple(map(int, re.search(r"(\d+)\.(\d+)\.(\d+)", p.parts[-4]).groups())),
    )
    if not bundles:
        sys.exit("Claude CLI not found. Set CLAUDE_BIN.")
    return str(bundles[-1])


def hook_settings() -> str:
    """Return the --settings JSON that installs the write guard hook."""
    command = f"{shlex.quote(sys.executable)} {shlex.quote(str(HOOK))}"
    return json.dumps({
        "hooks": {
            "PreToolUse": [{
                "matcher": "Write|Edit|MultiEdit|NotebookEdit|Bash",
                "hooks": [{"type": "command", "command": command}],
            }]
        }
    })


def hook_env(protected: list[Path]) -> dict[str, str]:
    """Return the environment that the write guard hook reads."""
    return {
        **os.environ,
        "DSZ_LOOP_SCENARIOS": str(SCENARIOS),
        "DSZ_LOOP_PROTECTED": os.pathsep.join(str(p) for p in protected),
    }


def run_claude(cfg: LoopConfig, prompt: str, args: list[str], env: dict[str, str]) -> dict:
    """Run one headless CLI call and return its parsed JSON result.

    Raises:
        RuntimeError: if the CLI exits non-zero or reports an error result.
    """
    cmd = [cfg.claude_bin, "-p", prompt, "--output-format", "json", *args]
    if cfg.budget_usd is not None:
        cmd += ["--max-budget-usd", str(cfg.budget_usd)]
    proc = subprocess.run(
        cmd, cwd=REPO, env=env, capture_output=True, text=True, timeout=cfg.timeout_s
    )
    if proc.returncode != 0 and not proc.stdout.strip():
        raise RuntimeError(f"claude exited {proc.returncode}: {proc.stderr.strip()[-2000:]}")
    result = json.loads(proc.stdout)
    if result.get("is_error"):
        raise RuntimeError(f"claude error ({result.get('subtype')}): {result.get('result')}")
    return result


def model_args(model: str | None) -> list[str]:
    """Return the --model arguments, or none to use the CLI default."""
    return ["--model", model] if model else []


def author_args(cfg: LoopConfig, session_id: str, first: bool) -> list[str]:
    """Return the CLI arguments for one author turn."""
    session = ["--session-id", session_id] if first else ["--resume", session_id]
    return [
        *session,
        *model_args(cfg.author_model),
        "--append-system-prompt-file", str(SCENARIOS / "AGENTS.md"),
        "--permission-mode", "acceptEdits",
        "--allowedTools", *AUTHOR_TOOLS,
        "--settings", hook_settings(),
    ]


def reviewer_args(cfg: LoopConfig) -> list[str]:
    """Return the CLI arguments for one read-only reviewer call."""
    return [
        *model_args(cfg.reviewer_model),
        "--append-system-prompt-file", str(SCENARIOS / "REVIEWER.md"),
        "--allowedTools", *REVIEWER_TOOLS,
        "--disallowedTools", *REVIEWER_DENIED,
        "--json-schema", json.dumps(VERDICT_SCHEMA),
    ]


def scenario_folders() -> set[Path]:
    """Return every scenario folder that exists now."""
    return {p for p in SCENARIOS.iterdir() if p.is_dir() and not p.name.startswith((".", "__"))}


def newest_new_folder(protected: list[Path]) -> Path | None:
    """Return the newest scenario folder with a scenario.yaml that is not protected."""
    candidates = [
        p for p in scenario_folders() - set(protected) if (p / "scenario.yaml").is_file()
    ]
    return max(candidates, key=lambda p: (p / "scenario.yaml").stat().st_mtime, default=None)


def compile_check(folder: Path | None) -> VerifyResult:
    """Run stages S1 and S2 (parse, compile) the way AGENTS.md section 4 does."""
    if folder is None:
        return VerifyResult(False, "No new scenario folder with a scenario.yaml exists.")
    spec = folder.relative_to(DSZ) / "scenario.yaml"
    proc = subprocess.run(
        [str(DSZ / ".venv" / "bin" / "python"), "-c", COMPILE_SNIPPET, str(spec)],
        cwd=DSZ, capture_output=True, text=True, timeout=600,
    )
    output = (proc.stdout + proc.stderr).strip()
    return VerifyResult(proc.returncode == 0 and output.endswith("OK"), output[-6000:])


def git_changes() -> dict[str, str]:
    """Return each changed or untracked path with a hash of its content."""
    proc = subprocess.run(
        ["git", "status", "--porcelain", "-uall", "-z"],
        cwd=REPO, capture_output=True, text=True, check=True,
    )
    changes = {}
    for entry in filter(None, proc.stdout.split("\0")):
        path = entry[3:]
        full = REPO / path
        changes[path] = hashlib.sha256(full.read_bytes()).hexdigest() if full.is_file() else "gone"
    return changes


def stray_changes(baseline: dict[str, str], protected: list[Path]) -> list[str]:
    """Return paths that changed since the baseline outside the allowed folders."""
    stray = []
    for path, digest in git_changes().items():
        if baseline.get(path) == digest:
            continue
        if write_problem(str(REPO / path), SCENARIOS, protected) is not None:
            stray.append(path)
    return stray


def first_prompt(brief: str) -> str:
    """Return the author's first prompt."""
    idea = f"\n\nIdea from the person who runs this loop: {brief}" if brief else ""
    return (
        "Write one new Day Shift Zero scenario. Follow AGENTS.md exactly, "
        f"including the verify step and the report in section 7.{idea}"
    )


def review_prompt(folder: Path, report: str, verify: VerifyResult) -> str:
    """Return the reviewer's prompt for one round."""
    return (
        f"Review the scenario in {folder.relative_to(REPO)}/.\n\n"
        f"## Verify output (S1, S2): {'PASSED' if verify.ok else 'FAILED'}\n```\n{verify.output}\n```\n\n"
        f"## Author's report\n{report}\n\n"
        "Follow REVIEWER.md and give your verdict."
    )


def feedback_prompt(verify: VerifyResult, verdict: dict | None, stray: list[str]) -> str:
    """Return the author's prompt for the next round."""
    parts = [f"## Verify output (S1, S2): {'PASSED' if verify.ok else 'FAILED'}\n```\n{verify.output}\n```"]
    if stray:
        parts.append("## Changes outside your folder (not allowed, revert them)\n" + "\n".join(stray))
    if verdict is not None:
        parts.append("## Reviewer verdict\n```json\n" + json.dumps(verdict, indent=2) + "\n```")
    parts.append(
        "Follow AGENTS.md section 6: decide to improve or discard, act on it, "
        "verify again, and give the report in section 7 with your decision and reason."
    )
    return "\n\n".join(parts)


def cli_version(claude_bin: str) -> str:
    """Return the CLI version string."""
    return subprocess.run([claude_bin, "--version"], capture_output=True, text=True).stdout.strip()


def git_head() -> str:
    """Return the current commit hash."""
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True
    ).stdout.strip()


def new_run_log(cfg: LoopConfig, session_id: str) -> RunLog:
    """Create the run directory and start the summary with the run metadata."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    directory = RUNS / stamp
    directory.mkdir(parents=True)
    log = RunLog(directory)
    log.summary = {
        "git_head": git_head(),
        "claude_cli": cli_version(cfg.claude_bin),
        "config": asdict(cfg),
        "author_session_id": session_id,
        "rounds": [],
        "total_cost_usd": 0.0,
        "status": "running",
    }
    log.flush()
    return log


def record(log: RunLog, name: str, result: dict) -> None:
    """Write one CLI result and add its cost to the summary."""
    log.write(name, result)
    log.summary["total_cost_usd"] += result.get("total_cost_usd") or 0.0


def run_loop(cfg: LoopConfig) -> RunLog:
    """Run the author/verify/review loop and return the finished run log."""
    protected = sorted(scenario_folders())
    env = hook_env(protected)
    baseline = git_changes()
    session_id = str(uuid.uuid4())
    log = new_run_log(cfg, session_id)
    prompt = first_prompt(cfg.brief)

    for n in range(1, cfg.rounds + 1):
        print(f"[round {n}] author working ...", flush=True)
        author = run_claude(cfg, prompt, author_args(cfg, session_id, first=n == 1), env)
        record(log, f"round{n}_author.json", author)

        folder = newest_new_folder(protected)
        verify = compile_check(folder)
        stray = stray_changes(baseline, protected)
        log.write(f"round{n}_verify.txt", verify.output)
        entry = {
            "round": n,
            "folder": str(folder.relative_to(REPO)) if folder else None,
            "verify_ok": verify.ok,
            "stray_changes": stray,
            "permission_denials": author.get("permission_denials", []),
            "decision": None,
        }
        log.summary["rounds"].append(entry)
        print(f"[round {n}] folder={entry['folder']} verify={'ok' if verify.ok else 'FAILED'}"
              f" stray={len(stray)}", flush=True)

        verdict = None
        if verify.ok and not stray:
            print(f"[round {n}] reviewer working ...", flush=True)
            review = run_claude(cfg, review_prompt(folder, author.get("result", ""), verify),
                                reviewer_args(cfg), env)
            record(log, f"round{n}_review.json", review)
            verdict = review.get("structured_output")
            entry["decision"] = verdict["decision"] if verdict else "no_structured_output"
            print(f"[round {n}] verdict={entry['decision']}", flush=True)
            if verdict and verdict["decision"] == "pass":
                log.summary["status"] = "passed"
                log.flush()
                return log
        log.flush()
        prompt = feedback_prompt(verify, verdict, stray)

    log.summary["status"] = "rounds_exhausted"
    log.flush()
    return log


def parse_args() -> LoopConfig:
    """Parse the command line into a loop config."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rounds", type=int, default=4, help="maximum author turns")
    parser.add_argument("--author-model", default=None, help="CLI --model for the author")
    parser.add_argument("--reviewer-model", default=None, help="CLI --model for the reviewer")
    parser.add_argument("--budget-usd", type=float, default=None, help="--max-budget-usd per call")
    parser.add_argument("--timeout", type=int, default=3600, help="seconds per CLI call")
    parser.add_argument("--brief", default="", help="optional scenario idea for the author")
    args = parser.parse_args()
    return LoopConfig(
        claude_bin=find_claude_bin(),
        rounds=args.rounds,
        author_model=args.author_model,
        reviewer_model=args.reviewer_model,
        budget_usd=args.budget_usd,
        timeout_s=args.timeout,
        brief=args.brief,
    )


def main() -> None:
    """Run the loop and print where the run log is."""
    log = run_loop(parse_args())
    summary = log.summary
    print(f"status={summary['status']} cost=${summary['total_cost_usd']:.2f} log={log.directory}")


if __name__ == "__main__":
    main()
