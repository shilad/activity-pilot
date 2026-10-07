"""A student that follows a script instead of a model, for probes and for testing an assignment's world without paying
for a student. It looks like a ClaudeSDKClient to the run loop: `query` takes the prompt the student would see and
`receive_response` yields the same message types a model's session does.

A script is a function `script(prompt, student) -> list of actions` (or a coroutine returning one):

    ("say", text)            the message typed (put it last: text before a tool call is narration)
    ("bash", command)        run in the student's terminal (their environment, the repo as working folder)
    ("tool", name, args)     call one of the world's student tools, e.g. ("tool", "chrome_click", {"what": "Connect"})
    ("wait", seconds)        let time pass

`student.prompts` keeps every prompt it was shown; `student.results` every tool output."""
from __future__ import annotations

import asyncio, inspect, itertools, subprocess, time  # noqa: E401
from pathlib import Path

from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock, ToolResultBlock, ToolUseBlock, UserMessage

MODEL = "scripted"


class ScriptedStudent:
    def __init__(self, script, *, env: dict, cwd: Path, tools: dict):
        self.script, self.env, self.cwd, self.tools = script, env, Path(cwd), tools
        self.prompts: list[str] = []
        self.results: list[str] = []
        self._ids = itertools.count(1)
        self._prompt = ""

    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        return None

    async def interrupt(self) -> None:
        return None

    async def query(self, prompt: str) -> None:
        self._prompt = prompt
        self.prompts.append(prompt)

    async def _run(self, action) -> tuple[str, dict, str, bool]:
        kind = action[0]
        if kind == "bash":
            p = await asyncio.to_thread(subprocess.run, action[1], shell=True, cwd=self.cwd, env=self.env, text=True,
                                        capture_output=True, stdin=subprocess.DEVNULL, timeout=600)
            return "Bash", {"command": action[1]}, (p.stdout + p.stderr).strip(), p.returncode != 0
        if kind == "tool":
            name, args = action[1], action[2] if len(action) > 2 else {}
            out = await self.tools[name].handler(args)
            text = "\n".join(c.get("text", "") for c in out.get("content", []) if isinstance(c, dict))
            return f"mcp__laptop__{name}", args, text, bool(out.get("is_error"))
        raise ValueError(f"unknown scripted action {action!r}")

    async def receive_response(self):
        t0 = time.monotonic()
        actions = self.script(self._prompt, self)
        actions = await actions if inspect.isawaitable(actions) else actions
        for action in actions or []:
            if action[0] == "say":
                yield AssistantMessage(content=[TextBlock(text=action[1])], model=MODEL)
            elif action[0] == "wait":
                await asyncio.sleep(action[1])
            else:
                tid = f"scripted-{next(self._ids)}"
                name, args, text, err = await self._run(action)
                self.results.append(text)
                yield AssistantMessage(content=[ToolUseBlock(id=tid, name=name, input=args)], model=MODEL)
                yield UserMessage(content=[ToolResultBlock(tool_use_id=tid, content=text, is_error=err)])
        yield ResultMessage(subtype="success", duration_ms=int((time.monotonic() - t0) * 1000), duration_api_ms=0,
                            is_error=False, num_turns=1, session_id="scripted", total_cost_usd=0.0, usage={},
                            model_usage={})
