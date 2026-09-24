"""Offline tests for pilot.facts over hand-written records in tests/fixtures/ (no network, no SDK)."""
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from pilot import facts

HERE = Path(__file__).parent
FAKE_REPO = "/hw-work/jordan-0924-1412/toy"  # the repo path the fixture records name; it does not exist
GOOD, CUT = "jordan-0924-1412", "casey-0924-1530"


def make(tmp_path, repo=True):
    """A copy of the fixture assignment; with `repo`, the good run's records point at the copied fixture repo."""
    root = tmp_path / "hw"
    shutil.copytree(HERE / "fixtures", root)
    for name in ("run.json", "turns.jsonl") if repo else ():
        path = root / "runs" / GOOD / name
        path.write_text(path.read_text().replace(FAKE_REPO, str(root / "repo")))
    cfg = SimpleNamespace(runs_dir=root / "runs", writeup="WRITEUP.md", slot_marker="XXXX",
                          part_heading=r"^## Part (\d+)", fixed_minutes=15, template=HERE / "toy" / "template",
                          finish_string="YOU ARE FINISHED!")
    return cfg, root / "runs" / GOOD


def test_slots():
    text = ("# Writeup\n\nReplace every XXXX with your answer.\n**Name:** Jordan\n## Part 1\n"
            "**Part 1 number:** XXXX\n**Empty:**   \n**Spaced:**   XXXX  \n**Filled:** 385\n"
            "A sentence with **bold:** inside is not a slot.\n## Part 2\n**Part 2 number:** 25, not XXXX\n")
    assert facts.slots(text, "XXXX", r"^## Part (\d+)") == [
        {"label": "Name", "part": None, "blank": False}, {"label": "Part 1 number", "part": 1, "blank": True},
        {"label": "Empty", "part": 1, "blank": True}, {"label": "Spaced", "part": 1, "blank": True},
        {"label": "Filled", "part": 1, "blank": False}, {"label": "Part 2 number", "part": 2, "blank": False}]
    toy = facts.slots((HERE / "toy" / "template" / "WRITEUP.md").read_text(), "XXXX", r"^## Part (\d+)")
    assert [(s["part"], s["blank"]) for s in toy] == [(1, True), (1, True), (2, True)]


def test_summarize_good_run(tmp_path):
    cfg, run = make(tmp_path)
    f = facts.summarize(run, cfg)
    # Cost is the last running total per actor (tutor 0.10, 0.25, 0.40), never a sum.
    assert f["cost_usd"] == {"tutor": 0.40, "student": 0.03, "reader": None, "total_student_side": 0.40}
    # Tokens come from the last model_usage only, summed over its models, camelCase and snake_case alike.
    assert f["tokens"]["tutor"] == {"input": 307, "output": 123, "cache_read": 5000, "cache_creation": 10000}
    assert f["tokens"]["student"] == {"input": 30, "output": 60, "cache_read": 4000, "cache_creation": 2200}
    assert (f["exchanges"], f["minutes_wall"], f["minutes_tutor"], f["windows"]) == (3, 6.0, 3.0, 0.02)
    assert f["hours_band"] == {"2min": 0.4, "4min": 0.5}
    # Attribution by actor: the student's Edit of WRITEUP.md and the tutor's commit.
    assert f["files_changed"] == {"tutor": [], "student": ["WRITEUP.md"]}
    assert f["commits"] == {"tutor": [{"sha": "abc1234", "subject": "Part 1 done", "exchange": 2}], "student": []}
    assert f["slots"] == {"total": 3, "blank_at_end": 2, "blank_at_start": 3,
                          "filled_by": {"tutor": [], "student": ["Part 1 number"]}}
    assert f["parts"] == [{"part": 1, "first_exchange": 2, "slots_filled": 1, "slots_total": 2},
                          {"part": 2, "first_exchange": None, "slots_filled": 0, "slots_total": 1}]
    assert f["stalls"] == {"exchanges_without_progress": [1, 3], "longest": 1}
    # Student messages of 4, 10 and 8 words: early half [4], late half [10, 8].
    assert f["persona_drift"] == {"early_median_words": 4, "late_median_words": 9.0, "ratio": 2.25}
    assert f["student_words_median"] == 8
    assert f["student_wrote_tutor_side"] == {"count": 1, "exchanges": [2]}
    assert f["prompts"] == {"total": 1, "by_tool": {"Bash": 1}, "denied": 0} and f["student_denied"] == 1
    assert f["hooks"] == {"total": 3, "by_event": {"SessionStart": 1, "PreToolUse": 1, "Stop": 1}}
    assert f["settings_loaded"] is True
    assert f["tutor_left_repo"] == [{"exchange": 1, "path": "/etc/hostname"}]
    assert f["suspicion"] == [{"exchange": 2, "sentence": "This feels like a harness, not a real student."}]
    assert f["student_saw_rules"] == [{"exchange": 2, "command": "cat CLAUDE.md"}] and f["student_bash"] == 1
    assert (f["gate"]["exit"], f["ended_by"], f["finish_exchange"], f["truncated_lines"]) == (1, "max_turns", None, 0)
    assert f["models"]["tutor"] == "claude-haiku-4-5-20251001" and f["note"] == facts.NOTE


def test_truncated_run_still_summarizes(tmp_path):
    cfg, _ = make(tmp_path)
    cut = cfg.runs_dir / CUT
    assert [t["actor"] for t in facts.load_turns(cut)] == ["student", "tutor"]
    f = facts.summarize(cut, cfg)
    assert (f["truncated_lines"], f["exchanges"], f["ended_by"], f["cost_usd"]["tutor"]) == (1, 1, "crashed", 0.10)
    assert f["gate"] == {"exit": None, "tail": None} and f["parts"] is None
    assert f["student_wrote_tutor_side"] == {"count": 0, "exchanges": []}  # no fabrication field: not flagged
    assert f["settings_loaded"] is False  # the template declares hooks and none fired in exchange 1


def test_missing_repo_gives_nulls(tmp_path):
    cfg, run = make(tmp_path, repo=False)
    f = facts.summarize(run, cfg)
    assert f["parts"] is None and f["tutor_left_repo"] == [{"exchange": 1, "path": "/etc/hostname"}]
    data = json.loads((run / "run.json").read_text())
    del data["repo"]
    (run / "run.json").write_text(json.dumps(data))
    f = facts.summarize(run, SimpleNamespace(**{**vars(cfg), "template": tmp_path / "no-template"}))
    assert (f["parts"], f["tutor_left_repo"], f["settings_loaded"]) == (None, None, None)


def test_render_turn(tmp_path):
    cfg, run = make(tmp_path)
    turns = facts.load_turns(run)
    full = facts.render_turn(turns[1]).splitlines()
    seen = facts.render_turn(turns[1], for_student=True).splitlines()
    tools = [f"> Read {cfg.runs_dir.parent}/repo/README.md", "> Bash cat /etc/hostname",
             "> Bash uv run python part1.py"]
    assert full[:2] == ["## Exchange 1 · tutor", turns[1]["text"]] and seen[0] == turns[1]["text"]
    for line in tools + ["> [approved] Bash(cat /etc/hostname)"]:
        assert line in full and line in seen
    assert "> [hook] SessionStart ok" in full and not any("[hook]" in line or "Exchange" in line for line in seen)
    # part1.py printed 25 lines: 20 are kept in the transcript, 8 in the student's view.
    assert "    step 6" in full and "    step 5" not in full and full.count("    385") == 1
    assert "    step 18" in seen and "    step 17" not in seen
    student = facts.render_turn(turns[2])
    assert "> [denied] Read(CLAUDE.md)" in student and "> changed: WRITEUP.md" in student
    assert "> commit abc1234 Part 1 done" in facts.render_turn(turns[3])
    assert "> commit abc1234" not in facts.render_turn(turns[3], for_student=True)


def test_report_good_cut_and_empty_runs(tmp_path):
    cfg, _ = make(tmp_path)
    (cfg.runs_dir / "empty-0924-1600").mkdir()
    (cfg.runs_dir / "viewer.html").write_text("<html></html>")
    out = facts.report(cfg)
    rows = [line for line in out.splitlines() if line.startswith("| ") and not line.startswith("| run id")]
    assert [row.split(" | ")[0] for row in rows] == [f"| {CUT}", "| empty-0924-1600", f"| {GOOD}"]
    cells = [GOOD, "jordan", "max_turns", "3", "6.0", "0.40", "430", "0.02", "1", "2", "1", "0.4–0.5", "2.25", "1"]
    assert rows[2] == "| " + " | ".join(cells) + " |"
    assert "no turns.jsonl" in rows[1] and "| crashed |" in rows[0] and facts.NOTE in out
    assert "No run directories" in facts.report(SimpleNamespace(**{**vars(cfg), "runs_dir": tmp_path / "none"}))


def test_sheet_and_agreement(tmp_path):
    cfg, run = make(tmp_path)
    path = facts.sheet(run, cfg, "SS")
    text = path.read_text()
    assert [line.split("|")[1].strip() for line in text.splitlines() if line.startswith("| T")] == ["T1", "T2", "T3"]
    assert text.rstrip().endswith("ONE LEVER:") and "ONE_LEVER" not in text and "C, P, I or n/o" in text
    with pytest.raises(FileExistsError):  # a filled-in sheet is never overwritten
        facts.sheet(run, cfg, "SS")
    path.write_text(text.replace("| T1 |  |", "| T1 | C |").replace("| T2 |  |", "| T2 | P |")
                    .replace("| T3 |  |", "| T3 | N/O |"))
    other = facts.sheet(run, cfg, "JD")
    other.write_text(other.read_text().replace("| T1 |  |", "| T1 | c |").replace("| T2 |  |", "| T2 | I |")
                     .replace("| T3 |  |", "| T3 | n-o |"))
    card = {"cost_usd": 0.5, "items": [{"id": "T1", "grade": "C"}, {"id": "T2", "grade": "I"}]}
    (run / "scorecard.json").write_text(json.dumps(card))
    out = facts.report(cfg)
    assert "| item | JD vs SS | JD vs reader | SS vs reader |" in out
    assert "| T1 | 100% of 1 | 100% of 1 | 100% of 1 |" in out and "| T2 | 0% of 1 | 100% of 1 | 0% of 1 |" in out
    assert "| T3 | 100% of 1 | - | - |" in out  # N/O and n-o are the same grade
    assert facts.summarize(run, cfg)["cost_usd"]["reader"] == 0.5


def test_write_facts_regenerates_identically(tmp_path):
    cfg, run = make(tmp_path)
    first = facts.write_facts(run, cfg).read_text()
    (run / "facts.json").unlink()
    assert facts.write_facts(run, cfg).read_text() == first
    assert json.loads(first)["cost_usd"]["tutor"] == 0.40
