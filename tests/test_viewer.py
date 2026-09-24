"""Offline test of pilot.viewer over a hand-written run, a run directory with no records and a crash-cut line."""
import shutil
from pathlib import Path
from types import SimpleNamespace

from pilot import viewer

FIXTURE = Path(__file__).parent / "fixtures_viewer"


def test_build_renders_records_and_degrades(tmp_path):
    shutil.copytree(FIXTURE, tmp_path / "toy-assignment")
    runs = tmp_path / "toy-assignment" / "runs"
    (runs / "casey-0924-1500").mkdir()  # a run directory with no records (git cannot hold an empty directory)
    with (runs / "jordan-0924-1412" / "turns.jsonl").open("a", encoding="utf-8") as f:
        f.write('{"exchange": 3, "actor": "stud')  # a last line cut off by a crash

    out = viewer.build(SimpleNamespace(runs_dir=runs))
    html = out.read_text(encoding="utf-8")

    assert out == runs / "viewer.html"
    assert "Pilot runs: toy-assignment" in html
    assert 'href="#run-jordan-0924-1412"' in html and 'id="run-jordan-0924-1412"' in html
    assert "script do I run first?" in html  # student text
    assert "Ready. Start with part1.py." in html  # tutor text
    assert "Bash uv run python part1.py" in html and "Read /root/hw-work/jordan-0924-1412/toy/README.md" in html
    assert "[approved] Bash(git push origin main)" in html
    assert "[denied] Read(CLAUDE.md): you have never opened that" in html
    assert "[hook] SessionStart ok" in html
    assert "tutor: commit abc1234 Part 1 done" in html
    assert "student: changed: WRITEUP.md · filled: Part 1 number" in html
    assert html.count("No progress in this exchange") == 1  # facts.json lists exchange 1 as a stall
    assert "<td>0.31</td>" in html and "<td>3.4</td>" in html  # tutor USD and wall minutes from facts.json
    assert "ONE LEVER: Tell the student to run part2.py" in html  # scorecard
    assert "Persona sheet (personas/jordan.md)" in html and "Jordan Lee" in html
    assert "Gate output (exit 1)" in html
    assert "Skipped 1 malformed line in turns.jsonl." in html
    assert "casey-0924-1500: no turns.jsonl in this directory" in html
    assert 'id="run-casey-0924-1500"' not in html
    assert "&lt;b&gt;Which&lt;/b&gt;" in html and "<b>" not in html
    assert "<script" not in html and "http" not in html


def test_build_without_facts_or_runs(tmp_path):
    runs = tmp_path / "a" / "runs"
    shutil.copytree(FIXTURE / "runs" / "jordan-0924-1412", runs / "jordan-0924-1412")
    for name in ("facts.json", "gate.txt", "scorecard.md"):
        (runs / "jordan-0924-1412" / name).unlink()
    html = viewer.build(SimpleNamespace(runs_dir=runs)).read_text(encoding="utf-8")
    assert "<td>2</td>" in html and "<td>0.31</td>" in html  # exchanges and tutor USD from turns.jsonl
    assert "No scorecard.md" in html and "No gate.txt" in html and "No persona sheet at personas/jordan.md" in html
    assert "No run directories" in viewer.build(SimpleNamespace(runs_dir=tmp_path / "b" / "runs")).read_text()
