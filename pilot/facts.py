"""Measure a run from its records (RECORDS.md): WRITEUP slots, the transcript block for an actor turn, facts.json,
the report table over every run, and blank calibration sheets. Standard library only. `cfg` is read by attribute:
runs_dir, writeup, slot_marker, part_heading, fixed_minutes, template."""
import itertools
import json
import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import median

WINDOW_USD = 20.0  # assumed usage in USD per five-hour Claude for Teams window; a rule of thumb
MINUTES_PER_EXCHANGE = (2, 4)  # minutes a real student spends reading and typing per exchange, low and high
STUDENT_TAIL_LINES = 8  # tool output lines per tool call in the tutor's reply as the student sees it
TRANSCRIPT_TAIL_LINES = 20  # tool output lines per tool call in transcript.md
NOTE = "cost measured with a warm prompt cache; a real student pausing minutes between messages may pay more"
LABEL = re.compile(r"^\*\*(.+?)\*\*(.*)$", re.S)  # a line that starts with a bold label; the rest is the inline value
TRAIL = re.compile(r"^\s*(\(.*?\))?\s*(\*\*:\*\*|:)?\s*")  # after the bold: an optional (note), then a colon, bold or plain
SUSPICION = re.compile(r"simulat|harness|being tested", re.I)
RULE_FILES = re.compile(r"claude\.md|\.claude", re.I)
ABS_PATH = re.compile(r"(?:^|(?<=[\s\"'=(]))(~?/[\w.~-][^\s\"'`\\,;|&<>()]*)")  # absolute or ~ paths; not URLs
SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
SHEET_ROW = re.compile(r"^\|\s*(\w[\w.-]*)\s*\|([^|\n]*)\|", re.M)  # "| ID | grade |" in a calibration sheet
MAIN_ARGS = ("command", "file_path", "path", "pattern", "url", "skill", "description")
TOKEN_KEYS = {"input": ("inputTokens", "input_tokens"), "output": ("outputTokens", "output_tokens"),
              "cache_read": ("cacheReadInputTokens", "cache_read_input_tokens"),
              "cache_creation": ("cacheCreationInputTokens", "cache_creation_input_tokens")}
COLUMNS = ["run id", "persona", "ended_by", "exchanges", "wall minutes", "tutor USD", "tutor tokens (input+output)",
           "windows", "prompts", "blanks at end", "gate exit", "hours band", "drift", "fabrications"]


def _blank_heading(value: str, marker: str) -> bool:
    """A heading slot is blank when its first paragraph is empty, the marker, or the marker and a (note)."""
    return not value or bool(re.fullmatch(re.escape(marker) + r"\s*(\(.*\))?", value, re.S))


def slots(text: str, marker: str, part_heading: str, slot_heading: str = "") -> list[dict]:
    """Every slot in a writeup: a line starting with a bold label. Four shapes are read: `**Label:** value`,
    `**Question?** value`, `**Label** (note): value`, and a label whose answer sits on the lines below it (the
    first paragraph before the next label or heading). A bold label wrapped onto the next line is joined first.
    A slot is blank when its value is the marker or empty.

    With `slot_heading` (a regular expression whose group 1 is the label, such as `^### (.+)$`), a matching
    heading is also a slot: its value is the first paragraph below it, and it is blank when that paragraph is
    empty, the marker, or the marker followed by a bracketed note (`XXXX (add the diagram)`). Bold labels inside
    a heading slot's answer are part of the answer, not slots."""
    raw, lines, skip = text.splitlines(), [], False
    for i, line in enumerate(raw):
        if skip:  # the continuation line was joined onto the label above; keep the line count
            lines.append("")
            skip = False
        elif line.startswith("**") and "**" not in line[2:] and i + 1 < len(raw):
            lines.append(line + " " + raw[i + 1].strip())
            skip = True
        else:
            lines.append(line)
    part, out, heading = None, [], re.compile(part_heading)
    slot_rx, inside = re.compile(slot_heading) if slot_heading else None, False
    for idx, line in enumerate(lines):
        if m := heading.match(line):
            part, inside = int(m.group(1)), False
            continue
        if slot_rx and (m := slot_rx.match(line)):
            below = []
            for nxt in lines[idx + 1:]:
                if nxt.lstrip().startswith("#"):
                    break
                if nxt.strip():
                    below.append(nxt.strip())
                elif below:
                    break
            out.append({"label": m.group(1).strip(), "part": part,
                        "blank": _blank_heading(" ".join(below), marker)})
            inside = True
            continue
        if line.lstrip().startswith("#"):
            inside = False
        if inside or not (m := LABEL.match(line.strip())):
            continue
        label, value = m.group(1).strip().rstrip(":").strip(), TRAIL.sub("", m.group(2), count=1).strip()
        if not value:  # the answer sits below the label
            below = []
            for nxt in lines[idx + 1:]:
                s = nxt.strip()
                if s.startswith(("**", "#")) or heading.match(nxt):
                    break
                if s:
                    below.append(s)
                elif below:
                    break
            value = " ".join(below)
        out.append({"label": label, "part": part, "blank": value in (marker, "")})
    return out


def _text(path) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _loads(text):
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def _json(path) -> dict | None:
    data = _loads(_text(path))
    return data if isinstance(data, dict) else None


def load_turns(run_dir: Path) -> list[dict]:
    """The lines of turns.jsonl that parse; a last line cut short by a crash is skipped."""
    rows = [_loads(line) for line in (_text(Path(run_dir) / "turns.jsonl") or "").splitlines() if line.strip()]
    return [r for r in rows if isinstance(r, dict)]


def _arg(tool) -> str:
    """A tool call's main argument (the command, file path, pattern ...), or else its raw input."""
    args = _loads(tool.get("input")) if isinstance(tool.get("input"), str) else tool.get("input")
    if isinstance(args, dict):
        return next((args[k] for k in MAIN_ARGS if isinstance(args.get(k), str)), json.dumps(args))
    return str(tool.get("input") or "")


def render_turn(turn: dict, *, for_student: bool = False) -> str:
    """One transcript block; `for_student` is the tutor's reply as the student's terminal shows it."""
    tail = STUDENT_TAIL_LINES if for_student else TRANSCRIPT_TAIL_LINES
    out = [] if for_student else [f"## Exchange {turn.get('exchange')} · {turn.get('actor')}"]
    out.append((turn.get("text") or "").strip() or "(no text)")
    if not for_student and (turn.get("narration") or "").strip():  # what the student wrote to itself while editing
        out += ["> (to self) " + line for line in turn["narration"].strip().splitlines() if line.strip()]
    for tool in turn.get("tools") or []:
        arg = _arg(tool).strip().splitlines() or [""]
        more = " ..." if len(arg) > 1 or len(arg[0]) > 200 else ""
        out.append(f"> {tool.get('name')} {arg[0][:200]}{more}" + (" (error)" if tool.get("is_error") else ""))
        out += ["    " + line for line in str(tool.get("result") or "").rstrip().splitlines()[-tail:]]
    for p in turn.get("prompts") or []:
        word = "approved" if p.get("decision") == "allow" else "denied"
        out.append(f"> [{word}] {p.get('tool')}({p.get('summary')})")
    out += [f"> [question] {a.get('question')} · answer: {a.get('answer')}" for a in turn.get("asks") or []]
    if for_student:
        return "\n".join(out) + "\n"
    out += [f"> [hook] {h.get('event')} {'ok' if h.get('ok') else 'not ok'}" for h in turn.get("hooks") or []]
    done = [f"commit {c.get('sha')} {c.get('subject')}" for c in turn.get("commits") or []]
    if turn.get("files_changed"):  # the last commit line carries the files changed, as RECORDS.md shows
        done = done[:-1] + [" · ".join(done[-1:] + ["changed: " + ", ".join(turn["files_changed"])])]
    out += ["> " + d for d in done]
    out += [f"> [stopped] {turn['stop']}"] if turn.get("stop") else []
    return "\n".join(out) + "\n\n"


def _last(lines, get):
    return next((v for v in map(get, reversed(lines)) if v is not None), None)


def _tokens(lines) -> dict | None:
    """Tokens in the actor's last model_usage, summed over models; camelCase or snake_case keys."""
    usage = _last(lines, lambda t: (t.get("result") or {}).get("model_usage") or None)
    if not isinstance(usage, dict):
        return None
    models = [m for m in usage.values() if isinstance(m, dict)]
    return {k: sum(int(m.get(a) or m.get(b) or 0) for m in models) for k, (a, b) in TOKEN_KEYS.items()}


def _minutes(start, end) -> float | None:
    try:
        return round((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() / 60, 2)
    except (TypeError, ValueError):
        return None


def _alive(pid) -> bool:
    try:
        return isinstance(pid, int) and pid > 0 and os.kill(pid, 0) is None
    except OSError as e:
        return isinstance(e, PermissionError)  # the process exists but belongs to another user


def _gate(run_dir) -> dict:
    first, _, rest = (_text(Path(run_dir) / "gate.txt") or "").partition("\n")
    code = first.strip().removeprefix("exit").strip()
    tail = "\n".join(rest.splitlines()[-10:]) or None
    return {"exit": int(code) if code.lstrip("-").isdigit() else code or None, "tail": tail}


def _outside(tool, repo: str) -> list[str]:
    """Absolute or ~ paths in a tool call's input that lie outside the repo (/dev/ ignored)."""
    raw, repo = tool.get("input"), repo.rstrip("/")
    paths = ABS_PATH.findall(raw if isinstance(raw, str) else json.dumps(raw))
    return [p for p in paths if p.rstrip("/") != repo and not p.startswith((repo + "/", "/dev/"))]


def _parts(turns, run, cfg) -> list[dict] | None:
    """Per part: slots in the repo's WRITEUP and the first exchange that filled one; None when the repo is gone."""
    text = _text(Path(run["repo"]) / cfg.writeup) if run.get("repo") else None
    if text is None:
        return None
    found, first = slots(text, cfg.slot_marker, cfg.part_heading, getattr(cfg, "slot_heading", "")), {}
    for t in reversed(turns):  # label -> the earliest exchange that filled it
        first.update(dict.fromkeys((t.get("slots") or {}).get("filled_this_turn") or [], t.get("exchange")))
    mine = {p: [s for s in found if s["part"] == p] for p in dict.fromkeys(s["part"] for s in found) if p is not None}
    return [{"part": p, "first_exchange": min((first[s["label"]] for s in m if s["label"] in first), default=None),
             "slots_filled": sum(not s["blank"] for s in m), "slots_total": len(m)} for p, m in mine.items()]


def summarize(run_dir: Path, cfg) -> dict:
    """Every facts.json field, from turns.jsonl, run.json, gate.txt and the repo run.json names. Writes nothing."""
    run_dir = Path(run_dir)
    run, turns = _json(run_dir / "run.json") or {}, load_turns(run_dir)
    lines = [line for line in (_text(run_dir / "turns.jsonl") or "").splitlines() if line.strip()]
    by = {a: [t for t in turns if t.get("actor") == a] for a in ("tutor", "student")}
    tutor, student, last = by["tutor"], by["student"], (turns[-1] if turns else {})
    exchanges = max((t.get("exchange") or 0 for t in turns), default=0)
    minutes = {a: round(sum(t.get("seconds") or 0 for t in by[a]) / 60, 2) for a in by}
    cost = {a: _last(by[a], lambda t: (t.get("result") or {}).get("total_cost_usd")) for a in by}
    prompts = [p for t in tutor for p in t.get("prompts") or []]
    hooks = [h for t in turns for h in t.get("hooks") or []]
    marks = [t["slots"] for t in turns if isinstance(t.get("slots"), dict)] or [{}]
    start = marks[0].get("blank")
    moved = Counter()  # exchange -> actor turns that changed a non-TRANSCRIPT file, filled a slot or committed
    for t in turns:
        files = [f for f in t.get("files_changed") or [] if f != "TRANSCRIPT.md"]
        filled = (t.get("slots") or {}).get("filled_this_turn")
        moved[t.get("exchange") or 0] += bool(files or filled or t.get("commits"))
    stalled = [x for x in sorted(moved) if not moved[x]]
    words = [len((t.get("text") or "").split()) for t in student]
    half = len(words) // 2
    early, late = (median(words[:half]), median(words[half:])) if half else (None, None)
    fabricated = [t.get("exchange") for t in student if (t.get("fabrication") or {}).get("fired")]
    repo, settings = run.get("repo"), _json(Path(cfg.template) / ".claude" / "settings.json") or {}
    left = dict.fromkeys((t.get("exchange"), p) for t in tutor for x in t.get("tools") or []
                         for p in _outside(x, repo or ""))
    bash = [(t.get("exchange"), _arg(x)) for t in student for x in t.get("tools") or [] if x.get("name") == "Bash"]
    return {
        "run_id": run.get("run_id", run_dir.name), "persona": run.get("persona"),
        "student_name": run.get("student_name"),
        "status": run.get("status"), "exchanges": exchanges, "truncated_lines": len(lines) - len(turns),
        "ended_by": run.get("ended_by") or last.get("stop") or
        ("crashed" if run.get("status") == "running" and not _alive(run.get("pid")) else None),
        "minutes_wall": _minutes(run.get("started"), run.get("ended") or last.get("t_end")),
        "minutes_tutor": minutes["tutor"], "minutes_student": minutes["student"],
        "setup_seconds": run.get("setup_seconds"),
        "cost_usd": {**cost, "reader": (_json(run_dir / "scorecard.json") or {}).get("cost_usd"),
                     "total_student_side": cost["tutor"]},
        "tokens": {a: _tokens(by[a]) for a in by},
        "windows": None if cost["tutor"] is None else round(cost["tutor"] / WINDOW_USD, 3),
        "hours_band": {f"{m}min": round((minutes["tutor"] + exchanges * m + (cfg.fixed_minutes or 0)) / 60, 2)
                       for m in MINUTES_PER_EXCHANGE},
        "prompts": {"total": len(prompts), "by_tool": dict(Counter(p.get("tool") for p in prompts)),
                    "denied": sum(p.get("decision") == "deny" for p in prompts)},
        "hooks": {"total": len(hooks), "by_event": dict(Counter(h.get("event") for h in hooks))},
        "settings_loaded": any(t.get("hooks") for t in turns if t.get("exchange") == 1)
        if turns and settings.get("hooks") else None,  # null when the template declares no hooks
        "files_changed": {a: list(dict.fromkeys(f for t in by[a] for f in t.get("files_changed") or [])) for a in by},
        "commits": {a: [{**c, "exchange": t.get("exchange")} for t in by[a] for c in t.get("commits") or []]
                    for a in by},
        "slots": {"total": marks[-1].get("total"), "blank_at_end": marks[-1].get("blank"),
                  "blank_at_start": None if start is None else start + len(marks[0].get("filled_this_turn") or []),
                  "filled_by": {a: [s for t in by[a] for s in (t.get("slots") or {}).get("filled_this_turn") or []]
                                for a in by}},
        "parts": _parts(turns, run, cfg), "gate": _gate(run_dir),
        "finish_exchange": next((t.get("exchange") for t in turns if t.get("finish_seen")), None),
        "stalls": {"exchanges_without_progress": stalled, "longest": max(
            (len(list(g)) for _, g in itertools.groupby(enumerate(stalled), lambda p: p[1] - p[0])), default=0)},
        "tutor_left_repo": [{"exchange": x, "path": p} for x, p in left] if repo else None,
        "suspicion": [{"exchange": t.get("exchange"), "sentence": s.strip()} for t in tutor
                      for s in SENTENCE.split(t.get("text") or "") if SUSPICION.search(s)],
        "student_saw_rules": [{"exchange": x, "command": c[:300]} for x, c in bash if RULE_FILES.search(c)],
        "student_bash": len(bash), "student_denied": sum(len(t.get("prompts") or []) for t in student),
        "empty_student_turns": sum(not (t.get("text") or "").strip() for t in student),
        "persona_drift": {"early_median_words": early, "late_median_words": late,
                          "ratio": round(late / max(1, early), 2) if half else None},
        "student_words_median": median(words) if words else None,
        "student_wrote_tutor_side": {"count": len(fabricated), "exchanges": fabricated},
        "models": {a: _last(by[a], lambda t: t.get("model") or None) or (run.get("models") or {}).get(a) for a in by},
        "sdk_version": run.get("sdk_version"), "claude_version": run.get("claude_version"), "note": NOTE}


def write_facts(run_dir: Path, cfg) -> Path:
    path = Path(run_dir) / "facts.json"
    path.write_text(json.dumps(summarize(run_dir, cfg), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _cell(v, digits=None) -> str:
    if v is None:
        return "-"
    return f"{v:.{digits}f}" if digits is not None and isinstance(v, (int, float)) else str(v).replace("|", "/")


def _row(d: Path, cfg) -> list[str]:
    """One report row: facts.json when present, else computed on the fly; a bad record becomes a note."""
    if not (d / "turns.jsonl").is_file():
        return [d.name, "no turns.jsonl"] + [""] * (len(COLUMNS) - 2)
    try:
        f = _json(d / "facts.json") or summarize(d, cfg)
        tok, band = (f.get("tokens") or {}).get("tutor"), f.get("hours_band") or {}
        lo, hi = (_cell(band.get(f"{m}min"), 1) for m in MINUTES_PER_EXCHANGE)
        return [d.name, _cell(f.get("persona")), _cell(f.get("ended_by")), _cell(f.get("exchanges")),
                _cell(f.get("minutes_wall"), 1), _cell((f.get("cost_usd") or {}).get("tutor"), 2),
                _cell(tok["input"] + tok["output"] if tok else None), _cell(f.get("windows"), 2),
                _cell((f.get("prompts") or {}).get("total")), _cell((f.get("slots") or {}).get("blank_at_end")),
                _cell((f.get("gate") or {}).get("exit")), f"{lo}–{hi}",
                _cell((f.get("persona_drift") or {}).get("ratio")),
                _cell((f.get("student_wrote_tutor_side") or {}).get("count"))]
    except Exception as e:  # one bad record must not stop a report over many runs
        return [d.name, _cell(f"could not summarize: {type(e).__name__}: {e}")] + [""] * (len(COLUMNS) - 2)


def _grade(grade) -> str:
    """C, P and I upper-cased; every spelling of not observed (n/o, n-o, n.o, no) becomes n/o."""
    grade = str(grade).strip().upper()
    return "n/o" if grade in ("N/O", "N-O", "N.O", "NO") else grade


def _agreement(dirs: list[Path]) -> str:
    """Percent exact agreement per item for each pair of graders (initials from sheets, and the reader)."""
    grades: dict[str, dict] = {}  # initials, or "reader" -> {(run id, item): grade}
    for d in dirs:
        for s in sorted(d.glob("sheet-*.md")):
            for item, grade in SHEET_ROW.findall(_text(s) or ""):
                if grade.strip() and item.lower() != "item":
                    grades.setdefault(s.stem.removeprefix("sheet-"), {})[(d.name, item)] = _grade(grade)
        for i in (_json(d / "scorecard.json") or {}).get("items") or []:
            if isinstance(i, dict) and i.get("id") and str(i.get("grade") or "").strip():
                grades.setdefault("reader", {})[(d.name, i["id"])] = _grade(i["grade"])
    pairs = list(itertools.combinations(sorted(grades), 2))  # every pair of graders, the reader included
    if not pairs:
        return ""
    rows = ["| item | " + " | ".join(f"{a} vs {b}" for a, b in pairs) + " |", "|---" * (len(pairs) + 1) + "|"]
    for item in sorted({i for g in grades.values() for _, i in g}):
        cells = []
        for a, b in pairs:
            both = [k for k in grades[a] if k[1] == item and k in grades[b]]
            same = sum(grades[a][k] == grades[b][k] for k in both)
            cells.append(f"{round(100 * same / len(both))}% of {len(both)}" if both else "-")
        rows.append(f"| {item} | " + " | ".join(cells) + " |")
    return ("\n## Agreement\n\nPercent exact agreement per item, over the runs both graded; blank grades are "
            "ignored.\n\n" + "\n".join(rows) + "\n")


def report(cfg) -> str:
    """One Markdown table over every run directory, the cost note, then agreement over filled-in sheets."""
    runs = Path(cfg.runs_dir)
    dirs = sorted(d for d in runs.iterdir() if d.is_dir()) if runs.is_dir() else []
    lines = ["| " + " | ".join(COLUMNS) + " |", "|---" * len(COLUMNS) + "|"]
    lines += ["| " + " | ".join(_row(d, cfg)) + " |" for d in dirs]
    empty = "" if dirs else f"\nNo run directories in {runs}.\n"
    note = f"\nNote: {NOTE}. Windows assume ${WINDOW_USD:.0f} of usage per five-hour window.\n"
    return "\n".join(lines) + "\n" + empty + note + _agreement(dirs)


def sheet(run_dir: Path, cfg, initials: str) -> Path:
    """A blank calibration sheet with one row per rubric item; never overwrites a sheet that exists."""
    rubric = (Path(cfg.runs_dir).parent / "rubric.md").read_text(encoding="utf-8")
    ids = [i for i in re.findall(r"^- \*\*(.+?)\*\*", rubric, re.M) if i != "ONE_LEVER"]
    text = "\n".join([f"# Calibration sheet: {Path(run_dir).name}, graded by {initials}", "",
                      "Grade each item C, P, I or n/o; under turns, list the exchange numbers the grade rests on.", "",
                      "| item | grade | turns | rationale |", "|---|---|---|---|", *[f"| {i} |  |  |  |" for i in ids],
                      "", "ONE LEVER: "]) + "\n"
    path = Path(run_dir) / f"sheet-{initials}.md"
    with path.open("x", encoding="utf-8") as f:  # mode "x": a filled-in sheet is never overwritten
        f.write(text)
    return path
