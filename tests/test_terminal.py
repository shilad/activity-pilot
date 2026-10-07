"""Offline tests for Claude Code's screens acted out by the harness (pilot/terminal.py), the `claude` stand-in, the
local GitHub (pilot/github.py), scenarios and the world module loader (pilot/world.py)."""
import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from pilot import github, terminal, world

PY = shutil.which("python3") or sys.executable


def _repo(tmp_path) -> Path:
    repo = tmp_path / "comp440-hw2"
    repo.mkdir()
    (repo / ".mcp.json").write_text(json.dumps({"mcpServers": {"cool-colab-mcp": {"command": "uv"}, "other": {}}}))
    return repo


def test_approval_screen_and_parse():
    screen = terminal.approval_screen("cool-colab-mcp").splitlines()
    assert screen[0] == "New MCP server found in this project: cool-colab-mcp"
    assert screen[3:6] == ["  Use this MCP server", "  Use this and all future MCP servers in this project",
                           "❯ Continue without using this MCP server"]
    cases = {"Use this MCP server": "yes", "use this mcp server.": "yes", "1": "yes", "yes": "yes",
             "Use this and all future MCP servers in this project": "yes_all", "2": "yes_all",
             "Continue without using this MCP server": "no", "3": "no", "": "no", "(presses Enter)": "no",
             "hmm what is this": "no", "no": "no"}
    for typed, want in cases.items():
        assert terminal.parse_approval(typed) == want, typed


def test_pending_and_apply(tmp_path):
    repo = _repo(tmp_path)
    assert terminal.pending(repo, ["cool-colab-mcp", "missing"]) == ["cool-colab-mcp"]
    terminal.apply_choice(repo, "cool-colab-mcp", "no")
    assert terminal.server_choice(repo, "cool-colab-mcp") == "no" and terminal.pending(repo, ["cool-colab-mcp"]) == []
    data = json.loads(terminal.settings_path(repo).read_text())
    assert data == {"disabledMcpjsonServers": ["cool-colab-mcp"]}
    terminal.settings_path(repo).write_text(json.dumps({"permissions": {"allow": ["Bash(ls:*)"]}}))
    terminal.apply_choice(repo, "cool-colab-mcp", "yes_all")
    data = json.loads(terminal.settings_path(repo).read_text())
    assert data == {"permissions": {"allow": ["Bash(ls:*)"]}, "enabledMcpjsonServers": ["cool-colab-mcp"],
                    "enableAllProjectMcpServers": True}
    assert terminal.server_choice(repo, "other") == "yes"  # "all future" approves every server


def test_exit_resume_and_modes():
    assert terminal.is_exit("/exit") and terminal.is_exit("  /exit\nthanks") and terminal.is_exit("/quit")
    assert not terminal.is_exit("I typed /exit already") and not terminal.is_exit("/exits")
    assert terminal.is_resume("/resume") and terminal.is_resume("/resume\nback") and not terminal.is_resume("resume")
    assert [terminal.start_mode(a) for a in ([], ["-c"], ["--resume"], ["-r", "abc"], ["--resume=xyz"], ["-r", "-c"])] \
        == ["new", "continue", "picker", "resume:abc", "resume:xyz", "picker"]


def test_picker():
    sessions = [{"id": "old", "first": "hi", "messages": 4, "last": 1000.0},
                {"id": "new", "first": "/setup", "messages": 14, "last": 1600.0}]
    screen = terminal.picker_screen(sessions, now=1720.0).splitlines()
    assert screen[1] == "❯ 1. /setup  ·  2 minutes ago  ·  14 messages" and screen[2].startswith("  2. hi")
    for typed, want in (("1", "new"), ("2", "old"), ("the setup one", "new"), ("/setup", "new"), ("hi", "old"),
                        ("", "new"), ("esc", None), ("9", "new")):
        assert terminal.parse_pick(typed, sessions) == want, typed
    assert "No conversations" in terminal.picker_screen([]) and terminal.parse_pick("1", []) is None


def test_stand_in(tmp_path):
    folder, fake = tmp_path / "term", tmp_path / "fakeclaude"
    fake.write_text(f"#!{PY}\nimport os, sys\nprint('REAL', sys.argv[1:], os.environ.get('CLAUDE_CONFIG_DIR'))\n")
    fake.chmod(0o755)
    script = terminal.write_stand_in(folder, python=PY, claude=str(fake), config_dir="/cfg/a", version="2.1.281")
    env = {**os.environ, "PATH": f"{script.parent}{os.pathsep}/usr/bin{os.pathsep}/bin"}
    out = subprocess.run(["claude", "mcp", "get", "cool-colab-mcp"], env=env, cwd=tmp_path, capture_output=True,
                         text=True).stdout
    assert out.strip() == "REAL ['mcp', 'get', 'cool-colab-mcp'] /cfg/a" and terminal.take_start(folder) is None
    # `cd <path> && claude --resume`, as typed in a new terminal window
    shown = subprocess.run(f'cd "{tmp_path}" && claude --resume', shell=True, env=env, capture_output=True,
                           text=True).stdout
    assert "Welcome to Claude Code" in shown and str(tmp_path) in shown
    req = terminal.take_start(folder)
    assert req["cwd"] == str(tmp_path) and req["args"] == ["--resume"] and str(script.parent) not in req["path"]
    assert terminal.take_start(folder) is None  # read once
    bad = subprocess.run(["claude", "update"], env=env, capture_output=True, text=True)
    assert bad.returncode == 1 and "not available" in bad.stderr


def test_local_github(tmp_path):
    root, exec_dir = tmp_path / "github", tmp_path / "git-core"
    env = {**os.environ, **github.install(exec_dir, root, python=PY)}
    src = tmp_path / "src"
    subprocess.run(["git", "init", "-q", "-b", "main", str(src)], check=True)
    subprocess.run(["git", "-C", str(src), "-c", "user.name=a", "-c", "user.email=a@b", "commit", "-q",
                    "--allow-empty", "-m", "one"], check=True)
    github.add_repo(root, "shilad", "comp440-hw2", src, push_denied_to="student")
    github.add_repo(root, "student", "comp440-hw2", src)

    def git(*args):
        return subprocess.run(["git", "-C", str(src), *args], env=env, capture_output=True, text=True)
    git("remote", "add", "origin", github.url("shilad", "comp440-hw2"))
    assert git("remote", "-v").stdout.split("\n")[0] == "origin\thttps://github.com/shilad/comp440-hw2 (fetch)"
    assert git("fetch", "origin").returncode == 0
    denied = git("push", "origin", "main")
    assert denied.returncode != 0 and "Permission to shilad/comp440-hw2.git denied to student" in denied.stderr
    git("remote", "set-url", "origin", github.url("student", "comp440-hw2"))
    git("commit", "--allow-empty", "-q", "-m", "two")
    assert git("push", "-q", "origin", "main").returncode == 0
    assert git("ls-remote", "https://github.com/nobody/nothing").returncode != 0
    assert github.local_path(root, "https://github.com/a/b.git/") == root / "a" / "b.git"


def test_scenarios():
    settings, presets = {"approve": "ask", "uv": "present"}, {"no-uv": {"uv": "missing"}}
    assert world.resolve_scenario(settings, presets, None) == {"names": [], "settings": settings}
    got = world.resolve_scenario(settings, presets, ["no-uv", "approve=decline"])
    assert got == {"names": ["no-uv", "approve=decline"], "settings": {"approve": "decline", "uv": "missing"}}
    for bad in (["nope"], ["colour=red"]):
        with pytest.raises(world.ScenarioError):
            world.resolve_scenario(settings, presets, bad)


def test_load_world(tmp_path):
    (tmp_path / "helper.py").write_text("VALUE = 7\n")
    (tmp_path / "w.py").write_text("import helper\nclass W:\n    def __init__(self, ctx): self.ctx = ctx\n"
                                   "    def tutor_env(self): return {'BROWSER': 'x', 'PATH': ['/a']}\n"
                                   "    async def start(self): self.ctx.log('started %d' % helper.VALUE)\n"
                                   "def make_world(ctx): return W(ctx)\n")
    logged = []
    ctx = world.Context(cfg=None, run_id="r", run_dir=tmp_path, workspace=tmp_path, repo=tmp_path, home=None,
                        tutor_config=None, settings={}, persona="p", log=logged.append, side_turn=None,
                        tutor_view=lambda: "", notify=None, tutor_busy=lambda: False)
    w = world.load_world(tmp_path / "w.py", ctx)
    asyncio.run(world.call(w, "start"))
    assert world.call(w, "tutor_env") == {"BROWSER": "x", "PATH": ["/a"]} and logged == ["started 7"]
    assert world.call(w, "student_tools", []) == [] and world.call(None, "facts") is None
