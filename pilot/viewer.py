"""Build runs/viewer.html: one self-contained page over every run directory in runs/.

Reads run.json, turns.jsonl, facts.json, gate.txt, scorecard.md and the persona sheet directly, in the shapes
RECORDS.md gives. Standard library only; the page has no scripts and loads nothing over the network.
"""
import json
import re
from datetime import datetime, timezone
from html import escape
from pathlib import Path

# Input keys tried in order to pull the one-line target (a command or a path) out of a tool call's input JSON.
TARGET_KEYS = ("command", "file_path", "notebook_path", "path", "pattern", "url", "query", "skill", "description")
CSS = ("body{max-width:62rem;margin:0 auto;padding:0 1rem;font-family:sans-serif;line-height:1.4}"
       "pre,code{font-family:monospace;font-size:.9em}pre,.t{white-space:pre-wrap}"
       "table{border-collapse:collapse}th,td{padding:.2rem .5rem;text-align:left;vertical-align:top}"
       "tbody tr:nth-child(even){background:#eee}")
COLUMNS = ("Run", "Persona", "Ended by", "Exchanges", "Gate exit", "Wall minutes", "Tutor USD", "Windows",
           "Prompts", "Blank slots at end", "Drift", "Fabrications")


def _text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _json(path: Path, notes: list[str]) -> dict:
    raw = _text(path)
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


def _turns(path: Path, notes: list[str]) -> list[dict]:
    turns, bad = [], 0
    for line in (_text(path) or "").splitlines():
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


def _first(*values):
    return next((v for v in values if v is not None), None)


def _num(value, digits: int):
    return f"{value:.{digits}f}" if isinstance(value, (int, float)) and not isinstance(value, bool) else value


def _cell(value) -> str:
    return "" if value is None else escape(str(value))


def _anchor(run_id: str) -> str:
    return "run-" + re.sub(r"[^A-Za-z0-9_-]", "-", run_id)


def _load(run_dir: Path, assignment_dir: Path) -> dict:
    notes: list[str] = []
    r = {"id": run_dir.name, "notes": notes, "run": _json(run_dir / "run.json", notes),
         "facts": _json(run_dir / "facts.json", notes), "gate": _text(run_dir / "gate.txt"),
         "scorecard": _text(run_dir / "scorecard.md"), "turns": None}
    if (run_dir / "turns.jsonl").exists():
        r["turns"] = _turns(run_dir / "turns.jsonl", notes)
    r["persona"] = str(r["run"].get("persona") or r["facts"].get("persona") or "")
    r["sheet"] = _text(assignment_dir / "personas" / f"{r['persona']}.md") if r["persona"] else None
    f, run, turns = r["facts"], r["run"], r["turns"] or []
    tutor_usd = [t["result"]["total_cost_usd"] for t in turns if t.get("actor") == "tutor"
                 and isinstance(t.get("result"), dict) and t["result"].get("total_cost_usd") is not None]
    gate_line = (r["gate"] or "").split("\n", 1)[0].strip()
    r["row"] = [r["persona"],
                _first(f.get("ended_by"), run.get("ended_by"), turns[-1].get("stop") if turns else None),
                _first(f.get("exchanges"), max((t.get("exchange") or 0 for t in turns), default=None)),
                _first((f.get("gate") or {}).get("exit"), gate_line[5:] if gate_line.startswith("exit ") else None),
                _num(f.get("minutes_wall"), 1),
                _num(_first((f.get("cost_usd") or {}).get("tutor"), tutor_usd[-1] if tutor_usd else None), 2),
                _num(f.get("windows"), 2),
                (f.get("prompts") or {}).get("total"),
                (f.get("slots") or {}).get("blank_at_end"),
                _num((f.get("persona_drift") or {}).get("ratio"), 2),
                (f.get("student_wrote_tutor_side") or {}).get("count")]
    return r


def _target(raw) -> str:
    data = raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except ValueError:
            data = raw  # the input was cut at 2000 characters; show its head
    if isinstance(data, dict):
        data = next((data[k] for k in TARGET_KEYS if data.get(k)), json.dumps(data))
    return " ".join(str(data or "").split())[:200]


def _tool(call: dict) -> str:
    line = f"{call.get('name')} {_target(call.get('input'))}".rstrip() + (" (error)" if call.get("is_error") else "")
    tail = str(call.get("result") or "")
    return f"<div><code>{escape(line)}</code></div>" + (f"<pre>{escape(tail)}</pre>" if tail.strip() else "")


def _turn(t: dict) -> str:
    head = [f"{t['seconds']:.0f} s"] if isinstance(t.get("seconds"), (int, float)) else []
    cost = (t.get("result") or {}).get("total_cost_usd")
    if isinstance(cost, (int, float)):
        head.append(f"session total ${cost:.2f}")
    out = [f"<p><strong>{escape(str(t.get('actor') or 'unknown').capitalize())}</strong> {escape(', '.join(head))}</p>"]
    text = str(t.get("text") or "")
    out.append(f'<div class="t">{escape(text)}</div>' if text.strip() else "<p>No text this turn.</p>")
    if str(t.get("narration") or "").strip():
        out.append(f'<p style="color:#666">(to self) {escape(str(t["narration"]))}</p>')
    tools = t.get("tools") or []
    if tools:
        calls = "".join(_tool(c) for c in tools if isinstance(c, dict))
        out.append(f"<details><summary>{len(tools)} tool call{'s' * (len(tools) != 1)}</summary>{calls}</details>")
    lines = []
    for p in t.get("prompts") or []:
        allowed = p.get("decision") == "allow"
        reason = f": {p['reason']}" if not allowed and p.get("reason") else ""
        lines.append(f"[{'approved' if allowed else 'denied'}] {p.get('tool')}({p.get('summary')}){reason}")
    lines += [f"[question] {a.get('question')} [answer] {a.get('answer')}" for a in t.get("asks") or []]
    for h in t.get("hooks") or []:
        detail = "" if h.get("ok") or not h.get("output") else f": {h['output']}"
        lines.append(f"[hook] {h.get('event')} {'ok' if h.get('ok') else 'failed'}{detail}")
    fab = t.get("fabrication") or {}
    if fab.get("fired"):
        lines.append(f"[student wrote Claude's side, rule {fab.get('rule')}, "
                     f"{'re-asked' if fab.get('retried') else 'not re-asked'}]")
    if t.get("stop"):
        lines.append(f"[run stopped] {t['stop']}")
    out += [f"<div><code>{escape(line)}</code></div>" for line in lines]
    return "\n".join(out)


def _changes(t: dict) -> str:
    parts = [f"commit {c.get('sha')} {c.get('subject')}" for c in t.get("commits") or []]
    if t.get("files_changed"):
        parts.append("changed: " + ", ".join(map(str, t["files_changed"])))
    filled = (t.get("slots") or {}).get("filled_this_turn") or []
    if filled:
        parts.append("filled: " + ", ".join(map(str, filled)))
    return f"<div><code>{escape(str(t.get('actor')))}: {escape(' · '.join(parts))}</code></div>" if parts else ""


def _conversation(r: dict) -> str:
    if not r["turns"]:
        return "<p>turns.jsonl has no readable lines.</p>"
    stalls = (r["facts"].get("stalls") or {}).get("exchanges_without_progress") or []
    groups: dict = {}
    for t in r["turns"]:
        groups.setdefault(t.get("exchange"), []).append(t)
    out = []
    for ex, group in groups.items():
        out.append(f"<h4>Exchange {_cell(ex)}</h4>")
        out += [_turn(t) for t in group] + [c for c in map(_changes, group) if c]
        if ex in stalls:
            out.append("<p>No progress in this exchange: no slot filled, no commit, no file changed.</p>")
    return "\n".join(out)


def _section(r: dict) -> str:
    run, persona = r["run"], r["persona"]
    models = r["facts"].get("models") or run.get("models") or {}
    items = list(zip(COLUMNS[1:], r["row"])) + [
        ("Status", run.get("status")),
        ("Models", ", ".join(f"{k} {v or 'default'}" for k, v in models.items()) if isinstance(models, dict) else models),
        ("Started", run.get("started")), ("Template commit", (run.get("template") or {}).get("commit")),
        ("Error", run.get("error"))]
    strip = " · ".join(f"{escape(k)}: {_cell(v)}" for k, v in items if v not in (None, ""))
    out = [f'<section id="{_anchor(r["id"])}">', f"<h2>{escape(r['id'])}</h2>",
           f"<p>{strip}</p>" if run or r["facts"] else "<p>No run.json or facts.json in this directory.</p>"]
    if not r["facts"]:
        out.append("<p>No facts.json; exchanges and tutor USD are read from turns.jsonl, other figures are blank.</p>")
    out += [f"<p>{escape(n)}</p>" for n in r["notes"]]
    out += ["<h3>Conversation</h3>", _conversation(r), "<h3>Scorecard</h3>",
            f"<pre>{escape(r['scorecard'])}</pre>" if r["scorecard"] else "<p>No scorecard.md for this run.</p>"]
    sheet = f"personas/{persona}.md"
    if r["sheet"] is not None:
        out.append(f"<details><summary>Persona sheet ({escape(sheet)})</summary><pre>{escape(r['sheet'])}</pre></details>")
    else:
        out.append(f"<p>No persona sheet at {escape(sheet)}.</p>" if persona else "<p>No persona named in run.json.</p>")
    if r["gate"] is not None:
        first, _, rest = r["gate"].partition("\n")
        out.append(f"<details><summary>Gate output ({escape(first.strip())})</summary><pre>{escape(rest)}</pre></details>")
    else:
        out.append("<p>No gate.txt; the gate has not run for this run.</p>")
    out += ['<p><a href="#top">Back to the index</a></p>', "</section>"]
    return "\n".join(out)


def build(cfg) -> Path:
    """Write <runs_dir>/viewer.html over every run directory in cfg.runs_dir and return its path."""
    runs_dir = Path(cfg.runs_dir)
    assignment = runs_dir.resolve().parent
    dirs = [p for p in runs_dir.iterdir() if p.is_dir() and not p.name.startswith(".")] if runs_dir.is_dir() else []
    runs = sorted((_load(d, assignment) for d in dirs), key=lambda r: (str(r["run"].get("started") or ""), r["id"]),
                  reverse=True)
    rows = []
    for r in runs:
        if r["turns"] is None:
            error = f"; run.json error: {r['run']['error']}" if r["run"].get("error") else ""
            rows.append(f'<tr><td colspan="{len(COLUMNS)}">{escape(r["id"])}: no turns.jsonl in this directory, '
                        f"so it has no section below{escape(error)}.</td></tr>")
        else:
            link = f'<a href="#{_anchor(r["id"])}">{escape(r["id"])}</a>'
            rows.append("<tr>" + "".join(f"<td>{c}</td>" for c in [link] + [_cell(v) for v in r["row"]]) + "</tr>")
    head = "".join(f"<th>{escape(c)}</th>" for c in COLUMNS)
    index = (f"<table><thead><tr>{head}</tr></thead><tbody>\n" + "\n".join(rows) + "\n</tbody></table>"
             if rows else "<p>No run directories in this runs folder.</p>")
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    recorded = sum(r["turns"] is not None for r in runs)
    page = "\n".join([
        '<!DOCTYPE html>', '<html lang="en"><head><meta charset="utf-8">',
        f"<title>Pilot runs: {escape(assignment.name)}</title><style>{CSS}</style></head><body>",
        f'<h1 id="top">Pilot runs: {escape(assignment.name)}</h1>',
        f"<p>Generated {stamp}. {len(runs)} run director{'y' if len(runs) == 1 else 'ies'}, {recorded} with turns.jsonl.</p>",
        index, *(_section(r) for r in runs if r["turns"] is not None), "</body></html>", ""])
    out = runs_dir / "viewer.html"
    runs_dir.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    return out
