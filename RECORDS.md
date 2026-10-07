# Records and interfaces

The contract between `pilot/run.py` (writes), `pilot/facts.py`, `pilot/viewer.py`, `pilot/reader.py` (read)
and `pilot/cli.py` (dispatches). Where this file and the code disagree, fix one of them the same day.
Every field below is present on every record it belongs to; a value that could not be measured is `null`.

## Where records live

`<assignment-dir>/runs/<run-id>/` holds one run. `<run-id>` = persona first name, lowercased, `-MMDD-HHMM`,
and `-N` only if that id already exists (chosen by exclusive `mkdir` of the run directory).

| file | written | by |
|---|---|---|
| `run.json` | at start (status `running`); rewritten once at the end | run.py |
| `persona.md` | at start: the persona sheet exactly as this run was given it (`run.json` carries its sha256) | run.py |
| `turns.jsonl` | one line appended after every actor turn, flushed and fsynced | run.py |
| `transcript.md` | one block appended after every actor turn (rendered by `facts.render_turn`) | run.py |
| `run.log` | stderr of both CLI processes, appended as it arrives | run.py |
| `gate.txt` | end: first line `exit <code>` (or `exit timeout`), then the gate command's output | run.py |
| `facts.json` | end, in a guarded block; regenerable by `pilot report` | facts.py |
| `scorecard.md`, `scorecard.json` | `pilot read`; `scorecard.json` is `{"cost_usd": float, "model": str, "fidelity": "hold|drifted|broke", "one_lever": str, "items": [{"id": str, "grade": "C|P|I|n/o", "turns": [int], "evidence": str}]}` | reader.py |
| `sheet-<initials>.md` | `pilot calibrate` | facts.py |
| `../viewer.html` (in `runs/`) | `pilot view` | viewer.py |

## run.json

```json
{"run_id": "jordan-0924-1412", "status": "running|finished|failed",
 "assignment_dir": "/abs/path", "persona": "jordan", "student_name": "Jordan Lee", "student_email": "...",
 "template": {"path": "/abs/path", "commit": "sha"},
 "workspace": "/abs/work_dir/jordan-0924-1412", "repo": "/abs/.../toy", "origin": "/abs/.../origin.git",
 "config_dirs": {"tutor": "/abs/.home/jordan-0924-1412/a", "student": "/abs/.home/jordan-0924-1412/b"},
 "models": {"tutor": "" , "student": "", "reader": "opus"},
 "claude_version": "2.1.281", "sdk_version": "0.2.159", "pid": 12345, "host": "hostname",
 "env_stripped": ["CLAUDE_CODE_SESSION_ID", "..."],
 "started": "2026-09-24T14:12:03Z", "ended": null, "ended_by": null, "setup_seconds": 0.0,
 "session_ids": {"tutor": null, "student": null},
 "upstream": {"url": "", "local": null},          (set when the config key upstream_url is non-empty: the URL the template's setup types is rewritten to a local bare clone)
 "error": null,
 "scenario": {"names": ["uv-missing"], "settings": {"uv": "missing", "...": "..."}},
 "home": "/abs/work_dir/.home/<run-id>/home" | null,
 "tutor_sessions": ["uuid", "..."],                (every tutor session id, in order; a resumed one appears once)
 "restarts": [{"exchange": 4, "type": "exit|start|session|switch", "session": "uuid", "cwd": "...", "mode": "new|continue|picker|resume:<id>", "resumed": "uuid|null"}],
 "approvals": [{"exchange": 1, "type": "approval", "server": "name", "choice": "yes|yes_all|no", "forced": false}],
 "effort": {"tutor": {"asked": "low", "seen": ["low"]}, "student": {...}},   (seen: perTurnEffort in the session files)
 "world": {...},                                   (the world module's facts(), when it has one)
 "config": { ...the resolved config, every key, paths as strings... }}
```
`ended_by` is one of: `finished`, `left`, `max_turns`, `budget`, `timeout`, `error`, `student_silent`,
`student_loop`, `killed` (SIGTERM or Ctrl-C; the gate still runs), `crashed` (set by `report` when a run has
`status: running` and no live pid). `status` is `finished` for finished/left/max_turns/budget/student_silent/
student_loop and `failed` for error/timeout/killed. The student's file policy runs as an SDK PreToolUse hook (an
`allowed_tools` entry approves a tool before the permission callback sees it), with the callback as a catch-all.

## turns.jsonl

One JSON object per actor turn, in order. `exchange` counts student-then-tutor pairs from 1; the student's
turn is written first, then the tutor's.

```json
{"exchange": 3, "actor": "student|tutor", "session_id": "uuid",
 "t_start": "iso", "t_end": "iso", "seconds": 12.3,
 "text": "the actor's final text for the turn (all text blocks joined)",
 "tools": [{"name": "Bash", "input": "JSON string of the input, cut to 2000 chars", "result": "last 800 chars", "is_error": false}],
 "prompts": [{"tool": "Bash", "summary": "one line: the command or the file path", "decision": "allow|deny", "reason": "..."}],
 "hooks": [{"event": "SessionStart|PreToolUse|Stop|...", "ok": true, "output": "first 200 chars"}],
 "asks": [{"question": "...", "answer": "..."}],
 "result": {"total_cost_usd": 0.0123, "num_turns": 4, "duration_ms": 8100, "is_error": false, "subtype": "success",
            "usage": {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
            "model_usage": {"claude-x": {"inputTokens": 0, "outputTokens": 0, "cacheReadInputTokens": 0, "cacheCreationInputTokens": 0, "costUSD": 0.0}}},
 "model": "claude-haiku-4-5-20251001",
 "files_changed": ["WRITEUP.md"], "commits": [{"sha": "abc1234", "subject": "Part 1 done"}], "head": "abc1234",
 "slots": {"total": 3, "blank": 2, "filled_this_turn": ["Part 1 number"]},
 "finish_seen": false,
 "fabrication": {"fired": false, "rule": null, "retried": false},
 "narration": "",
 "stop": null}
```
- `prompts` are the tutor's permission prompts (the `can_use_tool` callback); on student turns they are the
  student's denied tool attempts.
- `result.total_cost_usd` is the SDK's running total for that session. Per-actor cost is the LAST value on
  that actor's lines, never a sum. `result.usage` and `result.model_usage` are copied as the SDK gives them
  (field names as delivered; the example shows the CLI's camelCase for model_usage).
- `files_changed`, `commits`, `head`, `slots` describe the repo at the end of this actor's turn, relative to
  the end of the previous turn (so they are attributable to this actor). `TRANSCRIPT.md` is excluded.
- `fabrication` (student lines only): whether the message looked like the student writing the tutor's side
  (a line starting "The assistant replied" / "Assistant:" / "Claude:", a 200-character echo of the tutor's last
  reply, or text after a `(leaves)` line), which rule fired, and whether the student was re-asked once.
- `narration` (student lines only): text the student model wrote before its own last tool call (talking to
  itself while editing); `text` is what came after it, which is what the tutor receives. When nothing came after
  the last tool call, `text` holds everything and `narration` is empty.
- `finish_seen` fires when the finish string is a whole line of a Bash result, or a whole line of the tutor's own
  text (bold or heading marks stripped); a Read of a README that quotes it must not end the run.
- Narration is split from the student's message only at a real tool call; a no-op command (`true`, `:`, `echo`,
  `sleep`) does not split, so a message written before a "wait" command still reaches the tutor.
- Slot shapes read by `facts.slots`: `**Label:** value`, `**Question?** value`, `**Label** (note): value`, a label
  with its answer on the lines below, and a bold label wrapped onto the next line.
- `stop` is null except on the last line, where it equals `ended_by`.
- `kind` (student lines, absent for a message to Claude): `approval` (answered Claude Code's start-up question),
  `terminal` (at the terminal while Claude Code was closed), `picker` (picked a conversation to resume), `side` (a
  world's side turn while the tutor worked, with `label`; it is written before the tutor turn it happened in).
- `event` (when something happened): `{"type": "exit"}`, `{"type": "start", "cwd", "args", "mode"}`,
  `{"type": "approval", "server", "choice", "forced"}`, `{"type": "resume_pick", "session", "offered"}`.
- `init` (a tutor session's first turn only): `{"mcp_servers": [...], "tools": n, "mcp_tools": {server: n}}` from
  the CLI's init message: which servers were connected and how many of their tools the tutor had.

## facts.json (computed only from turns.jsonl, run.json, gate.txt and the repo; never from memory)

```
run_id, persona, student_name, status, ended_by, exchanges,
minutes_wall, minutes_tutor (sum of tutor seconds / 60), minutes_student, setup_seconds,
cost_usd: {tutor, student, reader (from scorecard.json if present), total_student_side (= tutor)},
tokens: {tutor: {input, output, cache_read, cache_creation}, student: {...}}   (from the last model_usage per actor, summed over models)
windows: tutor cost / 20.0                                                    (WINDOW_USD constant, "assuming $20 per five-hour window")
hours_band: {"2min": h, "4min": h}  = minutes_tutor/60 + exchanges*m/60 + fixed_minutes/60
prompts: {total, by_tool: {Bash: n, ...}, denied: n}
hooks: {total, by_event: {SessionStart: n, ...}}, settings_loaded: bool|null (null when the template declares no hooks)
files_changed: {tutor: [...], student: [...]}, commits: {tutor: [...], student: [...]},
slots: {total, blank_at_start, blank_at_end, filled_by: {tutor: [...], student: [...]}},
parts: [{"part": 1, "first_exchange": 2, "slots_filled": 2, "slots_total": 2}],   (from slot labels under ## Part N)
gate: {"exit": 0|int|"timeout"|null, "tail": "last 10 lines"}, finish_exchange: int|null,
stalls: {"exchanges_without_progress": [5, 6], "longest": 2},   (no slot filled, no commit, no non-protected file changed by either actor)
tutor_left_repo: [ {exchange, path} ], suspicion: [ {exchange, sentence} ], student_saw_rules: [ {exchange, command} ],
student_bash: n, student_denied: n, empty_student_turns: n,
persona_drift: {early_median_words, late_median_words, ratio}, student_words_median: n,   (the old validity gate excluded ratios outside [0.3, 1.8]; reported, not judged)
student_wrote_tutor_side: {count, exchanges: [...]},
truncated_lines: n (turns.jsonl lines that did not parse); commits[].exchange is added; ended_by falls back to the last
line's stop, then to "crashed" when run.json says running and the recorded pid is not alive,
models: {tutor: "...", student: "..."}, sdk_version, claude_version,
note: "cost measured with a warm prompt cache; a real student pausing minutes between messages may pay more",
scenario (from run.json), restarts: {exits: [exchange], starts: [...], sessions: [...], count}, approvals: [...],
side_turns: [{exchange, label, seconds}], terminal_turns: [exchange],
tutor_sessions: [{exchange, session_id, mcp_servers, mcp_tools}]   (from each session's first init)
Words, drift, silence and fabrication count student messages only (no kind).
```

## transcript.md

Header: `# <run_id>` then a line with persona, template commit, models, started. Then per actor turn:

```
## Exchange 3 · student            (or · tutor)
<text>
> Edit WRITEUP.md                  (one line per tool call: name and the command or file; then the output tail, at most 20 lines, indented)
> [approved] Bash(uv run python part1.py)    (one line per permission prompt)
> [hook] SessionStart ok
> commit abc1234 Part 1 done · changed: WRITEUP.md
```

The tutor's reply as the STUDENT sees it is the same rendering with the output tail cut to 8 lines and without
the hook and commit lines (the student sees its terminal, not the harness's bookkeeping).

## Module interfaces (signatures the other modules import)

```python
# pilot/run.py
@dataclass(frozen=True) class Config: ...   # every pilot.toml key with its default, plus assignment_dir, runs_dir, template, work_dir as absolute Paths
def load_config(assignment_dir: Path) -> Config
def run_one(cfg: Config, persona: str, *, repo: Path | None = None, turns: int | None = None) -> Path   # returns the run directory
# pilot/facts.py
def slots(text: str, marker: str, part_heading: str) -> list[dict]       # [{"label","part","blank"}]
def load_turns(run_dir: Path) -> list[dict]
def render_turn(turn: dict, *, for_student: bool = False) -> str
def summarize(run_dir: Path, cfg: Config) -> dict                        # writes nothing
def write_facts(run_dir: Path, cfg: Config) -> Path                      # facts.json
def report(cfg: Config) -> str                                            # markdown table over runs (+ agreement)
def sheet(run_dir: Path, cfg: Config, initials: str) -> Path
# pilot/viewer.py
def build(cfg: Config) -> Path                                            # runs/viewer.html
# pilot/reader.py
async def read(run_dir: Path, cfg: Config) -> Path                        # scorecard.md (+ scorecard.json)
# pilot/cli.py
def main(argv: list[str] | None = None) -> int
# pilot/terminal.py (Claude Code's screens acted out), pilot/world.py (scenarios, Context, load_world),
# pilot/github.py (local GitHub), pilot/scripted.py (ScriptedStudent): each module's docstring is its interface.
def run_one(cfg, persona, *, repo=None, turns=None, scenario=None, student=None, tutor=None) -> Path
```

Constants, each defined once with a comment: `WINDOW_USD = 20.0`, `MINUTES_PER_EXCHANGE = (2, 4)`,
`STUDENT_TAIL_LINES = 8`, `TRANSCRIPT_TAIL_LINES = 20`, `STUDENT_MAX_TURNS = 12`, `LEAK_WORDS = ("sim", "pilot", "harness", "persona")`.
