# activity-pilot

`pilot` runs a simulated student through an assignment: a Claude model plays the student a persona sheet
describes and works with real Claude Code, the tutor, in a fresh copy of the assignment's template under the
template's own rules, permissions and hooks. Every turn is recorded as it happens, and each run is measured:
minutes, tokens, cost, permission prompts, who changed which file, how far the student got, and whether the
student stayed in character. A second model then reads the run and grades the tutor against the assignment's
rubric, citing exchanges.

## Install

```sh
uv sync --extra dev                                     # this repo: the library, `pilot`, and pytest
uv add git+https://github.com/<owner>/activity-pilot   # an assignment repo, from git
uv add --editable ../activity-pilot                     # an assignment repo, while developing the library
```

Run commands as `uv run pilot ...` (Python 3.11 or later). The pinned `claude-agent-sdk` 0.2.159 ships its own
`claude` 2.1.281 and prefers it to any on your PATH, so pinning the SDK pins the CLI; `run.json` records both.
TODO: `prompts/` sits outside the `pilot` package, so a git install does not ship it yet and `pilot run` falls
back to a built-in student frame; until the wheel includes it, use the editable path dependency.

## Authentication

Runs use your Claude subscription and count against its included usage; overflow is billed to credits only if
extra usage is on for the account.

- **Laptop:** log in to `claude` as usual; pilot links each run's config directories to your credentials file
  when there is one. On macOS the login is in the Keychain, which a per-run config directory cannot see, so use
  the token. TODO: confirm with the probe on a Mac.
- **Scripts and containers:** `claude setup-token` prints a token that authenticates with your subscription.
  Export it as `CLAUDE_CODE_OAUTH_TOKEN`, which `env_keep` passes through. Last resort: `shared_config = true`.
- **API keys are refused:** `pilot run` will not start while `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` is
  set. **Never bare mode:** it never reads subscription credentials; the SDK does not use it; do not add it.

Every other `CLAUDE*` and `ANTHROPIC_*` variable is stripped (names recorded in `run.json`), so a run started
inside a Claude Code session does not reuse it. In a Claude Code cloud container, authentication goes through
`ANTHROPIC_BASE_URL`, which is kept.

## Commands

| Command | What it does |
|---|---|
| `pilot run <assignment-dir> <persona> [--repo PATH] [--turns N]` | One run of `personas/<persona>.md` on a fresh copy of the template, or on the repo at PATH; at most N exchanges (default `max_turns`) |
| `pilot read <assignment-dir> <run-id>` | One reader call over a finished run; writes `scorecard.md` and `scorecard.json` |
| `pilot report <assignment-dir>` | Recomputes facts for every run and prints one Markdown table, plus agreement over filled calibration sheets |
| `pilot view <assignment-dir>` | Writes `runs/viewer.html`, one self-contained page over every run |
| `pilot calibrate <assignment-dir> <run-id> --initials XX` | Writes a blank grading sheet, `runs/<run-id>/sheet-XX.md` |

To check a machine end to end: `uv run pilot run tests/toy jordan` (Haiku on both sides, about ten cents).

## The assignment repo

```
<assignment>-pilot/       private, one per assignment; never visible to the tutor
  pilot.toml
  personas/<name>.md      one sheet per persona, in the library's personas/FORMAT.md format
  rubric.md               "- **ID** text" lines; the reader grades each; ends with **ONE_LEVER**
  runs/<run-id>/          records; commit these
```

| Key | Default | Meaning |
|---|---|---|
| `template` | required | path to the template checkout; `git archive HEAD` exported, commit recorded |
| `work_dir` | `~/hw-work` | workspaces and config dirs; refused if it contains sim, pilot, harness or persona |
| `setup` | `""` | command run in the repo before exchange 1, timed; empty means the tutor does it |
| `gate` | `uv run python run_all.py` | run once at the end with a timeout |
| `finish_string` | `YOU ARE FINISHED!` | matched in untruncated tool results and gate output only |
| `writeup`, `slot_marker`, `part_heading` | `WRITEUP.md`, `XXXX`, `^## Part (\d+)` | slot convention |
| `max_turns` | 40 | exchanges; never passed to the SDK's `max_turns` |
| `max_usd` | 15 | run cap on tutor plus student by last totals; also `max_budget_usd` per client |
| `turn_timeout_s` | 1800 | per actor turn, and for setup and gate |
| `fixed_minutes` | 15 | minutes the record cannot see |
| `tutor_model`, `student_model` | `""` (CLI default) | served model recorded from the init message |
| `reader_model` | `opus` | |
| `student_bash` | true | whether the student session has Bash |
| `shared_config` | false | auth fallback: both sessions use the host `~/.claude`; trust written there by rename and recorded |
| `env_keep` | `["CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_BASE_URL"]` | `CLAUDE*` and `ANTHROPIC_*` variables passed through to the actors; everything else in those families is stripped |
| `upstream_url` | `""` | when the template's setup adds an upstream remote by URL, that URL is rewritten to a local bare clone so fetches stay offline |

The smallest `pilot.toml` is `template = "<path>"`; a relative path is taken from the assignment directory, as
in `tests/toy/pilot.toml`. The template may be a subdirectory of a larger repo, but it must be committed: only
tracked files are exported, and a run is refused while tracked files have uncommitted changes.

**The template contract.** A `CLAUDE.md` for the tutor; `.claude/settings.json` with the permission allowlist
and hooks; a `run_all.py` gate; `WRITEUP.md` with `**Label:** XXXX` slots under `## Part N`; a finish string
printed by the gate; hooks that use `CLAUDE_CONFIG_DIR` and their own `transcript_path` rather than globbing
`~/.claude`; no simulation material in the repo. A run is refused if the writeup has no parts or slots.

## What a run writes, and how to read it

The student's clone is `<work_dir>/<run-id>/<template-name>/`: the template's tracked files, `git init` under the
persona's name and email, one commit, and a bare `origin.git` beside it. Config directories are
`<work_dir>/.home/<run-id>/a` (tutor) and `b` (student, reader). Nothing under `work_dir` is deleted. In the
assignment repo, `runs/<run-id>/` holds `run.json`, `turns.jsonl` and `transcript.md` (appended per turn),
`run.log`, `gate.txt`, `facts.json`, and later `scorecard.*` and `sheet-XX.md`; `RECORDS.md` defines each field.

- **`transcript.md`**: exchange N is the student's message, then the tutor's reply with one `>` line per tool
  call and its output tail, `[approved]` per permission prompt, `[hook]` lines, and the turn's commit and files
  changed. Follow a live run with `tail -f runs/<run-id>/transcript.md`.
- **`facts.json`**: counted, never judged. `ended_by` is `finished` (the finish string appeared), `left` (the
  student stopped), `max_turns`, `budget`, `timeout`, `error`, `student_silent`, `student_loop` or `crashed`.
  Also minutes, cost, tokens, windows, hours band, prompts, hooks, files, slots and commits by actor, parts by
  exchange, stalls, `tutor_left_repo`, `suspicion`, `student_saw_rules`, `persona_drift`, `student_wrote_tutor_side`.
- **`runs/viewer.html`** (`pilot view`): all runs on one offline page, with tool calls, prompts, hooks and facts.
- **`scorecard.md`** (`pilot read`): each rubric item graded C, P, I or n/o with its exchanges; the arc;
  stalls; a fidelity check on the student ending `Fidelity: hold | drifted | broke`; what the run could not
  show; and a `ONE LEVER:` line. Do not quote a `broke` run for anything the student did.

## Starting mid-assignment, and returning students

Runs start from a fresh template. `--repo` runs in the repo you give it, in place, so to start later, copy an
earlier run's workspace, reset the copy to the commit you want (`head` on each `turns.jsonl` line is the commit
at the end of that turn), point its `origin` at the copy's own bare repo, and pass it with `--repo`.
For a student coming back the next day, give them a sheet whose `## Who you are` describes the earlier sitting
as they remember it; the tutor is a new session that knows only what it can read in the repo.

```sh
cp -a ~/hw-work/jordan-0924-1412 ~/hw-work/jordan-b
git -C ~/hw-work/jordan-b/<template-name> reset --hard <sha>
git -C ~/hw-work/jordan-b/<template-name> remote set-url origin ~/hw-work/jordan-b/origin.git
uv run pilot run . jordan --repo ~/hw-work/jordan-b/<template-name>
```

The tutor sees this path, so a path containing sim, pilot, harness or persona is refused.

## Sweeps, stopping, calibration, cost

**Sweeps:** `printf 'jordan\nsam\n' | xargs -P 2 -I{} pilot run <assignment-dir> {}`. Keep to `-P 2` on one
subscription; a rate limit ends a run as `error` with the message text.

**Stopping a run:** `kill -TERM <pid>`, with the `pid` from `runs/<run-id>/run.json`, then `pkill -TERM -P <pid>`
for the `claude` processes it started. `pilot run` does not catch SIGTERM, so the kill skips the end-of-run
gate, and once the parent has exited its children belong to init and `pkill -P` finds none: note them with
`pgrep -P <pid>` before the kill and end them by pid. Completed turns stay on disk; `report` marks the run
`crashed`.

**Calibration:** `pilot calibrate` writes a blank sheet with one row per rubric item. Fill it blind, from
`transcript.md`, before `pilot read`. `pilot report` then prints percent agreement per item between every pair
of people and between each person and the reader.

**Cost** is measured with a warm prompt cache, because the simulated student answers in seconds; a real student
taking minutes between messages may pay more. Windows are tutor USD / 20 ($20 per five-hour window, a rule of
thumb); the hours band is tutor minutes plus 2 or 4 minutes per exchange plus `fixed_minutes`.

## Student behavior

- **Real tools and a terminal view.** The student has its own editor and terminal (Read, Glob, Grep, Edit,
  Write, Bash) and sees each tutor reply as a terminal shows it, output cut to 8 lines. It can edit only the
  files its sheet's `edits:` line names; `CLAUDE.md`, `.claude/` and `TRANSCRIPT.md` are closed to its tools;
  its Bash is recorded, and a command naming the rule files is recorded as `student_saw_rules`.
- **No authorship instruction.** Nothing tells the student its words must be its own. Earlier harnesses said
  so and then saw no copying, which measured the instruction. Authorship is what a run measures.
- **Permission to stop.** The student may stop when tired, out of time, blocked, or satisfied, by writing
  `(leaves)`, so `ended_by: left` is a finding rather than a cap.
- **Fabricated tutor turns detected and re-asked.** A student message that writes the tutor's side is re-asked
  once and recorded (`fabrication` per turn, `student_wrote_tutor_side` in facts).
- **Drift and fidelity reported per run.** `persona_drift` compares early and late message length; the
  reader's fidelity section says whether the student stayed within its sheet.
- **The roster.** Personas meant to test a template's rules must include the students who stress them;
  `personas/FORMAT.md` lists them and says how to write a sheet the student stays within.

## Design notes

- The tutor is real Claude Code: the `claude_code` system prompt preset and project settings only, so it gets
  the template's `CLAUDE.md`, permissions, hooks and skills and nothing from the host.
- Permission prompts are counted by a callback. With no allowed-tools override, the template's allowlist is the
  only auto-approval; every prompt a student would see is recorded and answered yes.
- The student's edits are attributed by whose turn it was: turns alternate, so whatever changed on disk during
  a turn belongs to that actor. No command is parsed.
- Records are appended and fsynced after every turn, so a crash loses one turn.
- Nothing course-specific is in the library: `prompts/student.md` (the student frame), `prompts/reader.md` (the
  reader's brief) and `personas/FORMAT.md` are generic; everything else belongs to the assignment repo.

Tests: `uv run pytest` is offline; `LIVE=1 uv run pytest` adds a three-exchange toy run on Haiku, about ten cents.
