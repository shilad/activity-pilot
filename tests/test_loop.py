"""The run loop offline: a scripted student and a fake tutor go through the start-up question (declined), /exit, the
terminal (`claude mcp reset-project-choices` through the stand-in, then `cd <repo> && claude`), the question again
(approved), /resume and the picker, and a message to the reopened conversation. No model is called; the real CLI runs
only for `claude mcp reset-project-choices`, which needs no login."""
import asyncio
import json
import re
import shutil
import subprocess
import uuid
from pathlib import Path

from claude_agent_sdk import (AssistantMessage, ResultMessage, SystemMessage, TaskNotificationMessage, TaskStartedMessage,
                              TextBlock)

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
                     ("student", "message"), ("tutor", "message"), ("student", "message"), ("tutor", "message")]
    assert turns[-1]["stop"] == "left" and FakeTutor.made[1].prompt == "thanks"  # the last words still got a reply
    term = turns[4]
    assert term["event"]["type"] == "start" and term["event"]["cwd"] == str(repo)
    assert "have been reset" in term["tools"][0]["result"] and "is open in this window" in term["tools"][1]["result"]
    f = facts.summarize(out, cfg)
    assert f["restarts"]["count"] == 1 and f["restarts"]["exits"] == [2] and f["terminal_turns"] == [3]
    assert f["student_words_median"] is not None and "at the terminal" in (out / "transcript.md").read_text()
    # the claude placed in the run's home is the bundled CLI, reached without any path that names the library
    claude = Path(data["home"]) / ".local" / "bin" / "claude"
    assert claude.is_symlink() and "pilot" not in str(claude.resolve()).lower()


class QueueTutor(FakeTutor):
    """A tutor whose first reply is still running when the world starts a side turn; a message queued meanwhile is
    answered right after that reply, as the CLI does when it cannot absorb it mid-reply."""
    hook = None

    async def query(self, prompt):
        self.queue = getattr(self, "queue", []) + [prompt]

    async def receive_response(self):
        prompt = self.queue.pop(0)
        self.prompt = prompt
        yield AssistantMessage(content=[TextBlock(text=f"Working on: {prompt[:30]}")], model="fake",
                               session_id=self.sid)
        if prompt == "open the tab" and QueueTutor.hook:
            await QueueTutor.hook()
        yield ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1,
                            session_id=self.sid, total_cost_usd=0.0, usage={}, model_usage={})


def test_typed_while_working_reaches_the_tutor(tmp_path):
    adir = _assignment(tmp_path)
    (adir / "w.py").write_text("CTX = {}\ndef make_world(ctx):\n    CTX['ctx'] = ctx\n    return object()\n")
    toml = (adir / "pilot.toml").read_text().replace('approve_servers = ["colab"]\n', "") + 'world = "w.py"\n'
    (adir / "pilot.toml").write_text(toml.replace("restarts = true\n", ""))
    cfg = run.load_config(adir)

    def script(prompt, st):
        if prompt.startswith("You have just opened"):
            return [("say", "open the tab")]
        if prompt.startswith("(side)"):
            return [("say", "wait, is Connect safe?")]
        return [("say", "ok\n(leaves)")]

    async def hook():
        import sys
        ctx = sys.modules[[m for m in sys.modules if m.startswith("pilot_world_")][-1]].CTX["ctx"]
        assert ctx.tutor_busy() and "Working on: open the tab" in ctx.tutor_text()
        await ctx.side_turn("(side) a tab opened", "test")
    QueueTutor.hook = hook
    out = run.run_one(cfg, "jordan", tutor=QueueTutor,
                      student=lambda env, tools, cwd: ScriptedStudent(script, env=env, tools=tools, cwd=cwd))
    turns = facts.load_turns(out)
    side = next(t for t in turns if t.get("kind") == "side")
    tutor1 = next(t for t in turns if t["actor"] == "tutor")
    assert side["sent"] == "queued" and tutor1["queued"][0]["text"] == "wait, is Connect safe?"
    assert "Working on: wait, is Connect safe?" in tutor1["text"]  # answered within the same exchange
    assert "[typed while Claude worked] wait, is Connect safe?" in (out / "transcript.md").read_text()


def test_from_run_copies_and_rewrites(tmp_path):
    cfg = run.load_config(_assignment(tmp_path))
    first = run.run_one(cfg, "jordan", tutor=FakeTutor, student=lambda env, tools, cwd: ScriptedStudent(
        lambda p, st: [("say", "Use this MCP server" if "New MCP" in p else "bye\n(leaves)")], env=env, tools=tools,
        cwd=cwd))
    old = json.loads((first / "run.json").read_text())
    old_ws, old_repo = Path(old["workspace"]), Path(old["repo"])
    old_a = Path(old["config_dirs"]["tutor"])
    session_dir = old_a / "projects" / run.munged(old_repo)
    session_dir.mkdir(parents=True)
    (session_dir / "s1.jsonl").write_text(json.dumps({"type": "user", "cwd": str(old_repo)}) + "\n")
    second = run.run_one(cfg, "jordan", from_run=old_ws.name, tutor=FakeTutor, student=lambda env, tools, cwd:
                         ScriptedStudent(lambda p, st: [("say", "bye\n(leaves)")], env=env, tools=tools, cwd=cwd))
    new = json.loads((second / "run.json").read_text())
    new_repo, new_a = Path(new["repo"]), Path(new["config_dirs"]["tutor"])
    assert new["from_run"]["run"] == old_ws.name and new_repo != old_repo and new_repo.is_dir()
    assert str(new_repo) in json.loads((new_a / ".claude.json").read_text())["projects"]
    moved = new_a / "projects" / run.munged(new_repo) / "s1.jsonl"
    assert json.loads(moved.read_text())["cwd"] == str(new_repo)
    assert terminal.server_choice(new_repo, "colab") == "yes"  # the approval carried over: no question this time
    assert not any(t.get("kind") == "approval" for t in facts.load_turns(second))
    claude = Path(new["home"]) / ".local" / "bin" / "claude"
    assert str(claude.resolve()).startswith(new["home"])  # points into the new home, not the old one
    assert json.loads((session_dir / "s1.jsonl").read_text())["cwd"] == str(old_repo)  # the old run is untouched
    for path in Path(new["workspace"]).rglob("*"):
        if path.is_file() and "objects" not in path.parts and path.stat().st_size < run.LINK_BYTES:
            try:
                assert not re.search(re.escape(str(old_ws)) + r"(?![\w-])", path.read_text()), path
            except UnicodeDecodeError:
                pass


class StreamTutor:
    """A tutor on one message stream, like the CLI's: its first reply starts a background task and ends; the
    task's end arrives a moment later, and Claude carries on alone with one more reply."""

    def __init__(self, opts):
        self.opts, self.q, self.sid = opts, asyncio.Queue(), "s-bg"

    async def connect(self):
        return None

    async def disconnect(self):
        return None

    async def interrupt(self):
        return None

    def _result(self):
        return ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1,
                             session_id=self.sid, total_cost_usd=0.0, usage={}, model_usage={})

    async def query(self, prompt):
        if prompt.startswith("grade"):
            await self.q.put(TaskStartedMessage(subtype="task_started", data={}, task_id="t1",
                                                description="Grade batch 01", uuid="u1", session_id=self.sid))
            await self.q.put(AssistantMessage(content=[TextBlock(text="The graders are running.")], model="fake"))
            await self.q.put(self._result())

            async def later():
                await asyncio.sleep(1.5)
                await self.q.put(TaskNotificationMessage(subtype="task_notification", data={}, task_id="t1",
                                                         status="completed", output_file="", summary="done",
                                                         uuid="u2", session_id=self.sid))
                await self.q.put(AssistantMessage(content=[TextBlock(text="All graders finished.")], model="fake"))
                await self.q.put(self._result())
            asyncio.get_running_loop().create_task(later())
        else:
            await self.q.put(AssistantMessage(content=[TextBlock(text=f"Reply to {prompt}")], model="fake"))
            await self.q.put(self._result())

    async def receive_messages(self):
        while True:
            yield await self.q.get()

    async def receive_response(self):
        async for m in self.receive_messages():
            yield m
            if isinstance(m, ResultMessage):
                return


def test_background_work_finishes_inside_the_reply(tmp_path):
    adir = _assignment(tmp_path)
    toml = (adir / "pilot.toml").read_text().replace('approve_servers = ["colab"]\n', "").replace("restarts = true\n",
                                                                                                    "")
    (adir / "pilot.toml").write_text(toml)
    cfg = run.load_config(adir)
    msgs = iter(["grade it", "thanks\n(leaves)"])
    out = run.run_one(cfg, "jordan", tutor=StreamTutor, student=lambda env, tools, cwd: ScriptedStudent(
        lambda p, st: [("say", next(msgs))], env=env, tools=tools, cwd=cwd))
    turns = [t for t in facts.load_turns(out) if t["actor"] == "tutor"]
    assert "The graders are running." in turns[0]["text"] and "All graders finished." in turns[0]["text"]
    assert turns[0]["background"]["started"] == ["Grade batch 01"] and turns[0]["background"]["waited_s"] >= 1
    assert turns[1]["text"] == "Reply to thanks"  # the next reply is not mixed up with the earlier one
