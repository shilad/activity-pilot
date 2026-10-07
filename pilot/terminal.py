"""Claude Code's own screens that a headless tutor never shows, acted out for the student: the start-up question for
a new project MCP server, the terminal after `/exit`, the `claude` command that starts Claude Code again, and the
`/resume` picker. Pure functions and one small script, so each piece is tested offline.

Wording comes from the strings in the bundled CLI (2.1.281) where it could be found there; each screen says
where its text comes from."""
from __future__ import annotations

import json, os, re, time  # noqa: E401
from pathlib import Path

# The start-up question for one new .mcp.json server, from CLI 2.1.281 (its dialog component's strings): the title,
# the body, and the three options in order. The highlighted option when the dialog opens is the third ("no"), and
# Esc also picks it, so a student who presses Enter without reading declines the server.
APPROVAL_TITLE = "New MCP server found in this project: {name}"
APPROVAL_BODY = ("MCP servers may execute code or access system resources. All tool calls require approval. "
                 "Learn more in the MCP documentation.")
APPROVAL_OPTIONS = (("yes", "Use this MCP server"), ("yes_all", "Use this and all future MCP servers in this project"),
                    ("no", "Continue without using this MCP server"))
APPROVAL_DEFAULT = "no"
APPROVAL_HOW = "(Type the option you pick. Pressing Enter without picking one takes the highlighted option.)"
EXIT_COMMANDS = ("/exit", "/quit")  # both close the CLI
RESUME_COMMAND = "/resume"
STAND_IN_PASSTHROUGH = ("mcp", "-v", "--version", "-h", "--help")  # handed to the real CLI with the tutor's settings
STATE_FILE = "start.json"  # written by the stand-in when the student starts Claude Code


def settings_path(repo: Path) -> Path:
    """Where the CLI keeps a project's approvals: localSettings, `<repo>/.claude/settings.local.json`."""
    return Path(repo) / ".claude" / "settings.local.json"


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def project_servers(repo: Path) -> list[str]:
    return list((_read(Path(repo) / ".mcp.json").get("mcpServers") or {}))


def server_choice(repo: Path, name: str) -> str | None:
    """'yes' (approved), 'no' (rejected) or None (pending), from the project's and the local settings."""
    for path in (settings_path(repo), Path(repo) / ".claude" / "settings.json"):
        data = _read(path)
        if name in (data.get("disabledMcpjsonServers") or []):
            return "no"
        if name in (data.get("enabledMcpjsonServers") or []) or data.get("enableAllProjectMcpServers") is True:
            return "yes"
    return None


def pending(repo: Path, names) -> list[str]:
    """The servers among `names` that are in .mcp.json and neither approved nor rejected: the CLI asks about these."""
    return [n for n in names if n in project_servers(repo) and server_choice(repo, n) is None]


def apply_choice(repo: Path, name: str, choice: str) -> None:
    """Write the choice the way the CLI's dialog does: yes adds the name to enabledMcpjsonServers, yes_all also sets
    enableAllProjectMcpServers, no adds it to disabledMcpjsonServers, each in the local settings file."""
    path = settings_path(repo)
    data = _read(path)
    key = "disabledMcpjsonServers" if choice == "no" else "enabledMcpjsonServers"
    if name not in (data.get(key) or []):
        data[key] = [*(data.get(key) or []), name]
    if choice == "yes_all":
        data["enableAllProjectMcpServers"] = True
    path.parent.mkdir(parents=True, exist_ok=True)
    (tmp := path.with_name(path.name + ".tmp")).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def approval_screen(name: str) -> str:
    """The dialog as the terminal shows it, the highlighted option marked with ❯."""
    rows = [("❯ " if value == APPROVAL_DEFAULT else "  ") + label for value, label in APPROVAL_OPTIONS]
    return "\n".join([APPROVAL_TITLE.format(name=name), APPROVAL_BODY, "", *rows, "", APPROVAL_HOW])


def parse_approval(text: str) -> str:
    """The option a typed reply picks: a label (or its first words), a number, or a plain yes/no. Anything else is
    Enter on the highlighted option, which is no."""
    t = " ".join(text.lower().replace("❯", " ").split()).strip(" .!*`\"'")
    if not t:
        return APPROVAL_DEFAULT
    if "all future" in t or t in ("2", "2.", "yes all", "yes_all"):
        return "yes_all"
    if "continue without" in t or "without using" in t or t in ("3", "3.", "no", "n", "decline", "skip", "esc"):
        return "no"
    if t.startswith(("use this", "1", "yes", "y ", "approve", "use it", "use the")) or t in ("y", "ok", "sure"):
        return "yes"
    return APPROVAL_DEFAULT


def is_exit(text: str) -> bool:
    """The student typed /exit (or /quit) alone or as the first line of their message."""
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return first.split(" ")[0].lower() in EXIT_COMMANDS


def is_resume(text: str) -> bool:
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return first.split(" ")[0].lower() == RESUME_COMMAND


def picker_screen(sessions: list[dict], now: float | None = None) -> str:
    """The /resume list: newest first, one line each with its first message, age and message count. A paraphrase
    of CLI 2.1.281's picker, whose exact columns could not be read from the binary."""
    now = time.time() if now is None else now
    rows = []
    for i, s in enumerate(sorted(sessions, key=lambda s: -s["last"]), 1):
        mins = max(0, round((now - s["last"]) / 60))
        age = "just now" if mins < 1 else f"{mins} minute{'s' * (mins != 1)} ago" if mins < 60 else \
            f"{mins // 60} hour{'s' * (mins // 60 != 1)} ago"
        first = " ".join(str(s["first"]).split())[:60] or "(no prompt)"
        rows.append(f"{'❯' if i == 1 else ' '} {i}. {first}  ·  {age}  ·  {s['messages']} messages")
    if not rows:
        return "Resume a conversation\nNo conversations found in this folder.\n(Press Esc to go back.)"
    return "\n".join(["Resume a conversation", *rows, "", "(Type the number of the conversation you pick. "
                                                       "Enter takes the highlighted one; Esc goes back.)"])


def parse_pick(text: str, sessions: list[dict]) -> str | None:
    """The session id a reply picks, or None for Esc. Newest first, as on the screen."""
    order = sorted(sessions, key=lambda s: -s["last"])
    t = text.strip().lower()
    if not order or t in ("esc", "escape", "none", "back", "cancel", "no"):
        return None
    if m := re.match(r"^\D*?(\d+)", t):
        n = int(m.group(1))
        return order[n - 1]["id"] if 1 <= n <= len(order) else order[0]["id"]
    for s in order:
        if t and t[:20] in " ".join(str(s["first"]).lower().split()):
            return s["id"]
    return order[0]["id"]  # Enter on the highlighted (newest) conversation


STAND_IN = '''#!{python}
"""claude: start Claude Code in this folder, or run one of its commands."""
import json, os, sys, time

CLAUDE = {claude!r}
SETTINGS = {config!r}
STATE = {state!r}
VERSION = {version!r}
here = os.path.dirname(os.path.abspath(__file__))
path = os.pathsep.join(p for p in os.environ.get("PATH", "").split(os.pathsep) if p and p != here)
args = sys.argv[1:]
if args and args[0] in {passthrough!r}:
    env = dict(os.environ, PATH=path, **({{"CLAUDE_CONFIG_DIR": SETTINGS}} if SETTINGS else {{}}))
    os.execve(CLAUDE, [CLAUDE, *args], env)
if args and not args[0].startswith("-"):
    print(f"claude: {{args[0]}} is not available right now.", file=sys.stderr)
    sys.exit(1)
request = {{"cwd": os.getcwd(), "args": args, "path": path, "time": time.time()}}
tmp = os.path.join(STATE, "start.tmp")
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(request, f)
os.replace(tmp, os.path.join(STATE, "start.json"))
width = max(48, len(os.getcwd()) + 12)
print("╭" + "─" * width + "╮")
for line in ("✻ Welcome to Claude Code!", "", "/help for help, /status for your current setup", "",
             "cwd: " + os.getcwd()):
    print("│ " + line.ljust(width - 2) + " │")
print("╰" + "─" * width + "╯")
print("Claude Code " + VERSION + " is open in this window.")
'''


def write_stand_in(folder: Path, *, python: str, claude: str, config_dir: str, version: str) -> Path:
    """The `claude` the student's terminal runs. `claude mcp ...` and --version/--help go to the real CLI with the
    tutor's settings folder; any other subcommand is refused; a bare `claude` (with flags such as --resume) writes
    a start request to `folder/state/start.json` for the run loop and prints the welcome box."""
    state = Path(folder) / "state"
    state.mkdir(parents=True, exist_ok=True)
    script = Path(folder) / "bin" / "claude"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(STAND_IN.format(python=python, claude=claude, config=config_dir, state=str(state),
                                      version=version or "", passthrough=STAND_IN_PASSTHROUGH), encoding="utf-8")
    script.chmod(0o755)
    return script


def take_start(folder: Path) -> dict | None:
    """The start request the stand-in left, removed so it is read once; None when the student did not start it."""
    path = Path(folder) / "state" / STATE_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    path.rename(path.with_name(f"start-{time.time_ns()}.json"))  # kept for the record
    return data if isinstance(data, dict) else None


def start_mode(args: list[str]) -> str:
    """How a `claude` command line starts: 'continue' (-c), 'picker' (--resume or -r without an id), 'resume:<id>',
    or 'new'."""
    for i, a in enumerate(args):
        if a in ("-c", "--continue"):
            return "continue"
        if a in ("-r", "--resume") or a.startswith("--resume="):
            value = a.split("=", 1)[1] if "=" in a else (args[i + 1] if i + 1 < len(args) and
                                                          not args[i + 1].startswith("-") else "")
            return f"resume:{value}" if value else "picker"
    return "new"
