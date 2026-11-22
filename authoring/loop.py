"""Run the scenario author/reviewer loop headless, with each agent in a sandbox.

One run:
  1. Build a workspace outside the repository: SPEC.md, FORMAT.md, VOCABULARY.md and an
     empty scenario/ folder. The agents see nothing else.
  2. The author (one CLI session, resumed each round) writes scenario/.
  3. This script runs `dsz verify` itself.
  4. If verify passes, a fresh read-only reviewer gives a JSON verdict.
  5. Stop on a passed verify plus a `pass` verdict, or after N rounds. Otherwise send the
     verify output and the verdict back to the author.
  6. On a pass, copy scenario/ to day_shift_zero/scenarios/<id>/ for human review.

Every call's output goes to runs/scenario_loop/<UTC time>/ (git-ignored).

Usage, from the repository root:
    python authoring/loop.py --rounds 3 --brief "optional idea"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DSZ = REPO / "day_shift_zero"
SCENARIOS = DSZ / "scenarios"
RUNS = REPO / "runs" / "scenario_loop"
VENV_BIN = DSZ / ".venv" / ("Scripts" if os.name == "nt" else "bin")
RESERVED_IDS = {"cloud_kitchen", "wedding_cake"}
COPIED = {"SPEC.md": REPO / "LONG_HORIZON_TASK_SPEC.md", "FORMAT.md": DSZ / "src" / "dsz" / "scenario" / "FORMAT.md"}

AUTHOR_TOOLS = ["Read", "Glob", "Grep", "Write", "Edit", "Bash"]
AUTHOR_ALLOWED = ["Read", "Glob", "Grep", "Write", "Edit", "Bash(dsz verify:*)"]
REVIEWER_TOOLS = ["Read", "Glob", "Grep"]

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


@dataclass(frozen=True)
class LoopConfig:
    """Settings for one loop run."""

    claude_bin: str
    rounds: int
    author_model: str | None
    reviewer_model: str | None
    budget_usd: float | None
    timeout_s: int
    seeds: int
    brief: str


@dataclass(frozen=True)
class VerifyResult:
    """The outcome of `dsz verify` on the workspace's scenario folder."""

    ok: bool
    output: str
    scenario_id: str | None


@dataclass
class RunLog:
    """Write each step's output to the run directory and keep the summary."""

    directory: Path
    summary: dict = field(default_factory=dict)

    def write(self, name: str, content: dict | str) -> None:
        """Write one step's output as JSON or text."""
        text = content if isinstance(content, str) else json.dumps(content, indent=2)
        (self.directory / name).write_text(text, encoding="utf-8")

    def flush(self) -> None:
        """Write the summary file."""
        self.write("summary.json", self.summary)


# ---- sandbox -------------------------------------------------------------------------------

def build_workspace() -> Path:
    """Create the workspace outside the repository and return its path."""
    workspace = Path(tempfile.mkdtemp(prefix="dsz-scenario-"))
    for name, source in COPIED.items():
        shutil.copyfile(source, workspace / name)
    vocab = subprocess.run([str(VENV_BIN / "dsz"), "vocab"], capture_output=True, text=True, check=True,
                           encoding="utf-8")
    (workspace / "VOCABULARY.md").write_text(vocab.stdout, encoding="utf-8")
    (workspace / "scenario").mkdir()
    return workspace


def agent_env(workspace: Path, role: str) -> dict[str, str]:
    """Return the agent's environment: the venv on PATH, and what the guard hook reads."""
    return {**os.environ, "PATH": f"{VENV_BIN}{os.pathsep}{os.environ['PATH']}",
            "DSZ_WORKSPACE": str(workspace), "DSZ_ROLE": role}


def guard_settings() -> str:
    """Return the --settings JSON that installs the guard hook for every tool."""
    command = f'"{Path(sys.executable).as_posix()}" "{(HERE / "guard.py").as_posix()}"'
    return json.dumps({"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": command}]}]}})


def sandbox_args(role: str, tools: list[str], allowed: list[str]) -> list[str]:
    """Return the CLI arguments that confine one agent to the workspace."""
    return ["--restricted", "--strict-mcp-config", "--settings", guard_settings(),
            "--append-system-prompt-file", str(HERE / f"{role}.md"),
            "--tools", ",".join(tools), "--allowedTools", *allowed]


# ---- agents --------------------------------------------------------------------------------

def find_claude_bin() -> str:
    """Return the Claude CLI path: $CLAUDE_BIN, PATH, or the newest VS Code bundle."""
    if os.environ.get("CLAUDE_BIN"):
        return os.environ["CLAUDE_BIN"]
    on_path = shutil.which("claude")
    if on_path:
        return on_path
    bundles = sorted(
        (p for p in Path.home().glob(".vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude*")
         if p.stem == "claude"),
        key=lambda p: tuple(map(int, re.search(r"(\d+)\.(\d+)\.(\d+)", p.parts[-4]).groups())),
    )
    if not bundles:
        sys.exit("Claude CLI not found. Set CLAUDE_BIN.")
    return str(bundles[-1])


def run_claude(cfg: LoopConfig, prompt: str, args: list[str], workspace: Path, role: str) -> dict:
    """Run one headless CLI call in the workspace and return its parsed JSON result.

    Raises:
        RuntimeError: if the CLI exits non-zero or reports an error result.
    """
    cmd = [cfg.claude_bin, "-p", prompt, "--output-format", "json", *args]
    if cfg.budget_usd is not None:
        cmd += ["--max-budget-usd", str(cfg.budget_usd)]
    proc = subprocess.run(cmd, cwd=workspace, env=agent_env(workspace, role), capture_output=True, text=True,
                          encoding="utf-8", timeout=cfg.timeout_s)
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
    return [*session, *model_args(cfg.author_model), "--permission-mode", "acceptEdits",
            *sandbox_args("author", AUTHOR_TOOLS, AUTHOR_ALLOWED)]


def reviewer_args(cfg: LoopConfig) -> list[str]:
    """Return the CLI arguments for one read-only reviewer call."""
    return [*model_args(cfg.reviewer_model), "--json-schema", json.dumps(VERDICT_SCHEMA),
            *sandbox_args("reviewer", REVIEWER_TOOLS, REVIEWER_TOOLS)]


# ---- checks --------------------------------------------------------------------------------

def taken_ids() -> set[str]:
    """Return the scenario IDs that a new scenario must not use."""
    return RESERVED_IDS | {p.name for p in SCENARIOS.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))}


def run_verify(cfg: LoopConfig, workspace: Path, report_path: Path) -> VerifyResult:
    """Run `dsz verify` on the workspace's scenario folder and add the ID-taken check."""
    proc = subprocess.run([str(VENV_BIN / "dsz"), "verify", "scenario", "--seeds", str(cfg.seeds),
                           "--json", str(report_path)],
                          cwd=workspace, capture_output=True, text=True, encoding="utf-8", timeout=cfg.timeout_s)
    output = (proc.stdout + proc.stderr).strip()[-6000:]
    report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
    sid = report.get("scenario_id")
    if sid in taken_ids():
        return VerifyResult(False, f"{output}\nID: '{sid}' is taken. Choose another id.", sid)
    return VerifyResult(proc.returncode == 0, output, sid)


# ---- prompts -------------------------------------------------------------------------------

def first_prompt(brief: str) -> str:
    """Return the author's first prompt."""
    idea = f"\n\nIdea from the person who runs this loop: {brief}" if brief else ""
    return (f"Write one new Day Shift Zero scenario in scenario/. These IDs are taken: "
            f"{', '.join(sorted(taken_ids()))}.{idea}")


def review_prompt(report: str, verify: VerifyResult) -> str:
    """Return the reviewer's prompt for one round."""
    return (f"Review the scenario in scenario/.\n\n## dsz verify: {'PASS' if verify.ok else 'FAIL'}\n"
            f"```\n{verify.output}\n```\n\n## Author's report\n{report}")


def feedback_prompt(verify: VerifyResult, verdict: dict | None) -> str:
    """Return the author's prompt for the next round."""
    parts = [f"## dsz verify: {'PASS' if verify.ok else 'FAIL'}\n```\n{verify.output}\n```"]
    if verdict is not None:
        parts.append("## Reviewer verdict\n```json\n" + json.dumps(verdict, indent=2) + "\n```")
    parts.append("Decide to improve or discard, act on it, run dsz verify, and report.")
    return "\n\n".join(parts)


# ---- loop ----------------------------------------------------------------------------------

def new_run_log(cfg: LoopConfig, session_id: str, workspace: Path) -> RunLog:
    """Create the run directory and start the summary with the run metadata."""
    directory = RUNS / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    directory.mkdir(parents=True)
    log = RunLog(directory)
    version = subprocess.run([cfg.claude_bin, "--version"], capture_output=True, text=True).stdout.strip()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    log.summary = {"git_head": head, "claude_cli": version, "config": asdict(cfg), "workspace": str(workspace),
                   "author_session_id": session_id, "rounds": [], "total_cost_usd": 0.0, "status": "running"}
    log.flush()
    return log


def record(log: RunLog, name: str, result: dict) -> None:
    """Write one CLI result and add its cost to the summary."""
    log.write(name, result)
    log.summary["total_cost_usd"] += result.get("total_cost_usd") or 0.0


def install(workspace: Path, sid: str) -> Path:
    """Copy the passed scenario into the repository for human review and return its folder."""
    target = SCENARIOS / sid
    shutil.copytree(workspace / "scenario", target)
    return target


def run_loop(cfg: LoopConfig) -> RunLog:
    """Run the author/verify/review loop and return the finished run log."""
    workspace = build_workspace()
    session_id = str(uuid.uuid4())
    log = new_run_log(cfg, session_id, workspace)
    prompt = first_prompt(cfg.brief)
    log.summary["status"] = "rounds_exhausted"
    try:
        for n in range(1, cfg.rounds + 1):
            print(f"[round {n}] author working ...", flush=True)
            author = run_claude(cfg, prompt, author_args(cfg, session_id, first=n == 1), workspace, "author")
            record(log, f"round{n}_author.json", author)
            shutil.copytree(workspace / "scenario", log.directory / f"round{n}_scenario")
            verify = run_verify(cfg, workspace, log.directory / f"round{n}_verify.json")
            log.write(f"round{n}_verify.txt", verify.output)
            entry = {"round": n, "scenario_id": verify.scenario_id, "verify_ok": verify.ok,
                     "permission_denials": author.get("permission_denials", []), "decision": None}
            log.summary["rounds"].append(entry)
            print(f"[round {n}] id={entry['scenario_id']} verify={'ok' if verify.ok else 'FAILED'}", flush=True)

            verdict = None
            if verify.ok:
                print(f"[round {n}] reviewer working ...", flush=True)
                review = run_claude(cfg, review_prompt(author.get("result", ""), verify), reviewer_args(cfg),
                                    workspace, "reviewer")
                record(log, f"round{n}_review.json", review)
                verdict = review.get("structured_output")
                entry["decision"] = verdict["decision"] if verdict else "no_structured_output"
                print(f"[round {n}] verdict={entry['decision']}", flush=True)
                if verdict and verdict["decision"] == "pass":
                    log.summary["status"] = "passed"
                    log.summary["installed_at"] = str(install(workspace, entry["scenario_id"]).relative_to(REPO))
                    break
            log.flush()
            prompt = feedback_prompt(verify, verdict)
    finally:
        log.flush()
        shutil.rmtree(workspace, ignore_errors=True)
    return log


def parse_args() -> LoopConfig:
    """Parse the command line into a loop config."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rounds", type=int, default=3, help="maximum author turns (default 3)")
    parser.add_argument("--author-model", default=None, help="CLI --model for the author")
    parser.add_argument("--reviewer-model", default=None, help="CLI --model for the reviewer")
    parser.add_argument("--budget-usd", type=float, default=None, help="--max-budget-usd per call")
    parser.add_argument("--timeout", type=int, default=3600, help="seconds per CLI call")
    parser.add_argument("--seeds", type=int, default=5, help="seeds for dsz verify (default 5)")
    parser.add_argument("--brief", default="", help="optional scenario idea for the author")
    args = parser.parse_args()
    return LoopConfig(find_claude_bin(), args.rounds, args.author_model, args.reviewer_model, args.budget_usd,
                      args.timeout, args.seeds, args.brief)


def main() -> None:
    """Run the loop and print where the run log is."""
    log = run_loop(parse_args())
    summary = log.summary
    print(f"status={summary['status']} cost=${summary['total_cost_usd']:.2f} log={log.directory}")
    if "installed_at" in summary:
        print(f"scenario for review: {summary['installed_at']}")


if __name__ == "__main__":
    main()
