"""The run loop offline: a scripted student and a fake tutor go through the start-up question (declined), /exit, the
terminal (`claude mcp reset-project-choices` through the stand-in, then `cd <repo> && claude`), the question again
(approved), /resume and the picker, and a message to the reopened conversation. No model is called; the real CLI runs
only for `claude mcp reset-project-choices`, which needs no login."""
import json
import shutil
import subprocess
import uuid
from pathlib import Path

from claude_agent_sdk import AssistantMessage, ResultMessage, SystemMessage, TextBlock

from pilot import facts, run, terminal
from pilot.scripted import ScriptedStudent

HERE = Path(__file__).parent


class FakeTutor:
    made: list = []

    def __init__(self, opts):
        self.opts, self.n = opts, 0
        self.sid = opts.resume or str(uuid.uuid4())
        FakeTutor.made.append(self)

    async def connect(self):
        return None

    async def disconnect(self):
        return None

    async def interrupt(self):
        return None

    async def query(self, prompt):
        self.prompt = prompt

    async def receive_response(self):
        self.n += 1
        yield SystemMessage(subtype="init", data={"session_id": self.sid, "model": "fake", "mcp_servers": [],
                                                  "tools": ["Bash"]})
        yield AssistantMessage(content=[TextBlock(text=f"Tutor reply to: {self.prompt[:40]}")], model="fake",
                               session_id=self.sid)
        yield ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1,
                            session_id=self.sid, total_cost_usd=0.0, usage={}, model_usage={})


def _assignment(tmp_path) -> Path:
    tpl = tmp_path / "course" / "tpl"
    shutil.copytree(HERE / "toy" / "template", tpl)
    (tpl / ".mcp.json").write_text(json.dumps({"mcpServers": {"colab": {"command": "true"}}}))
    for args in (["init", "-q", "-b", "main"], ["add", "-A"],
                 ["-c", "user.name=t", "-c", "user.email=t@e", "commit", "-q", "-m", "tpl"]):
        subprocess.run(["git", "-C", str(tpl), *args], check=True)
    shutil.copytree(HERE / "toy" / "personas", tmp_path / "course" / "personas")
    (tmp_path / "course" / "pilot.toml").write_text(
        f'template = "tpl"\nwork_dir = "{tmp_path / "work"}"\ngate = ""\nrepo_name = "course-repo"\n'
        'run_home = true\nrestarts = true\napprove_servers = ["colab"]\ntutor_setting_sources = ["project", "local"]\n'
        'run_path = ["/usr/bin", "/bin"]\n')
    return tmp_path / "course"


def test_restart_flow(tmp_path):
    cfg = run.load_config(_assignment(tmp_path))
    FakeTutor.made = []
    repo_holder = {}

    def script(prompt, st):
        repo = repo_holder["repo"]
        if "New MCP server found in this project: colab" in prompt:
            first = "You typed `claude`" in prompt
            return [("say", "Continue without using this MCP server" if first else "Use this MCP server")]
        if "Resume a conversation" in prompt:
            return [("say", "1")]
        if prompt.startswith("You have just opened Claude Code"):
            return [("say", "hello")]
        if "Claude Code has closed" in prompt:
            return [("bash", "claude mcp reset-project-choices"), ("bash", f'cd "{repo}" && claude'), ("say", "")]
        if "in a new conversation" in prompt:
            return [("say", "/resume")]
        if "reopened that conversation" in prompt:
            return [("say", "back")]
        if "Tutor reply to: hello" in prompt:
            return [("say", "/exit")]
        return [("say", "thanks\n(leaves)")]

    def make_student(env, tools, cwd):
        repo_holder["repo"] = cwd
        return ScriptedStudent(script, env=env, tools=tools, cwd=cwd)

    out = run.run_one(cfg, "jordan", student=make_student, tutor=FakeTutor)
    data = json.loads((out / "run.json").read_text())
    repo = Path(data["repo"])
    assert repo.name == "course-repo" and data["ended_by"] == "left", data["error"]
    first, second = FakeTutor.made
    assert first.opts.resume is None and second.opts.resume == first.sid  # /resume reopened the first conversation
    assert str(Path(data["home"]) / ".local" / "bin") in second.opts.env["PATH"]
    assert "terminal" not in second.opts.env["PATH"]  # the stand-in is the student's, never the tutor's
    assert second.opts.env["HOME"] == data["home"] and second.opts.setting_sources == ["project", "local"]
    assert [(a["choice"], a["forced"]) for a in data["approvals"]] == [("no", False), ("yes", False)]
    assert terminal.server_choice(repo, "colab") == "yes"
    types = [r["type"] for r in data["restarts"]]
    assert types == ["exit", "start", "session"] and data["restarts"][2]["resumed"] == first.sid
    turns = facts.load_turns(out)
    kinds = [(t["actor"], t.get("kind", "message")) for t in turns]
    assert kinds == [("student", "approval"), ("student", "message"), ("tutor", "message"), ("student", "message"),
                     ("student", "terminal"), ("student", "approval"), ("student", "message"), ("student", "picker"),
                     ("student", "message"), ("tutor", "message"), ("student", "message")]
    term = turns[4]
    assert term["event"]["type"] == "start" and term["event"]["cwd"] == str(repo)
    assert "have been reset" in term["tools"][0]["result"] and "is open in this window" in term["tools"][1]["result"]
    f = facts.summarize(out, cfg)
    assert f["restarts"]["count"] == 1 and f["restarts"]["exits"] == [2] and f["terminal_turns"] == [3]
    assert f["student_words_median"] is not None and "at the terminal" in (out / "transcript.md").read_text()
    # the claude placed in the run's home is the bundled CLI, reached without any path that names the library
    claude = Path(data["home"]) / ".local" / "bin" / "claude"
    assert claude.is_symlink() and "pilot" not in str(claude.resolve()).lower()
