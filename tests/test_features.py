"""Offline tests for the keys added for templates like HW2: heading slots, the finish pattern, any-command gates, the
token file and its redaction, efforts, and config checks. No network, no SDK session."""
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from pilot import facts, run

HERE = Path(__file__).parent

HEADINGS = """# A writeup

**Name:** XXXX
**Date:** 2026-10-07

## Part 0: Set up

### Step B: What an MCP server is

XXXX

### Step B: Why not paste code

A server gives Claude tools.
**Note:** this bold line is part of the answer, not a slot.

### Step D: How it connects

## Part 1: The tools

### Step 6: Your diagram

XXXX (add the diagram image to the repository and link it here)

### Step 7: Your grades

XXXX, but I changed my mind

## Part 2

[TBD]
"""


def test_heading_slots():
    got = facts.slots(HEADINGS, "XXXX", r"^## Part (\d+)", r"^### (.+)$")
    assert [(s["label"], s["part"], s["blank"]) for s in got] == [
        ("Name", None, True), ("Date", None, False),
        ("Step B: What an MCP server is", 0, True), ("Step B: Why not paste code", 0, False),
        ("Step D: How it connects", 0, True), ("Step 6: Your diagram", 1, True), ("Step 7: Your grades", 1, False)]
    # Without slot_heading the same text reads as label slots only: the old behaviour.
    assert [s["label"] for s in facts.slots(HEADINGS, "XXXX", r"^## Part (\d+)")] == ["Name", "Date", "Note"]


def test_finish_matcher():
    cfg = SimpleNamespace(finish_string="YOU ARE FINISHED!", finish_pattern=r"YOU ARE FINISHED WITH PART \d+!")
    match = run.finish_matcher(cfg)
    for line in ("YOU ARE FINISHED WITH PART 0!", "**YOU ARE FINISHED WITH PART 0!**", "  ## YOU ARE FINISHED!",
                 "Thanks for submitting. **YOU ARE FINISHED WITH PART 0!**", "_YOU ARE FINISHED WITH PART 12!_"):
        assert match(line), line
    for line in ('The checkpoint says "YOU ARE FINISHED WITH PART N!" at the end.', "YOU ARE FINISHED WITH PART 0",
                 "When you submit, I'll say YOU ARE FINISHED WITH PART 0!", ""):
        assert not match(line), line
    plain = run.finish_matcher(SimpleNamespace(finish_string="YOU ARE FINISHED!", finish_pattern=""))
    assert plain("YOU ARE FINISHED!") and not plain("YOU ARE FINISHED WITH PART 0!")


def _assignment(tmp_path, toml: str, writeup: str | None = None) -> Path:
    adir = tmp_path / "course"
    shutil.copytree(HERE / "toy", adir, ignore=shutil.ignore_patterns("runs"))
    if writeup is not None:
        (adir / "template" / "WRITEUP.md").write_text(writeup)
    (adir / "pilot.toml").write_text('template = "template"\nwork_dir = "%s"\n%s' % (tmp_path / "work", toml))
    return adir


def test_config_keys(tmp_path):
    cfg = run.load_config(_assignment(tmp_path, 'gate = "git log --format=%s | grep -qx \'Part 0 done\'"\n'
                                                 'slot_heading = "^### (.+)$"\nrepo_name = "comp440-hw2"\n'
                                                 'tutor_effort = "low"\n[settings]\napprove = "ask"\nuv = "present"\n'
                                                 '[scenarios.no-uv]\nuv = "missing"\n', HEADINGS))
    assert (cfg.repo_name, cfg.tutor_effort, cfg.settings, cfg.scenarios["no-uv"]) == \
        ("comp440-hw2", "low", {"approve": "ask", "uv": "present"}, {"uv": "missing"})
    assert run.load_config(_assignment(tmp_path / "b", 'gate = ""\n')).gate == ""
    for bad, why in (('tutor_effort = "fast"\n', "tutor_effort"), ('finish_pattern = "("\n', "regular expression"),
                     ('gate = "python3 missing_check.py"\n', "missing_check.py"),
                     ('approve_servers = ["x"]\n', "local"), ('world = "nowhere.py"\n', "world module"),
                     ('[settings]\na = "1"\n[scenarios.p]\nb = "2"\n', "scenarios.p")):
        with pytest.raises(run.ConfigError, match=why):
            run.load_config(_assignment(tmp_path / str(abs(hash(bad))), bad))
    with pytest.raises(run.ConfigError, match="heading slot"):
        run.load_config(_assignment(tmp_path / "c", 'slot_heading = "^#### (.+)$"\n', "# W\n\n## Part 1\n\nnone\n"))


def test_token_file_is_read_and_redacted(tmp_path, monkeypatch):
    token = "tok-" + "x" * 40
    (tmp_path / "token").write_text(token + "\n")
    monkeypatch.setattr(run, "SECRETS", [])
    cfg = SimpleNamespace(oauth_token_file=str(tmp_path / "token"), env_keep=("CLAUDE_CODE_OAUTH_TOKEN",), env_drop=())
    env, _ = run.clean_env(cfg)
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == token and run.SECRETS == [token]
    run.record_turn(tmp_path, {"exchange": 1, "actor": "tutor", "text": f"env shows {token}", "tools": [],
                               "prompts": []})
    run._write_json(tmp_path / "run.json", {"note": token})
    for name in ("turns.jsonl", "transcript.md", "run.json"):
        text = (tmp_path / name).read_text()
        assert token not in text and run.REDACTED in text, name
    (tmp_path / "bad").write_text("two words\n")
    with pytest.raises(run.ConfigError, match="one token"):
        run.read_token(SimpleNamespace(oauth_token_file=str(tmp_path / "bad")))


def test_env_drop(monkeypatch):
    monkeypatch.setenv("UV_CONFIG_FILE", "/somewhere/uv.toml")
    monkeypatch.setenv("UV_X", "1")
    monkeypatch.setenv("PIP_CONFIG_FILE", "/somewhere/pip.conf")
    env, stripped = run.clean_env(SimpleNamespace(env_keep=(), env_drop=("UV_*", "PIP_CONFIG_FILE"),
                                                  oauth_token_file=""))
    assert {"UV_CONFIG_FILE", "UV_X", "PIP_CONFIG_FILE"} <= set(stripped) and "UV_X" not in env


def test_session_efforts(tmp_path):
    d = tmp_path / "projects" / "-x-repo"
    d.mkdir(parents=True)
    lines = [{"type": "user"}, {"type": "assistant", "perTurnEffort": "low"}, {"type": "assistant", "perTurnEffort": "low"}]
    (d / "abc.jsonl").write_text("\n".join(map(json.dumps, lines)) + "\nnot json\n")
    assert run.session_efforts(tmp_path, ["abc", None]) == ["low"] and run.session_efforts(tmp_path, ["zzz"]) == []


@pytest.mark.parametrize("planted", ["CLAUDE.md", "CLAUDE.local.md", ".mcp.json", ".claude/CLAUDE.md",
                                     ".claude/agents/x.md", ".claude/skills/x/SKILL.md", ".claude/rules/x.md"])
def test_instructions_above_the_repo_are_refused(tmp_path, planted):
    """Claude Code loads these from every folder above the repository (CLI 2.1.281, checked with canary files), so a
    work_dir below one (a home folder holding someone's global instructions) is refused."""
    above = tmp_path / "above"
    (above / planted).parent.mkdir(parents=True, exist_ok=True)
    (above / planted).write_text("canary")
    adir = _assignment(tmp_path, "")
    toml = (adir / "pilot.toml").read_text().replace(str(tmp_path / "work"), str(above / "work"))
    (adir / "pilot.toml").write_text(toml)
    with pytest.raises(run.ConfigError, match="Claude Code files"):
        run.load_config(adir)
    assert run.ancestor_instructions(above / "work" / "r" / "repo") == [str(above / planted.split("/x")[0])
                                                                         if "/x" in planted else str(above / planted)]


def test_session_instructions(tmp_path):
    d = tmp_path / "projects" / "-x"
    d.mkdir(parents=True)
    lines = [{"type": "attachment", "attachment": {"type": "instructions", "files": [
        {"path": "/w/r/repo/CLAUDE.md", "type": "Project", "content": "rules"},
        {"path": "/home/someone/.claude/CLAUDE.md", "type": "Project", "content": "global"}]},
        "rendered": [{"type": "text", "content": "<system-reminder>\nInstructions.\n\nContents of /home/someone/.claude/"
                      "CLAUDE.md (project instructions):\n\nglobal\n\nContents of /w/r/repo/CLAUDE.md (project "
                      "instructions):\n\nrules\n</system-reminder>"}]}]
    (d / "s.jsonl").write_text("\n".join(map(json.dumps, lines)) + "\n")
    assert run.session_instructions(tmp_path, ["s"]) == [{"path": "/w/r/repo/CLAUDE.md", "type": "Project"},
                                                         {"path": "/home/someone/.claude/CLAUDE.md", "type": "Project"}]
    text, gone = run._scrub_instructions((d / "s.jsonl").read_text(), "/w/r")
    assert gone == ["/home/someone/.claude/CLAUDE.md"] and "global" not in text and "rules" in text
    rendered = json.loads(text)["rendered"][0]["content"]
    assert "Contents of /w/r/repo/CLAUDE.md" in rendered and "someone" not in rendered
    assert rendered.startswith("<system-reminder>") and rendered.endswith("</system-reminder>")
