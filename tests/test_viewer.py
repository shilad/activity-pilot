"""Offline test of pilot.viewer over a hand-written run, a run directory with no records and a crash-cut line."""
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from pilot import viewer

HERE = Path(__file__).parent
FIXTURE = HERE / "fixtures_viewer"
JORDAN = "jordan-0924-1412"


def _copy(tmp_path) -> Path:
    shutil.copytree(FIXTURE, tmp_path / "toy-assignment")
    return tmp_path / "toy-assignment" / "runs"


def _summarizing(runs: Path) -> SimpleNamespace:
    """A config that facts.summarize can use for a run without facts.json, built as tests/test_pilot.py builds it."""
    return SimpleNamespace(runs_dir=runs, writeup="WRITEUP.md", slot_marker="XXXX", part_heading=r"^## Part (\d+)",
                           fixed_minutes=15, template=HERE / "toy" / "template", finish_string="YOU ARE FINISHED!")


def _edit(path: Path, **fields) -> None:
    data = json.loads(path.read_text())
    data.update(fields)
    path.write_text(json.dumps(data))


def _pane(html: str, index: int, key: str) -> str:
    """One tab of one run's panel, as rendered."""
    start = html.index(f'id="p{index}-{key}"')
    end = html.find('class="pane"', start)
    return html[start:] if end == -1 else html[start:end]


def test_build_renders_records_and_degrades(tmp_path):
    runs = _copy(tmp_path)
    (runs / "casey-0924-1500").mkdir()  # a run directory with no records (git cannot hold an empty directory)
    with (runs / JORDAN / "turns.jsonl").open("a", encoding="utf-8") as f:
        f.write('{"exchange": 3, "actor": "stud')  # a last line cut off by a crash

    out = viewer.build(SimpleNamespace(runs_dir=runs))
    html = out.read_text(encoding="utf-8")

    assert out == runs / "viewer.html"
    assert "<title>Pilot runs: toy-assignment</title>" in html
    assert f'aria-controls="run-{JORDAN}"' in html and f'id="run-{JORDAN}"' in html
    assert "script do I run first?" in html  # student text
    assert "Ready. Start with part1.py." in html  # tutor text
    assert "Bash uv run python part1.py" in html and "Read /root/hw-work/jordan-0924-1412/toy/README.md" in html
    assert "[approved] Bash(git push origin main)" in html
    assert "[denied] Read(CLAUDE.md): you have never opened that" in html
    assert "[hook] SessionStart ok" in html
    assert "tutor: commit abc1234 Part 1 done" in html
    assert "student: changed: WRITEUP.md · filled: Part 1 number" in html
    assert html.count("No progress in this exchange") == 1  # facts.json lists exchange 1 as a stall
    assert "<dd>$0.31</dd>" in html and "<dd>3.4 minutes</dd>" in html  # tutor USD and wall minutes from facts.json
    assert "ONE LEVER: Tell the student to run part2.py" in html  # scorecard
    assert "Persona sheet (personas/jordan.md)" in html and "Jordan Lee" in html
    assert "Gate output (exit 1)" in html
    assert "Skipped 1 malformed line in turns.jsonl." in html
    assert "casey-0924-1500: no turns.jsonl in this directory" in html
    assert 'id="run-casey-0924-1500"' not in html
    assert "&lt;b&gt;Which&lt;/b&gt;" in html and "<b>" not in html
    assert html.count("<script") == 1 and "src=" not in html and "http" not in html

    # The rail: a button for the run with records, and a disabled entry for the directory without them.
    assert html.count('data-run="') == 1
    disabled = '<button class="run" type="button" disabled><span><span class="run-id">casey-0924-1500</span>no records'
    assert disabled in html
    # The run ran out of exchanges, so it did not finish, whatever the gate said.
    assert ('<span class="mark tone-bad" title="Ended because the exchange budget ran out. Gate exit 1. 2 of 3 writeup '
            'slots still blank.">✗</span>') in html
    assert re.findall(r'role="tab"[^>]*>([^<]+)</button>', html) == [
        "Conversation", "Outcome", "Scorecard", "The student", "Session facts"]

    # The conversation: Claude Code's start-up question, the student's own commands and what it wrote to itself.
    assert "Student (start-up question)" in html
    assert "[start-up question] notes: Continue without using this MCP server" in html  # the event, in words
    assert "(to self) Opening WRITEUP.md to type the number." in html
    assert ('<span class="tag tone-info">did</span><code>Edit /root/hw-work/jordan-0924-1412/toy/WRITEUP.md</code>'
            in html)
    assert '<span class="tag tone-bad">failed</span><code>Bash ls data/</code>' in html

    # The scorecard: worst first, each grade in its tone, and each exchange a link into the conversation.
    scorecard = _pane(html, 0, "scorecard")
    row = r'<td><span class="mono">([^<]+)</span></td><td><span class="tag tone-(\w+)">([^<]+)</span>'
    rows = re.findall(row, scorecard)
    assert rows == [("R2", "warn", "P"), ("R1", "good", "C"), ("R3", "quiet", "n/o")]
    assert '<a href="#x0-2" data-tab="conversation">2</a>' in scorecard and 'id="x0-2"' in html
    assert "Fidelity: <strong>hold</strong>" in scorecard and "Graded by test-reader for $0.42" in scorecard

    # The student: facts, then the persona's column of the placement grid, then the sheet.
    student = _pane(html, 0, "student")
    assert student.index("Student facts") < student.index("Placement grid") < student.index("Persona sheet")
    assert "From personas/INVENTORY.md, column jordan: 1 solid, 1 shaky, 1 wrong, 1 never" in student
    assert student.index("Group A — Running things") < student.index("Group B — Reading numbers")
    assert '<span class="mono">M1</span>' in student and '<span class="tag tone-good">solid</span>' in student
    assert '<span class="tag tone-bad">wrong<sup>1</sup></span>' in student
    assert "Belief 1: Every number a script prints is an average." in student
    assert student.count('<span class="tag outline tone-quiet">draft</span>') == 1  # N2
    assert student.count('<span class="tag outline tone-bad">open ruling</span>') == 1  # M2


def test_build_without_facts_or_runs(tmp_path):
    runs = tmp_path / "a" / "runs"
    shutil.copytree(FIXTURE / "runs" / JORDAN, runs / JORDAN)
    for name in ("facts.json", "gate.txt", "scorecard.md", "scorecard.json"):
        (runs / JORDAN / name).unlink()
    html = viewer.build(_summarizing(runs)).read_text(encoding="utf-8")
    # The exchanges and the tutor's cost, computed from turns.jsonl.
    assert "<dd>2 of a budget of 2</dd>" in html and "<dd>$0.31</dd>" in html
    assert "No facts.json in this run directory" in html
    assert "No scorecard for this run" in html and "No gate.txt" in html
    assert "No persona sheet at personas/jordan.md" in html
    assert "No placement grid: this assignment has no personas/INVENTORY.md." in html
    assert "No run directories" in viewer.build(SimpleNamespace(runs_dir=tmp_path / "b" / "runs")).read_text()


def test_finish_marks(tmp_path):
    """✓ only when the finish string was seen, whatever the gate's exit; ? when no ending was recorded."""
    runs = _copy(tmp_path)
    _edit(runs / JORDAN / "facts.json", ended_by="finished", finish_exchange=2)
    html = viewer.build(SimpleNamespace(runs_dir=runs)).read_text(encoding="utf-8")
    assert '<span class="mark tone-good" title="The finish string was seen in exchange 2. Gate exit 1.' in html

    for name in ("facts.json", "gate.txt"):
        (runs / JORDAN / name).unlink()
    _edit(runs / JORDAN / "run.json", ended_by=None)
    turns = runs / JORDAN / "turns.jsonl"
    turns.write_text(turns.read_text().replace('"stop": "max_turns"', '"stop": null'))
    html = viewer.build(_summarizing(runs)).read_text(encoding="utf-8")
    assert '<span class="mark tone-quiet" title="No ending was recorded. The gate has not run.' in html


def test_one_run_at_a_time(tmp_path):
    runs = _copy(tmp_path)
    shutil.copytree(runs / JORDAN, runs / "jordan-0924-1300")
    _edit(runs / "jordan-0924-1300" / "run.json", started="2026-09-24T13:00:00Z")
    html = viewer.build(SimpleNamespace(runs_dir=runs)).read_text(encoding="utf-8")
    assert html.count('data-run="') == 2
    assert html.index(f'data-run="run-{JORDAN}"') < html.index('data-run="run-jordan-0924-1300"')  # newest first
    assert f'<section class="panel" id="run-{JORDAN}">' in html
    assert '<section class="panel" id="run-jordan-0924-1300" hidden>' in html
    assert 'data-pane="conversation"><p' in html and 'data-pane="outcome" hidden>' in html


def test_session_facts_show_every_field(tmp_path):
    runs = _copy(tmp_path)
    _edit(runs / JORDAN / "facts.json", restarts={"exits": [2], "starts": [], "sessions": [], "count": 0},
          approvals=[{"exchange": 1, "type": "approval", "server": "notes", "choice": "no", "forced": False}],
          scenario={"names": ["uv-missing"], "settings": {"uv": "missing"}},
          tutor_sessions=[{"exchange": 1, "session_id": "7b1e", "mcp_servers": [], "mcp_tools": {}}],
          side_turns=[{"exchange": 2, "label": "checks phone", "seconds": 3.0}], terminal_turns=[2])
    html = viewer.build(SimpleNamespace(runs_dir=runs)).read_text(encoding="utf-8")
    facts = _pane(html, 0, "facts")
    for record in ("facts.json", "run.json"):
        for key in json.loads((runs / JORDAN / record).read_text()):
            assert f"<dt>{key}</dt>" in facts, (record, key)


def _hw_run(runs: Path, run_id: str, **run_fields) -> Path:
    """A run with what restarts, approvals, side turns, background work and a world module record (no course data)."""
    d = runs / run_id
    d.mkdir(parents=True)
    t = "2026-10-07T12:00:{:02d}Z".format

    def turn(exchange, actor, text, second, **extra):
        return {"exchange": exchange, "actor": actor, "text": text, "t_start": t(second), "t_end": t(second + 1),
                "seconds": 1.0, "tools": [], "prompts": [], "hooks": [], "asks": [], "result": None, **extra}
    usage = {"claude-opus-5-5": {"costUSD": 0.7}, "claude-sonnet-5": {"costUSD": 0.8},
             "claude-haiku-4-5-20251001": {"costUSD": 0.001}}
    turns = [
        turn(1, "student", "Use this MCP server", 0, kind="approval",
             event={"type": "approval", "server": "notes", "choice": "yes", "forced": False}),
        turn(1, "student", "please open the notebook", 2),
        turn(1, "student", "is Connect safe?", 4, kind="side", label="tab opened", sent="queued"),
        turn(1, "tutor", "Opening it now. Yes, Connect is safe.", 3,
             init={"mcp_servers": [{"name": "notes", "status": "pending"}], "mcp_tools": {}},
             queued=[{"text": "is Connect safe?", "t": t(4)}],
             background={"started": ["Grade batch 01"], "finished": ["Grade batch 01: completed"], "waited_s": 140.0},
             result={"total_cost_usd": 1.5, "model_usage": usage}),
        turn(2, "student", "/exit", 10, event={"type": "exit"}),
        turn(3, "student", "", 12, kind="terminal",
             event={"type": "start", "cwd": "/w/repo", "args": [], "mode": "new"}),
        turn(3, "student", "1", 14, kind="picker", event={"type": "resume_pick", "session": "s-1", "offered": 1}),
        turn(4, "student", "back", 16),
        turn(4, "tutor", "Welcome back.", 17, result={"total_cost_usd": 1.6, "model_usage": usage}),
    ]
    (d / "turns.jsonl").write_text("".join(json.dumps(x) + "\n" for x in turns))
    run = {"run_id": run_id, "persona": "sam-p1", "started": "2026-10-07T12:00:00Z", "status": "finished",
           "ended_by": "left", "rubric": "rubric-p1.md", "sandbox": {"sandbox": {"enabled": True}},
           "scenario": {"names": ["sleep"], "settings": {"sleep": "after_step2"}},
           "restarts": [{"exchange": 2, "type": "exit"}, {"exchange": 3, "type": "start", "cwd": "/w/repo"},
                        {"exchange": 3, "type": "session", "resumed": "s-1"}],
           "repo": "/w/repo", "tutor_instructions": [{"path": "/w/repo/CLAUDE.md", "type": "Project"}],
           "world": {"events": [{"t": datetime(2026, 10, 7, 12, 0, 3, tzinfo=timezone.utc).timestamp(),
                                 "type": "colab_tab_opened", "port": 4242}]}, **run_fields}
    (d / "run.json").write_text(json.dumps(run))
    (d / "scorecard.json").write_text(json.dumps({"items": [{"id": "T1", "grade": "C", "turns": [1],
                                                             "evidence": "ok"}], "rubric": "rubric-p1.md",
                                                  "rubric_sha256": "ab" * 32, "fidelity": "hold",
                                                  "rules": "/w/repo/CLAUDE.md"}))
    return d


def test_hw2_style_records(tmp_path):
    """Side turns, typed-while-working messages, the start-up question, /exit and claude again with /resume, world
    events, background work, a continued sitting, the scenario, the rubric, the sandbox, cost per model, and loaded
    instruction files from outside the repository, flagged."""
    runs = tmp_path / "course" / "runs"
    _hw_run(runs, "sam-1007-1100")
    _hw_run(runs, "sam-1007-1200", from_run={"run": "sam-1007-1100", "scrubbed": ["/home/x/.claude/CLAUDE.md"]},
            instructions_outside_repo=["/home/x/.claude/CLAUDE.md"])
    (runs / ".viewignore").write_text("# kept off the page\nhidden-*\n")
    _hw_run(runs, "hidden-1007-1300")
    html = viewer.build(_summarizing(runs)).read_text(encoding="utf-8")
    assert "hidden-1007-1300" not in html  # runs/.viewignore
    assert "Student (while Claude works: tab opened)" in html
    assert "[typed here: sent to Claude while it worked; it saw it at its next step]" in html
    assert "[typed while Claude worked] is Connect safe?" in html
    assert "[start-up question] notes: Use this MCP server" in html
    assert "[Claude Code closed] the student typed /exit" in html and 'class="break"' in html
    assert "Claude Code started again in /w/repo: it reopened conversation s-1." in html
    assert "[resume picker] 1 offered; picked conversation s-1" in html
    assert "[world] colab tab opened: port=4242" in html
    assert "[background] 1 started, 1 ended; the reply waited 140.0 s" in html
    assert "[session start] MCP servers: notes (pending)" in html
    assert "opus-5-5 $0.70 · sonnet-5 $0.80" in html and "haiku" not in html.split("Cost by model")[1][:200]
    assert '<a href="#run-sam-1007-1100" data-run="run-sam-1007-1100">sam-1007-1100</a>' in html
    assert "<dd>sleep</dd>" in html and "<dd>rubric-p1.md</dd>" in html and "Tutor sandbox" in html
    assert "against the rubric-p1.md whose sha256 begins abababababab, with the tutor&#x27;s CLAUDE.md as this run had it" in html
    assert html.count("loaded instruction files from outside its repository") >= 2  # both alarms on the second run
