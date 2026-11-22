"""Tests for the brief (`brief.py`) and how the loop uses it. Run: `python -m pytest authoring`."""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import loop
import pytest
from brief import Brief, BriefError, infeasible, load_brief, main, parse_brief, stamp_problem, unknown_names

HERE = Path(__file__).resolve().parent
VOCAB = {"stamp": "abc", "fixture_kinds": ["fridge", "counter"], "events": ["relocate"]}


def _vocabulary() -> dict:
    """Return the real platform vocabulary from `dsz vocab --json`."""
    return json.loads(loop.dsz_vocab("--json"))


def _doc_example() -> dict:
    """Return the JSON example in brief.md."""
    return json.loads(re.search(r"```json\n(.*?)```", (HERE / "brief.md").read_text(encoding="utf-8"), re.S).group(1))


def test_the_documented_example_is_a_valid_brief_with_known_names():
    """The example in brief.md parses and names only real vocabulary."""
    brief = parse_brief(_doc_example())
    assert brief.mode == "strict" and unknown_names(brief, _vocabulary()) == []


@pytest.mark.parametrize("change, problem", [
    ({"version": 2}, "version must be 1"),
    ({"mode": "loose"}, "mode must be one of"),
    ({"colour": "red"}, "unknown key 'colour'"),
    ({"must": "P3"}, "must must be a list"),
    ({"mode": "free"}, "mode free takes no objective"),
    ({"objective": ""}, "mode strict needs an objective"),
])
def test_parser_reports_each_problem(change, problem):
    """Each malformed field is named."""
    with pytest.raises(BriefError) as e:
        parse_brief({**_doc_example(), **change})
    assert any(problem in p for p in e.value.problems)


def test_load_brief_from_nothing_text_or_file(tmp_path):
    """No brief is free, text is improve with that objective, a .json path is parsed."""
    assert load_brief("") == Brief("free")
    idea = "A canteen with a moving co-worker"
    assert load_brief(idea) == Brief("improve", objective=idea)
    path = tmp_path / "brief.json"
    path.write_text(json.dumps(_doc_example()), encoding="utf-8")
    assert load_brief(str(path)).mode == "strict"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(BriefError, match="not valid JSON"):
        load_brief(str(path))


def test_names_and_stamp_are_checked_against_the_vocabulary():
    """Backticked names must be known (rule IDs are allowed); an old stamp gives a warning."""
    brief = Brief("improve", objective="Move it from the `fridge` to the `garage` (`CR8`).", vocabulary="old")
    assert unknown_names(brief, VOCAB) == ["`garage` is not in the vocabulary"]
    assert "written against vocabulary old" in stamp_problem(brief, VOCAB)
    assert stamp_problem(Brief("free"), VOCAB) is None


def test_brief_text_carries_the_mode_rule():
    """BRIEF.md tells the author what the mode allows, including how to declare a strict brief infeasible."""
    text = Brief("strict", objective="X", must=("P3",)).text()
    assert "Mode: **strict**" in text and "BRIEF INFEASIBLE:" in text and "## Must\n\n- P3" in text


def test_infeasible_reports_are_recognised():
    """The loop finds the declaration with or without bold, and only at a line start."""
    assert infeasible("BRIEF INFEASIBLE: CR6, the objective names the hidden place") == (
        "CR6, the objective names the hidden place")
    assert infeasible("Some intro.\n**BRIEF INFEASIBLE:** MR3") == "MR3"
    assert infeasible("The brief was feasible; no BRIEF INFEASIBLE: here") is None


def test_checker_exit_codes(tmp_path, capsys):
    """0 for a valid brief, 1 for problems, 2 if the file cannot be read."""
    good, vocab = tmp_path / "good.json", tmp_path / "vocabulary.json"
    good.write_text(json.dumps(_doc_example()), encoding="utf-8")
    vocab.write_text(json.dumps(_vocabulary()), encoding="utf-8")
    assert main([str(good), "--vocabulary", str(vocab)]) == 0
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({**_doc_example(), "mode": "x"}), encoding="utf-8")
    assert main([str(bad)]) == 1
    assert main([str(tmp_path / "missing.json")]) == 2
    capsys.readouterr()


def test_checker_runs_standalone(tmp_path):
    """brief.py needs only the standard library: it runs isolated from this repository."""
    copy = tmp_path / "brief.py"
    shutil.copyfile(HERE / "brief.py", copy)
    good = tmp_path / "good.json"
    good.write_text(json.dumps(_doc_example()), encoding="utf-8")
    done = subprocess.run([sys.executable, "-I", str(copy), str(good)], capture_output=True, text=True)
    assert done.returncode == 0 and "OK: a valid strict brief" in done.stdout


def test_workspace_gets_the_brief_and_any_warning():
    """The sandbox holds BRIEF.md; a stamp warning is appended to it."""
    workspace = loop.build_workspace(Brief("improve", objective="A canteen"), "vocabulary changed")
    try:
        text = (workspace / "BRIEF.md").read_text(encoding="utf-8")
        assert "Mode: **improve**" in text and "A canteen" in text and "Warning: vocabulary changed" in text
        assert {p.name for p in workspace.iterdir()} == {"SPEC.md", "FORMAT.md", "VOCABULARY.md", "BRIEF.md",
                                                         "scenario"}
    finally:
        shutil.rmtree(workspace)
