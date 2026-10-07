"""Scenarios and the assignment's world module: the small interface an assignment uses to add to a run what the
library cannot know (a browser, a stand-in web page, files the tutor's tools expect on the laptop).

pilot.toml names the module with `world = "world/world.py"` (relative to the assignment directory). The module
defines `make_world(ctx)` and returns an object; every method on it is optional:

    tutor_env() -> dict          extra environment for the tutor and the servers it starts; a list value for PATH
                                 is a list of folders put in front of the tutor's PATH
    student_tools() -> list      tools made with claude_agent_sdk.tool, served to the student as the `laptop` server
    student_note() -> str        a paragraph added to the student's frame (what else is open on their screen)
    async start()                after the workspace exists, before either session starts
    async stop()                 at the end of the run, before the gate
    facts() -> dict              saved in run.json under "world"

`ctx` (a Context) gives the world the run's paths and settings, a log, the tutor's reply so far, a way to run a
student turn while the tutor is working (`side_turn`), and a way to put a line on the student's screen before
their next message (`notify`). RECORDS.md lists the fields."""
from __future__ import annotations

import hashlib, importlib.util, sys  # noqa: E401
from pathlib import Path


class ScenarioError(ValueError):
    """--scenario named a setting or a preset that pilot.toml does not define."""


def resolve_scenario(settings: dict, presets: dict, picks: list[str] | None) -> dict:
    """The run's settings: pilot.toml's `[settings]` defaults, then each pick in order. A pick is `key=value` (one
    setting) or the name of a `[scenarios.<name>]` table (several settings at once)."""
    out, names = {k: str(v) for k, v in (settings or {}).items()}, []
    for pick in picks or []:
        if "=" in pick:
            key, value = (s.strip() for s in pick.split("=", 1))
            if key not in out:
                raise ScenarioError(f"--scenario {pick}: no setting named {key}; pilot.toml [settings] has "
                                    f"{', '.join(sorted(out)) or 'none'}")
            out[key] = value
            names.append(f"{key}={value}")
        elif isinstance((presets or {}).get(pick), dict):
            if unknown := sorted(set(presets[pick]) - set(out)):
                raise ScenarioError(f"[scenarios.{pick}] sets {', '.join(unknown)}, which [settings] does not define")
            out.update({k: str(v) for k, v in presets[pick].items()})
            names.append(pick)
        else:
            raise ScenarioError(f"--scenario {pick}: no preset named {pick} in pilot.toml [scenarios]")
    return {"names": names, "settings": out}


class Context:
    """What the library hands the world module. Paths are absolute; `home` is the run's home folder or None."""

    def __init__(self, *, cfg, run_id: str, run_dir: Path, workspace: Path, repo: Path, home: Path | None,
                 tutor_config: Path | None, settings: dict, persona: str, log, side_turn, tutor_view, notify,
                 tutor_busy):
        self.cfg, self.run_id, self.run_dir, self.workspace, self.repo = cfg, run_id, run_dir, workspace, repo
        self.home, self.tutor_config, self.settings, self.persona = home, tutor_config, settings, persona
        self._log, self._side, self._view, self._notify, self._busy = log, side_turn, tutor_view, notify, tutor_busy

    def log(self, text: str) -> None:
        """One line in run.log, marked [world]."""
        self._log(text)

    def tutor_text(self) -> str:
        """The tutor's reply so far in the turn in progress, as the student's terminal shows it; "" between turns."""
        return self._view()

    def tutor_busy(self) -> bool:
        return self._busy()

    async def side_turn(self, prompt: str, label: str) -> dict:
        """Run one student turn now, while the tutor works, and record it (kind "side", with `label`). What the
        student writes is not sent to the tutor. Returns the recorded turn (its text, tools, seconds)."""
        return await self._side(prompt, label)

    def notify(self, text: str) -> None:
        """Show `text` at the top of the student's next prompt (a screen they will see when they next look)."""
        self._notify(text)


def load_world(path: Path, ctx: Context):
    """Import the world module at `path` and return make_world(ctx)."""
    name = "pilot_world_" + hashlib.sha256(str(path).encode()).hexdigest()[:8]
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import the world module {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    sys.path.insert(0, str(path.parent))  # so the module can import its neighbours
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(path.parent))
    if not callable(getattr(module, "make_world", None)):
        raise ImportError(f"{path} defines no make_world(ctx)")
    return module.make_world(ctx)


def call(world, method: str, default=None):
    """world.method() when the world defines it, else default."""
    fn = getattr(world, method, None) if world is not None else None
    return fn() if callable(fn) else default
