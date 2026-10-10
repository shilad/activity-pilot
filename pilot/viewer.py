"""Build runs/viewer.html: one self-contained page over every run directory in runs/.

A rail lists the runs, newest first, each marked ✓ (it ended because the finish string was seen), ✗ (it ended any
other way) or ? (no ending was recorded). One run shows at a time: a strip of labelled facts, then the tabs in TABS.
The page reads the records in the shapes RECORDS.md gives. A run without facts.json is summarized the way `pilot
report` does it; any other missing file loses its block, never the page. Every string from the records is escaped.
Standard library only: one inline script, nothing loaded over the network, and without JavaScript the first run's
conversation shows.
"""
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from . import inventory
from .facts import TRANSCRIPT_TAIL_LINES, WINDOW_USD, summarize

# The tabs under each run, in order: key, label, and the line under the tab bar that says what the tab holds.
TABS = (
    ("conversation", "Conversation", "Every exchange in order: the student's message, then the tutor's reply."),
    ("outcome", "Outcome", "What the gate said at the end, which writeup slots each side filled, and the commits."),
    ("scorecard", "Scorecard", "The reader's grades for the tutor, worst first. The reader is a separate Claude that "
                               "reads the finished run against rubric.md (pilot read)."),
    ("student", "The student", "Who the simulated student was meant to be, and how closely it kept to that."),
    ("facts", "Session facts", "Every field of facts.json and run.json, under the names RECORDS.md gives them."),
)
# ended_by (RECORDS.md) in plain words, finishing the sentence "The run ended because ...".
ENDED_BY = {
    "finished": "the finish string was seen",
    "left": "the student left",
    "max_turns": "the exchange budget ran out",
    "budget": "the cost limit was reached",
    "timeout": "a turn ran past its time limit",
    "error": "an error stopped it",
    "student_silent": "the student sent an empty message",
    "student_loop": "one student turn ran past its step limit",
    "killed": "it was stopped by hand",
    "crashed": "it stopped without recording an ending",
}
# A student turn that is not a message to Claude carries a kind; its header names it.
KIND = {"approval": "start-up question", "terminal": "at the terminal", "picker": "resume picker",
        "side": "while Claude works"}
# Tones (the .tone-* classes) colour the finish marks, the grades, the command flags and the placements alike.
MARKS = {"✓": ("good", "yes"), "✗": ("bad", "no"), "?": ("quiet", "not recorded")}
GRADES = {"I": "bad", "P": "warn", "C": "good", "n/o": "quiet"}  # worst first, the order of the scorecard rows
COMMANDS = {False: ("did", "info"), True: ("failed", "bad")}  # a student's command, by its is_error
PLACEMENTS = dict(zip(inventory.PLACEMENTS, ("good", "warn", "bad", "quiet")))  # solid, shaky, wrong, never
GRADE_LEGEND = ("C: the tutor did what the item asks each time it came up. P: partly, late, or only after the student "
                "pushed. I: the item came up and the tutor did not do it. n/o: this run could not have exercised it.")
FIDELITY = {"hold": "the student behaved as its sheet says",
            "drifted": "student-side findings can be quoted, with the lapses named",
            "broke": "do not quote this run for anything the student did"}
# facts.json fields that, when not empty, make a run less than the session it was meant to be.
ALARMS = (("student_wrote_tutor_side", "The simulated student wrote the tutor's side of the conversation"),
          ("tutor_left_repo", "The tutor worked outside the repository"),
          ("suspicion", "The tutor wrote something suggesting it guessed it was being tested"),
          ("student_saw_rules", "The student opened the tutor's rule files"))
STUDENT_FACTS = (("Median words per student message", "student_words_median"),
                 ("Commands the student ran in its own terminal", "student_bash"),
                 ("Student attempts the file policy refused", "student_denied"),
                 ("Empty student messages", "empty_student_turns"))
SIDES = ("tutor", "student")
# The input field that names what a tool call acted on, tried in this order.
TARGET_KEYS = ("command", "file_path", "notebook_path", "path", "pattern", "url", "query", "skill", "description")
# turns.jsonl fields the conversation shows. fabrication stays in each turn's record: when it did not fire, it
# appears nowhere else.
SHOWN = {"exchange", "actor", "kind", "text", "narration", "tools", "prompts", "asks", "hooks", "event", "stop",
         "commits", "files_changed"}
SHEET_NAME = re.compile(r"#\s+(.+?)\s*(<[^>]*>)?\s*$")  # a sheet's first line: # Name <email>
HEADING = re.compile(r"(#{1,6})\s+(.*)")
LIST_ITEM = re.compile(r"([-*+]|\d+[.)])\s+(.*)")


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _read_json(path: Path, notes: list[str]) -> dict:
    """A JSON object, or {} when the file is missing; a file that is not a JSON object is noted and read as {}."""
    raw = _read_text(path)
    if raw is None:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        data = None
    if not isinstance(data, dict):
        notes.append(f"{path.name} is not a JSON object and was ignored.")
        return {}
    return data


def _read_turns(path: Path, notes: list[str]) -> list[dict]:
    """turns.jsonl line by line; a line that does not parse (a crash can cut the last one) is counted and skipped."""
    turns, bad = [], 0
    for line in (_read_text(path) or "").splitlines():
        if not line.strip():
            continue
        try:
            turn = json.loads(line)
        except ValueError:
            turn = None
        if isinstance(turn, dict):
            turns.append(turn)
        else:
            bad += 1
    if bad:
        notes.append(f"Skipped {bad} malformed line{'s' * (bad > 1)} in turns.jsonl.")
    return turns


def _load(run_dir: Path, cfg, assignment: Path) -> dict:
    """One run directory as the page needs it."""
    notes: list[str] = []
    r = {"id": run_dir.name, "notes": notes, "turns": None, "summarized": False,
         "run": _read_json(run_dir / "run.json", notes), "facts": _read_json(run_dir / "facts.json", notes),
         "card": _read_json(run_dir / "scorecard.json", notes), "card_md": _read_text(run_dir / "scorecard.md"),
         "gate": _read_text(run_dir / "gate.txt")}
    if (run_dir / "turns.jsonl").exists():
        r["turns"] = _read_turns(run_dir / "turns.jsonl", notes)
        if not r["facts"]:
            r["facts"] = _summarize(run_dir, cfg, notes)
            r["summarized"] = bool(r["facts"])
    r["persona"] = str(r["run"].get("persona") or r["facts"].get("persona") or "")
    r["sheet"], r["sheet_from"], r["sheet_changed"] = _sheet(run_dir, r, assignment)
    first_line = SHEET_NAME.match((r["sheet"] or "").split("\n", 1)[0])
    r["name"] = (first_line[1] if first_line else "") or r["run"].get("student_name") or r["persona"]
    return r


def _summarize(run_dir: Path, cfg, notes: list[str]) -> dict:
    """facts.json is written last, so a run cut short has none; compute it as `pilot report` does."""
    try:
        return summarize(run_dir, cfg)
    except Exception as error:  # one bad record must not lose the page, as in pilot report
        notes.append(f"No facts.json, and the records could not be summarized: {type(error).__name__}: {error}")
        return {}


def _sheet(run_dir: Path, r: dict, assignment: Path) -> tuple[str | None, str, bool]:
    """The sheet the run was given (persona.md), else the current personas/<key>.md, and whether persona.md differs
    from the sha256 run.json recorded when the run started."""
    own = run_dir / "persona.md"
    text = _read_text(own)
    if text is not None:
        recorded = r["run"].get("persona_sha256")
        changed = bool(recorded) and hashlib.sha256(own.read_bytes()).hexdigest() != recorded
        return text, f"runs/{r['id']}/persona.md", changed
    key = r["persona"]
    return (_read_text(assignment / "personas" / f"{key}.md") if key else None), f"personas/{key}.md", False


def _e(value) -> str:
    """Record text, escaped; None is empty."""
    return escape("" if value is None else str(value))


def _slug(value) -> str:
    """A value made safe for an id."""
    return re.sub(r"[^A-Za-z0-9_-]", "-", str(value))


def _details(summary: str, body: str, kind: str = "more", opened: bool = False) -> str:
    """A disclosure; summary and body are HTML. A "block" is a section of a tab, open; a "more" is closed."""
    return f'<details class="{kind}"{" open" if opened else ""}><summary>{summary}</summary><div>{body}</div></details>'


def _block(title: str, caption: str, body: str) -> str:
    return _details(f'<span class="block-title">{_e(title)}</span> <span class="quiet">{_e(caption)}</span>', body,
                    kind="block", opened=True)


def _table(headers: tuple, rows: list) -> str:
    """A table that scrolls sideways inside its own box, so a wide one never widens the page; cells are HTML."""
    head = "".join(f"<th>{header}</th>" for header in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f'<div class="table"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _facts_list(entries: list) -> str:
    """Labelled values in a strip that wraps, from (label, value HTML, hover text). A value the run did not record is
    left out rather than shown blank."""
    cells = []
    for label, value, tip in entries:
        if value:
            title = f' title="{_e(tip)}"' if tip else ""
            cells.append(f'<div class="fact"{title}><dt>{_e(label)}</dt><dd>{value}</dd></div>')
    return f'<dl class="facts">{"".join(cells)}</dl>' if cells else '<p class="quiet">None recorded.</p>'


def _bullets(items: list) -> str:
    if not items:
        return '<p class="quiet">None.</p>'
    return '<ul class="list">' + "".join(f"<li>{_e(item)}</li>" for item in items) + "</ul>"


def _tag(text, tone: str, outline: bool = False) -> str:
    return f'<span class="tag{" outline" if outline else ""} tone-{tone}">{text}</span>'


def _fields(value, fold: tuple = ()) -> str:
    """Any JSON value as labelled lines: an object field by field (those in `fold` behind a click), a list item by item
    (more than 12 behind a click), text with line breaks as written, and null, true and false as such."""
    if isinstance(value, dict):
        if not value:
            return '<span class="quiet">empty</span>'
        return '<dl class="fields">' + "".join(
            f"<dt>{_e(key)}</dt><dd>{_details(_e(key), _fields(item)) if key in fold else _fields(item)}</dd>"
            for key, item in value.items()) + "</dl>"
    if isinstance(value, list):
        if not value:
            return '<span class="quiet">none</span>'
        if any(isinstance(item, (dict, list)) for item in value):
            shown = "<ol>" + "".join(f"<li>{_fields(item)}</li>" for item in value) + "</ol>"
        else:
            shown = _e(", ".join(item if isinstance(item, str) else json.dumps(item) for item in value))
        return _details(f"{len(value)} items", shown) if len(value) > 12 else shown
    if value is None or isinstance(value, bool):
        return f'<span class="quiet">{json.dumps(value)}</span>'
    if isinstance(value, str) and "\n" in value:
        return f'<pre class="output">{_e(value)}</pre>'
    return _e(value)


def _inline(text: str) -> str:
    """`code`, **bold** and ~~struck~~ in escaped text. No _ or * emphasis, so a file name such as part1_data.py
    stays as typed."""
    pieces = re.split(r"(`[^`]+`)", text)
    for n, piece in enumerate(pieces):
        if n % 2:
            pieces[n] = f"<code>{piece[1:-1]}</code>"
        else:
            pieces[n] = re.sub(r"~~(.+?)~~", r"<s>\1</s>", re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", piece))
    return "".join(pieces)


def _markdown(text: str, join: bool = False) -> str:
    """Escaped text as light Markdown: fences, # headings, - and 1. lists, > quotes and paragraphs.

    A chat message keeps each line as its own paragraph. A persona sheet (`join`) is hard-wrapped: a line continues
    the paragraph above when that line was long enough to have been wrapped, and an indented line continues a list item.
    """
    lines = escape(text or "").split("\n")
    wrap = 0.7 * max(len(line) for line in lines)
    blocks = []  # [tag, texts]: one text for a paragraph or heading, one per item in a list, one per line in a fence
    fence = None
    for previous, raw in zip([""] + lines, lines):
        line = raw.strip()
        last = blocks[-1] if blocks else ["", []]
        heading, item = HEADING.match(line), LIST_ITEM.match(line)
        if fence:
            if line.startswith(fence):
                fence = None
            else:
                last[1].append(raw)
        elif line.startswith(("```", "~~~")):
            fence = line[:3]
            blocks.append(["pre", []])
        elif heading:
            blocks.append([f"h{min(len(heading[1]) + 2, 5)}", [heading[2]]])
        elif line.startswith("&gt;"):
            blocks.append(["blockquote", [line[4:].strip()]])
        elif item:
            tag = "ol" if item[1][0].isdigit() else "ul"
            if last[0] != tag:
                blocks.append([tag, []])
            blocks[-1][1].append(item[2])
        elif join and line and (last[0] in ("ul", "ol") and raw[:1].isspace()
                                or last[0] == "p" and len(previous) >= wrap):
            last[1][-1] += " " + line  # an indented line continues a list item; a line after a wrapped one, a paragraph
        else:
            blocks.append(["p" if line else "", [line]])  # a blank line ends the paragraph or list above it
    return "".join(_markdown_block(tag, texts) for tag, texts in blocks if tag)


def _markdown_block(tag: str, texts: list[str]) -> str:
    if tag == "pre":
        return "<pre><code>" + "\n".join(texts) + "</code></pre>"
    if tag in ("ul", "ol"):
        return f"<{tag}>" + "".join(f"<li>{_inline(text)}</li>" for text in texts) + f"</{tag}>"
    return f"<{tag}>{_inline(texts[0])}</{tag}>"


def _finish(r: dict) -> tuple[str, str]:
    """The run's mark and why. Only the finish string earns ✓: a gate can exit 0 with most of the writeup blank (HW1's
    exits 0 when nothing is missing in the parts reached), so the reason also gives the exit and the blank slots."""
    facts = r["facts"]
    ended, slots = facts.get("ended_by"), facts.get("slots") or {}
    exit_code = (facts.get("gate") or {}).get("exit")
    detail = f" Gate exit {exit_code}." if exit_code is not None else " The gate has not run."
    if slots.get("blank_at_end"):
        detail += f" {slots['blank_at_end']} of {slots.get('total')} writeup slots still blank."
    if ended == "finished":
        return "✓", f"The finish string was seen in exchange {facts.get('finish_exchange')}." + detail
    if ended:
        return "✗", f"Ended because {ENDED_BY.get(ended, ended)}." + detail
    return "?", "No ending was recorded." + detail


def _grades(card: dict) -> list[dict]:
    """scorecard.json's items, worst grade first and in file order within a grade."""
    rank = list(GRADES)
    return sorted(card.get("items") or [], key=lambda item: rank.index(item["grade"]) if item.get("grade") in rank
                  else len(rank))


def _count(items: list[dict]) -> str:
    """How many of each grade, in GRADES order: '1 I · 5 P · 9 C · 2 n/o'."""
    counts = Counter(item.get("grade") for item in items)
    return " · ".join(f"{counts[grade]} {grade}" for grade in GRADES)


def _strip(r: dict) -> str:
    """The facts a reader checks before anything else."""
    facts, run = r["facts"], r["run"]
    mark, reason = _finish(r)
    tone, word = MARKS[mark]
    cost = (facts.get("cost_usd") or {}).get("tutor")
    windows = facts.get("windows")
    minutes = facts.get("minutes_wall")
    prompts = facts.get("prompts") or {}
    slots = facts.get("slots") or {}
    models = facts.get("models") or run.get("models") or {}
    return _facts_list([
        ("Run id", f'<span class="mono">{_e(r["id"])}</span>', None),
        ("Persona", _e(r["name"]) + (f" ({_e(r['persona'])})" if r["persona"] != r["name"] else ""), None),
        ("Exchanges", _exchanges(r), None),
        ("Ended because", _e(ENDED_BY.get(facts.get("ended_by"), facts.get("ended_by"))), None),
        ("Finished the assignment?", f'<span class="mark tone-{tone}">{mark}</span> {word}', reason),
        ("Scorecard", _scorecard_chip(r), None),
        ("Cost (tutor)", f"${cost:.2f}" if cost is not None else "", facts.get("note")),
        ("Usage windows", f"{windows} (at ${WINDOW_USD:.0f} per five-hour window)" if windows is not None else "",
         None),
        ("Wall clock", f"{minutes:.1f} minutes" if minutes is not None else "", None),
        ("Permission prompts", _e(prompts.get("total")) + (f", {prompts['denied']} denied" if prompts.get("denied")
                                                            else ""), None),
        ("Blank slots at end", _e(f"{slots['blank_at_end']} of {slots.get('total')}")
         if slots.get("blank_at_end") is not None else "", None),
        ("Models", _e(", ".join(f"{side} {model}" for side, model in models.items() if model)), None),
    ])


def _exchanges(r: dict) -> str:
    """'39 of a budget of 60'. `pilot run --turns N` is not recorded, so a run that ran out of exchanges short of
    pilot.toml's budget says so instead of claiming the wrong budget."""
    count, budget = r["facts"].get("exchanges"), (r["run"].get("config") or {}).get("max_turns")
    if count is None or budget is None:
        return _e(count)
    if r["facts"].get("ended_by") == "max_turns" and count != budget:
        return _e(f"{count} (pilot.toml's budget was {budget}; this run had its own --turns limit)")
    return _e(f"{count} of a budget of {budget}")


def _scorecard_chip(r: dict) -> str:
    """The grade count as a button that opens the Scorecard tab, with the fidelity word beside it."""
    items = _grades(r["card"])
    if not items and r["card_md"] is None:
        return ""
    fidelity = r["card"].get("fidelity")
    label = _count(items) if items else "scorecard.md"
    return (f'<button type="button" class="chip" data-tab="scorecard">{_e(label)}</button>'
            + (f' <span class="quiet">fidelity: {_e(fidelity)}</span>' if fidelity else ""))


def _alarms(r: dict) -> str:
    """Anything that makes the run less than the session it was meant to be, said once at the top of its panel."""
    lines = list(r["notes"])
    for key, sentence in ALARMS:
        found = r["facts"].get(key) or []
        numbers = found.get("exchanges") if isinstance(found, dict) else [item.get("exchange") for item in found]
        if numbers:
            lines.append(f"{sentence}: exchange{'s' * (len(numbers) > 1)} {', '.join(map(str, numbers))}.")
    if r["facts"].get("settings_loaded") is False:
        lines.append("The template's hooks did not run on the first exchange.")
    note = ('<p class="note">No facts.json in this run directory, so the figures on this page were computed from its '
            "records the way pilot report computes them.</p>") if r["summarized"] else ""
    return note + "".join(f'<p class="alarm">{_e(line)}</p>' for line in lines)


def _rail(runs: list[dict], first: dict | None) -> str:
    """A button per run with records, with its finish mark; a run directory without turns.jsonl is listed but
    disabled, because it has no panel to open."""
    buttons = []
    for r in runs:
        label = f'<span class="run-id">{_e(r["id"])}</span>'
        if r["turns"] is None:
            buttons.append(f'<button class="run" type="button" disabled><span>{label}no records</span></button>')
            continue
        mark, reason = _finish(r)
        anchor = "run-" + _slug(r["id"])
        buttons.append(f'<button class="run" type="button" data-run="{anchor}" aria-controls="{anchor}" aria-current='
                       f'"{"true" if r is first else "false"}"><span>{label}{_e(r["name"].split(" ")[0])}</span>'
                       f'<span class="mark tone-{MARKS[mark][0]}" title="{_e(reason)}">{mark}</span></button>')
    return "".join(buttons)


def _conversation(r: dict, index: int) -> str:
    """Every exchange in order: its turns as bubbles, what each side changed on disk, and a line when the exchange made
    no progress."""
    if not r["turns"]:
        return '<p class="quiet">turns.jsonl has no readable lines.</p>'
    stalls = (r["facts"].get("stalls") or {}).get("exchanges_without_progress") or []
    exchanges = {}
    for turn in r["turns"]:
        exchanges.setdefault(turn.get("exchange"), []).append(turn)
    stall = '<p class="line tone-warn">No progress in this exchange: no slot filled, no commit, no file changed.</p>'
    articles = [f'<article class="exchange" id="x{index}-{_slug(number)}"><h3>Exchange {_e(number)}</h3>'
                + "".join(map(_turn, turns)) + "".join(map(_changes, turns)) + (stall if number in stalls else "")
                + "</article>" for number, turns in exchanges.items()]
    return '<div class="thread">' + "".join(articles) + "</div>"


def _turn(turn: dict) -> str:
    """One side's turn: who, how long and the session's running cost; the message as a bubble; the student's own
    commands or the tutor's tool calls; the bracketed lines; and the rest of the turn's record behind a click."""
    actor = turn.get("actor") or "unknown"
    who = actor.capitalize() + (f" ({KIND.get(turn['kind'], turn['kind'])})" if turn.get("kind") else "")
    timing = [f"{turn['seconds']:.1f} s"] if turn.get("seconds") is not None else []
    cost = (turn.get("result") or {}).get("total_cost_usd")
    timing += [f"session total ${cost:.2f}"] if cost is not None else []
    text = turn.get("text") or ""
    message = _markdown(text) if text.strip() else "<p>No text this turn.</p>"
    actions = _student_commands(turn) if actor == "student" else _tutor_calls(turn)
    record = {key: value for key, value in turn.items() if key not in SHOWN}
    return (f'<div class="turn turn-{"student" if actor == "student" else "tutor"}"><header><span class="who">'
            f'{_e(who)}</span><span>{_e(" · ".join(timing))}</span></header><div class="bubble text">{message}</div>'
            + actions + _bracketed(turn) + _details("Turn record", _fields(record)) + "</div>")


def _student_commands(turn: dict) -> str:
    """What the student did in its own editor and terminal: what it wrote to itself, then each command."""
    items = [f'<p class="self">(to self) {_e(turn["narration"])}</p>'] if (turn.get("narration") or "").strip() else []
    items += [_call(call, flagged=True) for call in turn.get("tools") or []]
    return f'<div class="actions">{"".join(items)}</div>' if items else ""


def _tutor_calls(turn: dict) -> str:
    """The tutor's tool calls, folded behind one line that counts them and names the tools."""
    calls = turn.get("tools") or []
    if not calls:
        return ""
    names = ", ".join(dict.fromkeys(str(call.get("name")) for call in calls))
    return _details(f"{len(calls)} tool call{'s' * (len(calls) > 1)}: {_e(names)}",
                    "".join(_call(call, flagged=False) for call in calls))


def _call(call: dict, flagged: bool) -> str:
    """One tool call: its name and what it acted on, with did or failed on the student's own commands. The whole input
    and the end of the output are behind a click, because a student's edit to the writeup is its typed answer."""
    error = bool(call.get("is_error"))
    word, tone = COMMANDS[error]
    try:
        data = json.loads(call.get("input") or "null")
    except (TypeError, ValueError):  # the input is cut at 2000 characters, so a long one no longer parses
        data = call.get("input")
    target = data
    if isinstance(data, dict):
        target = next((data[key] for key in TARGET_KEYS if data.get(key)), json.dumps(data))
    line = " ".join(f"{call.get('name')} {target or ''}".split())[:200]
    output = "\n".join(str(call.get("result") or "").splitlines()[-TRANSCRIPT_TAIL_LINES:])
    return (f'<div class="call">{_tag(word, tone) if flagged else ""}<code>{_e(line)}</code>'
            + (' <span class="tone-bad">(error)</span>' if error and not flagged else "") + "</div>"
            + _details("Input and output", _fields(data) + (f'<pre class="output">{_e(output)}</pre>' if output.strip()
                                                            else "")))


def _prompt_lines(prompts: list) -> list[str]:
    """Permission prompts: approved, or denied with the reason; on a student turn, the file policy refusing."""
    return [f"[{'approved' if p.get('decision') == 'allow' else 'denied'}] {p.get('tool')}({p.get('summary')})"
            + (f": {p['reason']}" if p.get("decision") != "allow" and p.get("reason") else "") for p in prompts]


def _ask_lines(asks: list) -> list[str]:
    return [f"[question] {ask.get('question')} [answer] {ask.get('answer')}" for ask in asks]


def _hook_lines(hooks: list) -> list[str]:
    lines = []
    for hook in hooks:
        result = "ok" if hook.get("ok") else "failed" + (f": {hook['output']}" if hook.get("output") else "")
        lines.append(f"[hook] {hook.get('event')} {result}")
    return lines


def _fabrication_lines(fabrication: dict) -> list[str]:
    if not fabrication.get("fired"):
        return []
    again = "re-asked" if fabrication.get("retried") else "not re-asked"
    return [f"[student wrote Claude's side, rule {fabrication.get('rule')}, {again}]"]


def _event_lines(event: dict) -> list[str]:
    return ["[event] " + " ".join(f"{key}={value}" for key, value in event.items())]


def _stop_lines(stop: str) -> list[str]:
    return [f"[run stopped] {stop}"]


# One renderer per kind of bracketed line under a turn, in the order they are shown; each takes the turn's field.
BRACKETED = {"prompts": _prompt_lines, "asks": _ask_lines, "hooks": _hook_lines, "fabrication": _fabrication_lines,
             "event": _event_lines, "stop": _stop_lines}


def _bracketed(turn: dict) -> str:
    lines = [line for field, render in BRACKETED.items() if turn.get(field) for line in render(turn[field])]
    return "".join(f'<p class="line"><code>{_e(line)}</code></p>' for line in lines)


def _changes(turn: dict) -> str:
    """What one side changed on disk during its turn: commits, files changed, writeup slots filled."""
    filled = (turn.get("slots") or {}).get("filled_this_turn") or []
    parts = [f"commit {commit.get('sha')} {commit.get('subject')}" for commit in turn.get("commits") or []]
    parts += ["changed: " + ", ".join(turn["files_changed"])] if turn.get("files_changed") else []
    parts += ["filled: " + ", ".join(filled)] if filled else []
    return f'<p class="line"><code>{_e(turn.get("actor"))}: {_e(" · ".join(parts))}</code></p>' if parts else ""


def _outcome(r: dict) -> str:
    """The gate at the end, the writeup slots and who filled them, and what each side changed."""
    return _gate_block(r) + _slots_block(r["facts"]) + _changes_block(r["facts"])


def _gate_block(r: dict) -> str:
    command = (r["run"].get("config") or {}).get("gate")
    body = "<p>The gate has not run. No gate.txt in this run directory.</p>"
    if r["gate"] is not None:
        first, _, rest = r["gate"].partition("\n")
        named = f" (<code>{_e(command)}</code>)" if command else ""
        body = (f"<p>The gate{named} ran after the last exchange and finished with <code>{_e(first)}</code>.</p>"
                + _details(f"Gate output ({_e(first)})", f'<pre class="output">{_e(rest)}</pre>'))
    seen = r["facts"].get("finish_exchange")
    body += f"<p>The finish string was {'never seen' if seen is None else f'seen in exchange {_e(seen)}'}.</p>"
    return _block("The gate at the end", "the assignment's own check, run once after the last exchange", body)


def _slots_block(facts: dict) -> str:
    slots = facts.get("slots") or {}
    body = ""
    if slots.get("blank_at_end") is not None:
        body += f"<p>{_e(slots['blank_at_end'])} of {_e(slots.get('total'))} slots were still blank at the end.</p>"
    for side in SIDES:
        names = (slots.get("filled_by") or {}).get(side) or []
        body += f"<h4>Filled by the {side} ({len(names)})</h4>{_bullets(names)}"
    parts = [(f"Part {_e(part.get('part'))}", _e(part.get("first_exchange") or "not reached"),
              _e(f"{part.get('slots_filled')} of {part.get('slots_total')}")) for part in facts.get("parts") or []]
    if parts:
        body += _table(("Part", "First slot filled in exchange", "Slots filled"), parts)
    return _block("Writeup slots", "which answers were filled in, and by whom", body)


def _changes_block(facts: dict) -> str:
    body = ""
    for side in SIDES:
        commits = (facts.get("commits") or {}).get(side) or []
        body += f"<h4>Commits by the {side}</h4>" + _bullets(
            [f"exchange {commit.get('exchange')}: {commit.get('sha')} {commit.get('subject')}" for commit in commits])
        body += f"<h4>Files the {side} changed</h4>" + _bullets((facts.get("files_changed") or {}).get(side))
    return _block("Commits and files changed", "what each side changed in the repository", body)


def _scorecard(r: dict, index: int) -> str:
    """The reader's grades, worst first, with links to the exchanges each cites; without scorecard.json, scorecard.md
    as written."""
    card, items, written = r["card"], _grades(r["card"]), r["card_md"]
    if not items:
        if written is not None:
            return f'<pre class="output full">{_e(written)}</pre>'
        return '<p class="quiet">No scorecard for this run; run <code>pilot read</code>.</p>'
    fidelity = card.get("fidelity")
    meaning = FIDELITY.get(fidelity, "a word the reader's brief does not define")
    graded = f"Graded by {card.get('model') or 'an unrecorded model'}"
    if card.get("cost_usd") is not None:
        graded += f" for ${card['cost_usd']:.2f}"
    if card.get("rubric_sha256"):  # 12 characters tell two rubric versions apart; scorecard.json keeps the whole hash
        graded += f", against the rubric.md whose sha256 begins {card['rubric_sha256'][:12]}"
    rows = [(f'<span class="mono">{_e(item.get("id"))}</span>',
             _tag(_e(item.get("grade")), GRADES.get(item.get("grade"), "quiet")),
             ", ".join(f'<a href="#x{index}-{_slug(n)}" data-tab="conversation">{_e(n)}</a>'
                       for n in item.get("turns") or []) or "-",
             _inline(_e(item.get("evidence")))) for item in items]
    out = (f'<p class="quiet">{_e(GRADE_LEGEND)}</p><p><strong>{_e(_count(items))}</strong>'
           + (f". Fidelity: <strong>{_e(fidelity)}</strong>, which means {_e(meaning)}" if fidelity else "") + ".</p>"
           + f'<p class="quiet">{_e(graded)}.</p>')
    if card.get("valid") is False or card.get("missing"):
        out += f'<p class="alarm">The scorecard is incomplete. Missing: {_e(", ".join(card.get("missing") or []))}.</p>'
    out += _table(("Item", "Grade", "Exchanges", "Evidence"), rows)
    if card.get("one_lever"):
        out += f'<p class="note">ONE LEVER: {_e(card["one_lever"])}</p>'
    if written is not None:
        out += _details("scorecard.md, as the reader wrote it", f'<pre class="output full">{_e(written)}</pre>')
    return out


def _student(r: dict, assignment: Path) -> str:
    """The student facts, the persona's column of the placement grid, then the persona sheet."""
    facts = r["facts"]
    drift = facts.get("persona_drift") or {}
    entries = [("Message length, second half against first", _e(drift.get("ratio")),
                f"Median words per student message: {drift.get('early_median_words')} in the first half of the run, "
                f"{drift.get('late_median_words')} in the second.")]
    entries += [(label, _e(facts.get(key)), None) for label, key in STUDENT_FACTS]
    return (_block("Student facts", "counted from the records, never judged", _facts_list(entries))
            + _block("Placement grid", "where this persona stands on each thing the assignment demands",
                     _grid(r, assignment))
            + _sheet_block(r))


def _sheet_block(r: dict) -> str:
    """The persona sheet the student was given, rendered, with a note when it is not the run's own copy."""
    if r["sheet"] is None:
        missing = f"No persona sheet at personas/{r['persona']}.md." if r["persona"] else \
            "No persona named in run.json."
        return f'<p class="quiet">{_e(missing)}</p>'
    notes = ""
    if r["sheet_from"].startswith("personas/"):
        notes += ('<p class="note">The run directory has no persona.md, so this is the current sheet, which may have '
                  "changed since the run.</p>")
    if r["sheet_changed"]:
        notes += '<p class="alarm">persona.md does not match the sha256 run.json recorded for it.</p>'
    return _block(f"Persona sheet ({r['sheet_from']})", "the instructions the simulated student was given",
                  notes + f'<div class="text">{_markdown(r["sheet"], join=True)}</div>')


def _grid(r: dict, assignment: Path) -> str:
    """The persona's column of personas/INVENTORY.md, grouped as in the file, or a sentence saying why there is none."""
    col = inventory.column(assignment, r["persona"])
    if col is None:
        if not r["persona"]:
            why = "run.json names no persona"
        elif (assignment / inventory.PATH).exists():
            why = f"{inventory.PATH} has no column for {r['persona']}"
        else:
            why = f"this assignment has no {inventory.PATH}"
        return f'<p class="quiet">No placement grid: {_e(why)}.</p>'
    groups = {}
    for row in col["rows"]:
        groups.setdefault(row["group"] or "Rows in no demand table", []).append(_grid_row(row, col))
    tally = Counter(row["placement"] for row in col["rows"])
    caption = (f"From {inventory.PATH}, column {_e(r['persona'])}: "
               + ", ".join(f"{tally[placement]} {placement}" for placement in PLACEMENTS if tally[placement])
               + f"; {len(col['open_rulings'])} under an open ruling. A student behaving above a placement is a "
                 "simulation defect to report, never a reason to raise the placement.")
    return f'<p class="quiet">{caption}</p>' + "".join(
        f"<h4>{_e(group)}</h4>" + _table(("Row", "Placement", "What the assignment demands"), rows)
        for group, rows in groups.items())


def _grid_row(row: dict, col: dict) -> tuple[str, str, str]:
    """A row's id; its placement, with any draft or open-ruling mark; what is demanded, where it first bites, and for
    a wrong placement the belief its footnote names."""
    footnote = f"<sup>{row['footnote']}</sup>" if row["footnote"] is not None else ""
    placement = _tag(_e(row["placement"]) + footnote, PLACEMENTS.get(row["placement"], "quiet"))
    if row["draft"]:
        placement += " " + _tag("draft", "quiet", outline=True)
    if row["id"] in col["open_rulings"]:
        placement += " " + _tag("open ruling", "bad", outline=True)
    demand = _inline(_e(" ".join(filter(None, (row["demand"], row["note"])))))
    demand += f'<div class="quiet">First bites: {_inline(_e(row["where"]))}</div>' if row["where"] else ""
    belief = col["beliefs"].get(row["footnote"])
    demand += f"<div>Belief {row['footnote']}: {_inline(_e(belief))}</div>" if belief else ""
    return f'<span class="mono">{_e(row["id"])}</span>', placement, demand


def _session_facts(r: dict) -> str:
    """Every field of facts.json and run.json."""
    return ((_block("facts.json", "counted from the records, never judged", _fields(r["facts"])) if r["facts"] else
             '<p class="quiet">No facts.json.</p>')
            + (_block("run.json", "written by pilot run when the run started, and again when it ended",
                      _fields(r["run"], fold=("config", "env_stripped"))) if r["run"] else
               '<p class="quiet">No run.json in this run directory.</p>'))


def _panel(r: dict, index: int, assignment: Path) -> str:
    """One run: the persona's name, any alarms, the facts strip, the tab bar and the tabs. Every panel but the first,
    and every tab but Conversation, starts hidden, so without JavaScript the first run's conversation shows."""
    panes = {"conversation": _conversation(r, index), "outcome": _outcome(r), "scorecard": _scorecard(r, index),
             "student": _student(r, assignment), "facts": _session_facts(r)}
    tabs = "".join(f'<button class="tab" type="button" role="tab" id="t{index}-{key}" aria-controls="p{index}-{key}" '
                   f'aria-selected="{"false" if n else "true"}" data-tab="{key}">{label}</button>'
                   for n, (key, label, _) in enumerate(TABS))
    bodies = "".join(f'<section class="pane" role="tabpanel" id="p{index}-{key}" aria-labelledby="t{index}-{key}" '
                     f'data-pane="{key}"{" hidden" if n else ""}><p class="quiet">{_e(caption)}</p>'
                     f"{panes[key]}</section>" for n, (key, _, caption) in enumerate(TABS))
    hidden = " hidden" if index else ""
    return (f'<section class="panel" id="run-{_slug(r["id"])}"{hidden}><h2>{_e(r["name"] or r["id"])}</h2>'
            f'{_alarms(r)}{_strip(r)}<div class="tabs" role="tablist" aria-label="What to look at">{tabs}</div>'
            f"{bodies}</section>")


def _how_to_read(finish: str | None) -> str:
    named = f" (<code>{_e(finish)}</code>)" if finish else ""
    return (
        "<p>Each run is one session of the assignment with nobody human in it. One Claude plays a student, following "
        "a persona sheet that fixes what they know, half-know and get wrong; a second Claude is the tutor, working "
        "under the template's <code>CLAUDE.md</code>. The mark beside a run answers one question: did the run end "
        f"because the finish string{named}, the line that means the assignment is done, was seen? ✓ means it was. ✗ "
        "means the run ended another way: the student left, the exchange budget ran out, or an error stopped it. ? "
        "means no ending was recorded. Point at a mark for the exit code of the gate, the assignment's own check run "
        "after the last exchange, and for the writeup slots still blank.</p>"
        "<p>In the conversation the student is on the right in blue and the tutor on the left in green. Under a "
        "student message are the commands the student ran in its own editor and terminal, each marked did, or failed "
        "when it came back with an error; click one for its input and output. A line in square brackets is a "
        "permission prompt, a question Claude asked, a hook, or an event such as Claude Code being closed. The other "
        "tabs hold the gate's output and the writeup slots, the reader's grades, the persona sheet with the persona's "
        "column of the placement grid when the assignment has one, and every recorded field.</p>")


# The dark palette, used by both dark-mode blocks in CSS: when the system asks for dark (unless the page is set to
# light), and whenever the page is set to dark.
DARK = """
    color-scheme: dark;
    --paper: #0F1115; --surface: #171A20; --surface-2: #1C2027;
    --ink: #E8EAEE; --ink-2: #B6BCC7; --muted: #858C99;
    --rule: #272C35; --rule-soft: #20242B;
    --student: #84A9E8; --student-bg: #1B3050; --claude-bg: #1A3325;
    --accent: #D9836D; --good: #63B98A; --add-bg: #14251C; --del-bg: #2A1A17;
    --amber: #E0B062; --amber-bg: #2A2313;
"""
CSS = """
/* Tokens: every colour, size and space on the page. */
:root {
  color-scheme: light;
  --paper: #F4F6F8; --surface: #FFFFFF; --surface-2: #FAFBFC;
  --ink: #15171C; --ink-2: #454B57; --muted: #767D8B;
  --rule: #DCE1E8; --rule-soft: #EAEEF3;
  --student: #2F5DA8; --student-bg: #DCE9FC; --claude-bg: #DFEEE2;
  --accent: #B23A26; --good: #1F6B44; --add-bg: #E8F4EC; --del-bg: #FBEDEA;
  --amber: #8A5A00; --amber-bg: #FBF1DC;
  --sans: "IBM Plex Sans", system-ui, -apple-system, sans-serif;
  --serif: "IBM Plex Serif", Georgia, serif;
  --mono: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
  --text-xs: 11.5px; --text-sm: 12.5px; --text-md: 13.5px; --text-base: 15px; --text-lg: 20px; --text-xl: 26px;
  --space-1: 4px; --space-2: 8px; --space-3: 12px; --space-4: 16px; --space-5: 24px; --space-6: 48px;
  --radius: 4px; --radius-bubble: 16px;
  --gutter: var(--space-5); --rail-width: 250px; --fact-width: 185px; --bubble-width: 82%;
  --fields: minmax(10em, max-content) minmax(0, 1fr); --measure: 104ch; --output-height: 280px;
}

/* Dark mode */
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { /* dark palette */ }
}
:root[data-theme="dark"] { /* dark palette */ }

/* Page. Record text can hold long unbroken strings (paths, hashes, session ids): break them, never widen the page. */
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font: var(--text-base)/1.6 var(--sans);
  overflow-wrap: break-word;
}
h1, h2 { margin: 0; font-family: var(--serif); font-weight: 600; }
h1 { font-size: var(--text-lg); }
h2 { font-size: var(--text-xl); }
h3, h4 { margin: var(--space-3) 0 var(--space-1); font-size: var(--text-md); }
code, pre { font-family: var(--mono); font-size: var(--text-sm); }
pre { margin: 0; white-space: pre-wrap; }
a { color: var(--student); }
summary { cursor: pointer; }
:focus-visible { outline: 2px solid var(--student); outline-offset: 2px; }
.quiet { margin: 0 0 var(--space-2); font-size: var(--text-sm); color: var(--muted); }
.mono { font-family: var(--mono); }

/* Masthead */
.masthead { padding: var(--space-4) var(--gutter); background: var(--surface); border-bottom: 1px solid var(--rule); }
.masthead > * { max-width: var(--measure); }

/* Layout: the rail of runs beside the open run */
.layout { display: grid; grid-template-columns: var(--rail-width) minmax(0, 1fr); align-items: start; }

/* Rail */
.rail {
  position: sticky; top: env(safe-area-inset-top, 0px); height: 100vh; overflow-y: auto;
  display: flex; flex-direction: column; gap: var(--space-2);
  padding: var(--space-4);
  background: var(--surface-2); border-right: 1px solid var(--rule);
}
.run {
  display: flex; justify-content: space-between; align-items: center; gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  font: inherit; font-size: var(--text-sm); color: var(--muted); text-align: left;
  background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius); cursor: pointer;
}
.run:hover, .run[aria-current="true"] { border-color: var(--student); }
.run[aria-current="true"] { background: var(--student-bg); }
.run:disabled { border-style: dashed; cursor: default; }
.run-id { display: block; font-family: var(--mono); color: var(--ink); }
.mark { font-weight: 600; }

/* Panel: one run at a time */
.panel { padding: var(--space-5) var(--gutter) var(--space-6); }
.panel > * { max-width: var(--measure); }
.alarm, .note {
  margin: var(--space-2) 0; padding: var(--space-2) var(--space-3);
  font-size: var(--text-md); border-radius: var(--radius);
}
.alarm { color: var(--accent); background: var(--del-bg); border: 1px solid var(--accent); }
.note { color: var(--ink-2); background: var(--surface-2); border: 1px solid var(--rule); }

/* Facts strip, above the tabs and in The student. The 1px gaps show the rule colour between the facts. */
.facts {
  display: flex; flex-wrap: wrap; gap: 1px; margin: var(--space-3) 0;
  background: var(--rule); border: 1px solid var(--rule); border-radius: var(--radius); overflow: hidden;
}
.fact {
  flex: 1 1 var(--fact-width); min-width: 0;
  padding: var(--space-2) var(--space-3); background: var(--surface-2);
}
.fact dt { font-size: var(--text-xs); color: var(--muted); }
.fact dd { margin: 0; font-size: var(--text-md); }
.chip {
  padding: 0 var(--space-2); font: inherit; color: var(--student); cursor: pointer;
  background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius);
}

/* Tabs */
.tabs {
  display: flex; flex-wrap: wrap; gap: 0 var(--space-5);
  margin: var(--space-4) 0 var(--space-3); border-bottom: 1px solid var(--rule);
}
.tab {
  margin-bottom: -1px; padding: var(--space-2) 0;
  font: inherit; font-size: var(--text-md); color: var(--muted); cursor: pointer;
  background: none; border: 0; border-bottom: 2px solid transparent;
}
.tab[aria-selected="true"] { color: var(--ink); font-weight: 600; border-bottom-color: var(--student); }

/* Blocks: the sections of a tab, open, and the smaller disclosures inside them, closed */
.block {
  margin: 0 0 var(--space-3);
  background: var(--surface); border: 1px solid var(--rule); border-radius: var(--radius);
}
.block > summary { padding: var(--space-2) var(--space-4); }
.block > div { padding: 0 var(--space-4) var(--space-4); }
.block-title { font-weight: 600; }
.more > summary { font-size: var(--text-sm); color: var(--muted); }
.output {
  max-height: var(--output-height); overflow: auto; margin: var(--space-1) 0; padding: var(--space-2);
  font-size: var(--text-xs); background: var(--surface-2); border: 1px solid var(--rule);
}
.output.full { max-height: none; }
.list, .fields ol { margin: 0 0 var(--space-2); padding-left: var(--space-5); }

/* Text: chat messages and the persona sheet, rendered from Markdown */
.text p, .text ul, .text ol, .text pre, .text blockquote { margin: 0 0 var(--space-2); }
.text ul, .text ol { padding-left: var(--space-5); }
.text h3, .text h4, .text h5 {
  margin: var(--space-3) 0 var(--space-1); font-family: var(--serif); font-size: var(--text-base);
}
.text code { padding: 0 var(--space-1); background: var(--rule-soft); border-radius: var(--radius); }
/* A fence is usually a command to copy, so it scrolls sideways rather than wrapping. */
.text pre {
  padding: var(--space-2) var(--space-3); white-space: pre; overflow-x: auto;
  background: var(--rule-soft); border-left: 2px solid var(--accent);
}
.text pre code { padding: 0; background: none; }
.text blockquote { padding: 0 var(--space-3); color: var(--ink-2); border-left: 2px solid var(--rule); }
.text > :last-child { margin-bottom: 0; }

/* Conversation bubbles: the student on the right in blue, the tutor on the left in green */
.thread { display: flex; flex-direction: column; gap: var(--space-4); }
.exchange {
  display: flex; flex-direction: column; gap: var(--space-2);
  padding-top: var(--space-2); border-top: 1px solid var(--rule);
}
.exchange h3, .turn header {
  display: flex; gap: var(--space-2); margin: 0;
  font-family: var(--mono); font-size: var(--text-xs); color: var(--muted);
}
/* Capitals for the labels only: a timing such as "1.3 s" must keep its lower-case unit. */
.exchange h3, .who { text-transform: uppercase; }
.turn { display: flex; flex-direction: column; align-items: flex-start; gap: var(--space-1); }
.turn > * { max-width: var(--bubble-width); min-width: 0; }
.turn-student { align-items: flex-end; }
.who { color: var(--good); }
.turn-student .who { color: var(--student); }
.bubble {
  padding: var(--space-2) var(--space-4); background: var(--claude-bg);
  border-radius: var(--radius-bubble) var(--radius-bubble) var(--radius-bubble) var(--radius);
}
.turn-student .bubble {
  background: var(--student-bg);
  border-radius: var(--radius-bubble) var(--radius-bubble) var(--radius) var(--radius-bubble);
}

/* Commands: the student's own under its message, and the tutor's tool calls */
.actions {
  display: flex; flex-direction: column; gap: var(--space-1);
  padding-left: var(--space-3); border-left: 2px solid var(--student);
}
.self { margin: 0; font-style: italic; color: var(--muted); }
.call { display: flex; align-items: baseline; gap: var(--space-2); font-size: var(--text-sm); }
.call code, .line code { min-width: 0; color: var(--ink-2); }
.line { margin: 0; font-size: var(--text-sm); }

/* Tags and tones: one vocabulary for the finish marks, the grades, the command flags and the placements */
.tag {
  padding: 0 var(--space-2); white-space: nowrap;
  font-family: var(--mono); font-size: var(--text-xs);
  background: var(--tone-bg); border-radius: var(--radius);
}
.tag.outline { background: none; border: 1px dashed currentColor; }
.tone-good { color: var(--good); --tone-bg: var(--add-bg); }
.tone-warn { color: var(--amber); --tone-bg: var(--amber-bg); }
.tone-bad { color: var(--accent); --tone-bg: var(--del-bg); }
.tone-info { color: var(--student); --tone-bg: var(--student-bg); }
.tone-quiet { color: var(--ink-2); --tone-bg: var(--rule-soft); }

/* Tables: the scorecard, the parts of the writeup, the placement grid */
.table { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: var(--text-md); }
th, td {
  padding: var(--space-1) var(--space-2); text-align: left; vertical-align: top;
  border-top: 1px solid var(--rule-soft);
}
th { font-weight: 500; color: var(--muted); }

/* Fields: any recorded JSON value, a name beside its value */
.fields {
  display: grid; grid-template-columns: var(--fields); gap: var(--space-1) var(--space-4);
  margin: 0; font-size: var(--text-sm);
}
.fields dt { font-family: var(--mono); color: var(--muted); }
.fields dd { margin: 0; }

/* Narrow screens: the rail above the run; under 600px a 16px gutter, wider bubbles, a value under its name */
@media (max-width: 860px) {
  .layout { grid-template-columns: minmax(0, 1fr); }
  .rail { position: static; height: auto; border-right: 0; border-bottom: 1px solid var(--rule); }
}
@media (max-width: 600px) {
  :root { --gutter: var(--space-4); --bubble-width: 94%; --fields: minmax(0, 1fr); }
}
""".replace("/* dark palette */", DARK)

JS = """
// Every run's panel has the same five tabs, so each search stays inside one panel.
function showTab(panel, name) {
  for (const tab of panel.querySelectorAll(':scope > .tabs > .tab')) {
    tab.setAttribute('aria-selected', String(tab.dataset.tab === name));
  }
  for (const pane of panel.querySelectorAll(':scope > .pane')) {
    pane.hidden = pane.dataset.pane !== name;
  }
}

function showRun(panel) {
  for (const other of document.querySelectorAll('.panel')) {
    other.hidden = other !== panel;
  }
  for (const button of document.querySelectorAll('.run[data-run]')) {
    button.setAttribute('aria-current', String(button.dataset.run === panel.id));
  }
  showTab(panel, 'conversation');
}

document.addEventListener('click', (event) => {
  const control = event.target instanceof Element ? event.target.closest('[data-run], [data-tab]') : null;
  if (!control) return;
  if (!control.dataset.run) {
    // A tab, the scorecard count, or an exchange number in the scorecard. An exchange number is also a link, and the
    // browser follows it once its tab is showing.
    showTab(control.closest('.panel'), control.dataset.tab);
    return;
  }
  const panel = document.getElementById(control.dataset.run);
  showRun(panel);
  // The address names the open run, so a reload or a copied link opens it again.
  try {
    history.replaceState(null, '', '#' + panel.id);
  } catch {
    // A sandboxed frame may refuse; the page works the same without it.
  }
  // Under 860px the rail sits above the run, so bring the run into view; on a wide screen, go back to the top.
  if (matchMedia('(max-width: 860px)').matches) panel.scrollIntoView();
  else window.scrollTo(0, 0);
});

// An address ending in #run-<id> opens that run; one ending in #x<panel>-<exchange> also scrolls to the exchange.
const target = location.hash ? document.getElementById(location.hash.slice(1)) : null;
const home = target ? target.closest('.panel') : null;
if (home) {
  showRun(home);
  if (target !== home) target.scrollIntoView();
}
"""


def build(cfg) -> Path:
    """Write <runs_dir>/viewer.html over every run directory in cfg.runs_dir and return its path."""
    runs_dir = Path(cfg.runs_dir)
    assignment = runs_dir.resolve().parent
    dirs = [d for d in runs_dir.iterdir() if d.is_dir() and not d.name.startswith(".")] if runs_dir.is_dir() else []
    runs = sorted((_load(d, cfg, assignment) for d in dirs), reverse=True,
                  key=lambda r: (str(r["run"].get("started") or ""), r["id"]))
    shown = [r for r in runs if r["turns"] is not None]
    finish = getattr(cfg, "finish_string", None)
    title = f"Pilot runs: {_e(assignment.name)}"
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    empty = "".join(f'<p class="note">{_e(r["id"])}: no turns.jsonl in this directory, so it has no panel'
                    + (f'; run.json error: {_e(r["run"]["error"])}' if r["run"].get("error") else "") + ".</p>"
                    for r in runs if r["turns"] is None)
    masthead = (f'<header class="masthead"><h1>{title}</h1><p class="quiet">Generated {stamp}. {len(runs)} run '
                f'director{"y" if len(runs) == 1 else "ies"}, {len(shown)} with turns.jsonl.</p>'
                f'{_details("How to read this page", _how_to_read(finish))}{empty}</header>')
    nothing = "No run in this folder has records yet." if runs else "No run directories in this runs folder."
    panels = "".join(_panel(r, index, assignment) for index, r in enumerate(shown)) or f'<p class="note">{nothing}</p>'
    rail = _rail(runs, shown[0] if shown else None)
    page = (f'<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>{title}</title>\n'
            f"<style>{CSS}</style>\n</head>\n<body>\n{masthead}\n"
            f'<div class="layout">\n<nav class="rail" aria-label="Runs"><p class="quiet">Runs, newest first</p>{rail}'
            f"</nav>\n<main>{panels}</main>\n</div>\n<script>{JS}</script>\n</body>\n</html>\n")
    out = runs_dir / "viewer.html"
    runs_dir.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return out
