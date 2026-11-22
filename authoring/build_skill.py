"""Build the `scenario-brief` skill from this repository.

The skill is a snapshot: SKILL.md, the references the loop's agents also read (task spec,
FORMAT.md, vocabulary), the brief format, and `brief.py` as its checker. It records the
commit and the vocabulary stamp it was built from.

Usage, from the repository root:
    python authoring/build_skill.py [--out dist]
Output: <out>/scenario-brief/ and <out>/scenario-brief.skill (a zip of that folder).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

from loop import COPIED, REPO, dsz_vocab

HERE = Path(__file__).resolve().parent
NAME = "scenario-brief"


def build(out: Path) -> Path:
    """Write the skill folder and its .skill zip into `out`; return the zip's path."""
    folder = out / NAME
    shutil.rmtree(folder, ignore_errors=True)
    (folder / "references").mkdir(parents=True)
    (folder / "scripts").mkdir()
    vocabulary = json.loads(dsz_vocab("--json"))
    stamp = f"\n---\n\nBuilt from commit `{_commit()}`, vocabulary stamp `{vocabulary['stamp']}`.\n"
    (folder / "SKILL.md").write_text((HERE / "skill" / "SKILL.md").read_text(encoding="utf-8") + stamp,
                                     encoding="utf-8")
    for name, source in COPIED.items():
        shutil.copyfile(source, folder / "references" / name)
    (folder / "references" / "VOCABULARY.md").write_text(dsz_vocab(), encoding="utf-8")
    (folder / "references" / "vocabulary.json").write_text(json.dumps(vocabulary, indent=2) + "\n", encoding="utf-8")
    shutil.copyfile(HERE / "brief.md", folder / "references" / "brief.md")
    shutil.copyfile(HERE / "brief.py", folder / "scripts" / "brief.py")
    archive = out / f"{NAME}.skill"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                z.write(path, path.relative_to(out).as_posix())
    return archive


def _commit() -> str:
    """Return the short commit hash, with `-dirty` if the working tree has changes; `unknown` outside git."""
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True, text=True)
    if head.returncode != 0 or not head.stdout.strip():
        return "unknown"
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    return head.stdout.strip() + ("-dirty" if dirty else "")


def main() -> None:
    """Build the skill and print where it is."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=REPO / "dist", help="output folder (default: dist/)")
    print(build(parser.parse_args().out))


if __name__ == "__main__":
    main()
