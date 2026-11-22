"""Command line: `dsz verify <folder>` and `dsz vocab [--json]`.

Exit codes for `verify`: 0 pass, 1 fail, 2 error in the verifier itself or bad arguments.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    """Run one subcommand and return its exit code."""
    parser = argparse.ArgumentParser(prog="dsz", description="Day Shift Zero tools.")
    sub = parser.add_subparsers(dest="command", required=True)
    v = sub.add_parser("verify", help="check a scenario folder (stages S1 to S4)")
    v.add_argument("folder", type=Path, help="folder with scenario.yaml")
    v.add_argument("--seeds", type=int, default=5, help="seeds 0..N-1 for S4 (default 5)")
    v.add_argument("--json", type=Path, default=None, help="also write the report as JSON to this path")
    vocab = sub.add_parser("vocab", help="print the platform vocabulary as Markdown")
    vocab.add_argument("--json", action="store_true", help="print the names and the stamp as JSON instead")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(errors="replace")  # reports quote scenario text; never crash on the console encoding

    if args.command == "vocab":
        from dsz.scenario.vocabulary_doc import vocabulary_data, vocabulary_markdown
        sys.stdout.write(json.dumps(vocabulary_data(), indent=2) + "\n" if args.json else vocabulary_markdown())
        return 0

    from dsz.certify.verify import verify
    if args.seeds < 1:
        parser.error("--seeds must be at least 1")
    try:
        report = verify(args.folder, seeds=args.seeds)
    except Exception as e:  # noqa: BLE001  (a verifier bug is exit code 2, not a scenario failure)
        print(f"verifier error: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    print(report.to_text())
    if args.json:
        args.json.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
