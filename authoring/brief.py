"""The scenario brief: the prior a person gives the authoring loop. Standard library only.

The loop imports this file, and the `scenario-brief` skill ships it as its checker, so a
brief means the same thing in both places. The format is in `brief.md`.

Usage, as a checker:
    python brief.py brief.json [--vocabulary vocabulary.json]
Exit codes: 0 valid, 1 invalid, 2 the file cannot be read.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

VERSION = 1
MODES = ("free", "improve", "strict")
KEYS = {"version", "vocabulary", "mode", "objective", "notes", "must", "avoid"}
NAME = re.compile(r"`([^`]+)`")
RULE_IDS = re.compile(r"(P[1-5]|MR[1-5]|CR([1-9]|1[0-5])|OC[1-3]|[HMRCVE]1)")
MODE_TEXT = {
    "free": "There is no brief. Choose the idea and the objective yourself.",
    "improve": ("Start from this brief. You may change anything in it to meet SPEC.md. In your report, list each "
                "change and why."),
    "strict": ("Follow this brief. Keep the objective and every item under 'Must'. Only fill gaps and translate it "
               "into the format. If the brief cannot meet SPEC.md or the platform limits, write no scenario. Start "
               "your report with the line 'BRIEF INFEASIBLE:' followed by the rule IDs and the reason."),
}


class BriefError(ValueError):
    """A brief is malformed. `problems` lists every issue found."""

    def __init__(self, problems: list[str]) -> None:
        """Record all problems."""
        self.problems = problems
        super().__init__("invalid brief:\n- " + "\n- ".join(problems))


@dataclass(frozen=True)
class Brief:
    """A parsed brief."""

    mode: str
    objective: str = ""
    notes: str = ""
    must: tuple[str, ...] = ()
    avoid: tuple[str, ...] = ()
    vocabulary: str | None = None  # stamp of the vocabulary the brief was written against

    def text(self) -> str:
        """Return the brief as Markdown for the author and the reviewer (`BRIEF.md`)."""
        lines = ["# Brief", "", f"Mode: **{self.mode}**. {MODE_TEXT[self.mode]}"]
        for title, body in (("Objective", self.objective), ("Notes", self.notes)):
            if body:
                lines += ["", f"## {title}", "", body.strip()]
        for title, items in (("Must", self.must), ("Avoid", self.avoid)):
            if items:
                lines += ["", f"## {title}", ""] + [f"- {i}" for i in items]
        return "\n".join(lines) + "\n"


def parse_brief(raw: object) -> Brief:
    """Parse a brief mapping. Raise BriefError listing every problem."""
    if not isinstance(raw, dict):
        raise BriefError(["a brief is a JSON object"])
    p = [f"unknown key '{k}'" for k in sorted(set(raw) - KEYS)]
    if raw.get("version") != VERSION:
        p.append(f"version must be {VERSION}")
    mode = raw.get("mode")
    if mode not in MODES:
        p.append(f"mode must be one of {', '.join(MODES)}")
    for key in ("objective", "notes", "vocabulary"):
        if key in raw and not isinstance(raw[key], str):
            p.append(f"{key} must be a string")
    for key in ("must", "avoid"):
        if key in raw and not (isinstance(raw[key], list) and all(isinstance(x, str) and x for x in raw[key])):
            p.append(f"{key} must be a list of non-empty strings")
    objective = raw.get("objective", "") if isinstance(raw.get("objective"), str) else ""
    if mode == "free" and (objective.strip() or raw.get("must")):
        p.append("mode free takes no objective and no must list; use improve or strict")
    if mode in ("improve", "strict") and not objective.strip():
        p.append(f"mode {mode} needs an objective")
    if p:
        raise BriefError(p)
    return Brief(mode, objective, raw.get("notes", ""), tuple(raw.get("must", ())), tuple(raw.get("avoid", ())),
                 raw.get("vocabulary"))


def load_brief(arg: str) -> Brief:
    """Return the brief for a `--brief` value: empty is free, a .json path is a file, other text is improve.

    Raises:
        BriefError: if the file is malformed.
        OSError: if a .json path cannot be read.
    """
    if not arg.strip():
        return Brief("free")
    if arg.strip().endswith(".json"):
        try:
            return parse_brief(json.loads(Path(arg.strip()).read_text(encoding="utf-8")))
        except json.JSONDecodeError as e:
            raise BriefError([f"not valid JSON: {e}"]) from e
    return Brief("improve", objective=arg.strip())


def unknown_names(brief: Brief, vocabulary: dict) -> list[str]:
    """Return problems for `names` in backticks that are neither vocabulary names nor rule IDs."""
    known = {n for key, names in vocabulary.items() if key != "stamp" for n in names}
    texts = [brief.objective, brief.notes, *brief.must, *brief.avoid]
    names = sorted({n for t in texts for n in NAME.findall(t)})
    return [f"`{n}` is not in the vocabulary" for n in names if n not in known and not RULE_IDS.fullmatch(n)]


def stamp_problem(brief: Brief, vocabulary: dict) -> str | None:
    """Return a warning if the brief names another vocabulary stamp than `vocabulary` has."""
    if brief.vocabulary and brief.vocabulary != vocabulary.get("stamp"):
        return (f"the brief was written against vocabulary {brief.vocabulary}; the platform now has "
                f"{vocabulary.get('stamp')}. Check the names in the brief")
    return None


def infeasible(report: str) -> str | None:
    """Return the reason if an author report declares the brief infeasible, else None."""
    match = re.search(r"^\s*\**BRIEF INFEASIBLE:?\**\s*(.*)$", report, re.MULTILINE)
    if match is None:
        return None
    return match.group(1).strip() or "no reason given"


def main(argv: list[str] | None = None) -> int:
    """Check one brief file; print every problem."""
    parser = argparse.ArgumentParser(description="Check a scenario brief.")
    parser.add_argument("brief", type=Path)
    parser.add_argument("--vocabulary", type=Path, help="vocabulary.json, to check the names in backticks")
    args = parser.parse_args(argv)
    try:
        raw = json.loads(args.brief.read_text(encoding="utf-8"))
        vocabulary = json.loads(args.vocabulary.read_text(encoding="utf-8")) if args.vocabulary else None
    except (OSError, json.JSONDecodeError) as e:
        print(f"cannot read: {e}")
        return 2
    try:
        brief = parse_brief(raw)
    except BriefError as e:
        print("\n".join(f"- {p}" for p in e.problems))
        return 1
    problems = unknown_names(brief, vocabulary) if vocabulary else []
    warning = stamp_problem(brief, vocabulary) if vocabulary else None
    print("\n".join([f"- {p}" for p in problems] + ([f"warning: {warning}"] if warning else []))
          or f"OK: a valid {brief.mode} brief")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
