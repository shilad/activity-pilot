"""The `pilot` command: run, read, report, view, calibrate. The assignment directory always comes first."""
import argparse
import asyncio
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="pilot", description="Run a simulated student against an assignment template.")
    sub = p.add_subparsers(dest="command", required=True)
    helps = {"run": "run one persona against the template; prints the run directory",
             "read": "have the reader grade one run; prints scorecard.md", "report": "print one table over every run",
             "view": "write runs/viewer.html over every run", "calibrate": "write a blank grading sheet for one run"}
    cmd = {name: sub.add_parser(name, help=text) for name, text in helps.items()}
    for sp in cmd.values():
        sp.add_argument("assignment_dir", type=Path, help="the directory holding pilot.toml")
    cmd["run"].add_argument("persona", help="the persona sheet's name, personas/<persona>.md")
    cmd["run"].add_argument("--repo", type=Path, help="work in this existing repo instead of a fresh template copy")
    cmd["run"].add_argument("--turns", type=int, help="stop after this many exchanges (default: max_turns)")
    cmd["run"].add_argument("--scenario", action="append", default=[], metavar="NAME|KEY=VALUE",
                            help="a preset from pilot.toml [scenarios], or one setting; repeat for more")
    for name in ("read", "calibrate"):
        cmd[name].add_argument("run_id", help="a directory under runs/")
    cmd["calibrate"].add_argument("--initials", required=True, help="the grader's initials, as in sheet-XX.md")
    a = p.parse_args(argv)

    from .run import ConfigError, load_config  # every other module loads only when its command runs
    try:
        cfg = load_config(a.assignment_dir)
        if a.command == "run":
            from .run import run_one
            out = run_one(cfg, a.persona, repo=a.repo, turns=a.turns, scenario=a.scenario)
            print(out)
            return 0 if json.loads((out / "run.json").read_text(encoding="utf-8"))["status"] == "finished" else 1
        if a.command == "report":
            from . import facts
            out = facts.report(cfg)
        elif a.command == "view":
            from . import viewer
            out = viewer.build(cfg)
        elif a.command == "read":
            from . import reader
            out = asyncio.run(reader.read(cfg.runs_dir / a.run_id, cfg))
        else:
            from . import facts
            out = facts.sheet(cfg.runs_dir / a.run_id, cfg, a.initials)
    except (ConfigError, ImportError) as e:  # ImportError: that command's module is not written yet
        print(f"pilot: {e}", file=sys.stderr)
        return 2
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
