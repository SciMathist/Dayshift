"""Tests for build_skill.py: the package holds what it should and works outside this repository."""

import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

import build_skill
from build_skill import build

HERE = Path(__file__).resolve().parent
FILES = {"SKILL.md", "references/SPEC.md", "references/FORMAT.md", "references/VOCABULARY.md",
         "references/vocabulary.json", "references/brief.md", "scripts/brief.py"}


def test_skill_package_contents_and_stamps(tmp_path):
    """The zip has one top folder with the expected files; SKILL.md has front matter and build stamps."""
    archive = build(tmp_path)
    with zipfile.ZipFile(archive) as z:
        names = set(z.namelist())
    assert names == {f"scenario-brief/{f}" for f in FILES}
    skill = (tmp_path / "scenario-brief" / "SKILL.md").read_text(encoding="utf-8")
    vocabulary = json.loads((tmp_path / "scenario-brief" / "references" / "vocabulary.json").read_text(
        encoding="utf-8"))
    assert skill.startswith("---\nname: scenario-brief\ndescription: ")
    stamp = r"Built from commit `([0-9a-f]+(-dirty)?|unknown)`, vocabulary stamp `" + vocabulary["stamp"] + "`"
    assert re.search(stamp, skill)


def test_commit_stamp_outside_git(monkeypatch, tmp_path):
    """Built from a copy that is not a git checkout, the commit stamp says `unknown`, not an empty string."""
    monkeypatch.setattr(build_skill, "REPO", tmp_path)
    assert build_skill._commit() == "unknown"


def test_extracted_skill_checks_a_brief_without_the_repository(tmp_path):
    """Unzipped elsewhere, the checker runs isolated (-I) against the bundled vocabulary."""
    with zipfile.ZipFile(build(tmp_path / "build")) as z:
        z.extractall(tmp_path / "elsewhere")
    skill = tmp_path / "elsewhere" / "scenario-brief"
    example = re.search(r"```json\n(.*?)```", (skill / "references" / "brief.md").read_text(encoding="utf-8"),
                        re.S).group(1)
    (tmp_path / "brief.json").write_text(example, encoding="utf-8")
    done = subprocess.run([sys.executable, "-I", str(skill / "scripts" / "brief.py"), str(tmp_path / "brief.json"),
                           "--vocabulary", str(skill / "references" / "vocabulary.json")],
                          capture_output=True, text=True, cwd=tmp_path)
    assert done.returncode == 0, done.stdout
    assert "OK: a valid strict brief" in done.stdout
