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
  when there is one. On macOS the login is in the Keychain under a name tied to the config directory, so a
  per-run config directory is not logged in (confirmed on a Mac, Oct 2026): use the token. Save it in a file
  only you can read and name that file in `oauth_token_file` (for example `~/.config/activity-pilot/token`);
  pilot reads it into `CLAUDE_CODE_OAUTH_TOKEN` and redacts it from every record.
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
| `pilot run <assignment-dir> <persona> [--repo PATH \| --from-run RUN_ID] [--turns N] [--scenario S ...] [--rubric FILE]` | One run of `personas/<persona>.md` on a fresh copy of the template, on the repo at PATH, or on a copy of an earlier run (`--from-run`: its workspace, home folder and tutor settings, with every path rewritten to the new run); at most N exchanges (default `max_turns`); each `--scenario` is a preset name from `[scenarios]` or one `key=value` setting; `--rubric` is recorded for `pilot read` |
| `pilot read <assignment-dir> <run-id> [--rubric FILE]` | One reader call over a finished run, against the rubric given, else the one the run recorded, else `rubric.md`; writes `scorecard.md` and `scorecard.json` |
| `pilot report <assignment-dir>` | Recomputes facts for every run and prints one Markdown table, plus agreement over filled calibration sheets |
| `pilot view <assignment-dir>` | Writes `runs/viewer.html`, one self-contained page over every run |
| `pilot calibrate <assignment-dir> <run-id> --initials XX` | Writes a blank grading sheet, `runs/<run-id>/sheet-XX.md` |

To check a machine end to end: `uv run pilot run tests/toy jordan` (Haiku on both sides, about ten cents).

## The assignment repo

```
<assignment>-pilot/       private, one per assignment; never visible to the tutor
  pilot.toml
  personas/<name>.md      one sheet per persona, in the library's personas/FORMAT.md format
  personas/INVENTORY.md   optional: what the assignment demands, each persona placed on it (FORMAT.md)
  rubric.md               "- **ID** text" lines; the reader grades each; ends with **ONE_LEVER**
  runs/<run-id>/          records; commit these
```

| Key | Default | Meaning |
|---|---|---|
| `template` | required | path to the template checkout; `git archive HEAD` exported, commit recorded |
| `work_dir` | `/Users/Shared/hw-work` on macOS, `/var/tmp/hw-work` elsewhere | workspaces and config dirs, created readable by you only; refused if it contains sim, pilot, harness or persona, or if any folder above it holds files Claude Code would load as the tutor's own instructions (below) |
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
| `upstream_url` | `""` | when the template's setup adds an upstream remote by URL, that URL is rewritten to a local bare clone so fetches stay offline (`git remote -v` then shows the local path; `pilot/github.py` keeps GitHub URLs instead) |
| `oauth_token_file` | `""` | a file holding a `claude setup-token` token, read into `CLAUDE_CODE_OAUTH_TOKEN`; the token is redacted from every record |
| `repo_name` | `""` | the student's copy is `<work_dir>/<run-id>/<repo_name>`; empty means the template folder's name |
| `finish_pattern` | `""` | a regular expression a finish line must match in full (beside `finish_string`); in the tutor's own text a `**bold**` span may carry it |
| `slot_heading` | `""` | a regular expression for a heading that is a slot (group 1 is its label), e.g. `^### (.+)$`; its answer is the first paragraph below, blank when empty, the marker, or the marker and a `(note)` |
| `tutor_effort`, `student_effort`, `reader_effort` | `""` | the CLI's `--effort` (low, medium, high, xhigh, max); `run.json` `effort.seen` lists the levels the CLI wrote in each session file |
| `env_drop` | `[]` | host variables never passed to the actors, by name or `PREFIX*` (e.g. `UV_*` so a host package mirror does not leak in) |
| `tutor_setting_sources` | `["project"]` | the tutor's setting sources; add `"local"` for `.claude/settings.local.json`, where the CLI keeps server approvals and remembered permissions |
| `run_home` | false | each run's own home folder for both actors (`<work_dir>/.home/<run-id>/home`, with `Downloads/`, Claude Code in `~/.local/bin` as its installer puts it, `UV_CACHE_DIR` shared under `<work_dir>/.cache/uv`) |
| `run_path` | `[]` | the folders after `~/.local/bin` on the actors' PATH instead of the host's PATH |
| `approve_servers` | `[]` | `.mcp.json` servers whose start-up question the student answers before the first message and at each start while undecided (needs `"local"` in `tutor_setting_sources`) |
| `restarts` | false | the student may `/exit`; they are then at their terminal, where `claude` (a stand-in) starts Claude Code again and `/resume` reopens a conversation |
| `world` | `""` | the assignment's world module (`pilot/world.py` documents it), relative to the assignment directory |
| `tutor_sandbox` | false | Claude Code's own sandbox for the tutor's commands (macOS Seatbelt), set through the SDK's settings option, never in the repository: no command may read any home folder or another run; this run's workspace, home and settings folders and the shared caches stay readable and writable; network and local servers stay open; nothing is auto-approved, so permission prompts are unchanged. git commands run outside it (the sandbox never lets a command write `.git/config`, which `git remote` needs); reads outside the run still fail for them. The Read, Edit and Write tools get the same limits as deny rules. A refused read shows as "Operation not permitted" or "denied by sandbox". Needs `run_home` |
| `tell_date` | false | tell the student today's real date, so a sheet's story date does not contradict the tutor's clock |
| `[settings]`, `[scenarios.<name>]` | none | per-run settings with their defaults, and named presets of them; chosen with `--scenario`, recorded in `run.json`, given to the world |

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
- **`runs/viewer.html`** (`pilot view`): all runs on one offline page, each marked by how it ended, with its
  conversation, gate and writeup slots, scorecard, student (and its column of `personas/INVENTORY.md`, when there is
  one) and every field of `facts.json` and `run.json`. It also shows what restarts, worlds and the newer keys record:
  side turns and messages typed while Claude worked, the start-up question's answer, a ruled break where Claude Code
  closed or started again, `[world]` lines placed by time, background work, the continued run (`--from-run`, linked),
  the scenario, the rubric, the sandbox, cost per model, and a loud warning when the tutor loaded instruction files
  from outside its repository. Runs named in `runs/.viewignore` (one id or shell pattern per line, `#` comments)
  are left off the page.
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

## Keep the tutor's instructions to the template's

Claude Code reads instructions from every folder above the repository, not only from the repository: CLI 2.1.281
loads `CLAUDE.md`, `CLAUDE.local.md`, `.claude/CLAUDE.md`, `.claude/rules/`, `.claude/agents/`, `.claude/skills/`,
`.claude/commands/` and `.mcp.json` from each of them (checked with canary files; settings files above the project
are not read). A home folder usually holds `~/.claude/CLAUDE.md`, a person's global instructions, so runs under the
home folder gave the tutor those too. pilot refuses a `work_dir`, a `--repo` or a run whose repository has any of
these above it (`ancestor_instructions`), and `run.json` lists the instruction files the tutor actually loaded
(`tutor_instructions`, from the `instructions` entries in its session files), with any outside the repository under
`instructions_outside_repo`. `--from-run` copies of older runs drop such outside files from the earlier tutor's
saved conversations (`from_run.scrubbed`); words the tutor wrote about them in its replies stay. The student's
session reads no settings sources, so it loads none of these.

## Restarts, the start-up question, and the world

With `restarts`, a student message whose first line is `/exit` (or `/quit`) closes the tutor's CLI. The student's
next turns are at their terminal: their Bash, with a `claude` stand-in first on PATH. `claude mcp ...` (and
`--version`, `--help`) runs the real CLI with the tutor's settings folder, so `claude mcp reset-project-choices` and
`claude mcp get <server>` act on the tutor's state; a bare `claude` (also `cd <path> && claude`, `claude --resume`,
`claude -c`) starts Claude Code again with the PATH that terminal had. The first thing typed then picks the
conversation: `/resume` shows a picker of the earlier conversations started in that folder and reopens the one
picked (the SDK's resume); anything else starts a new one. A resumed CLI starts its MCP servers again.

With `approve_servers`, the student sees Claude Code's question for a new project server (CLI 2.1.281's wording;
the third option, "Continue without using this MCP server", is highlighted, so Enter declines) and the answer is
written to `.claude/settings.local.json` as the CLI writes it. A headless CLI connects an undecided server without
asking and honours a "no" only when it reads local settings. A scenario setting `approve` set to `yes` or
`decline` overrides the answer on the first start.

A world module (`world = "..."`) adds what the template's tools expect around them: tutor environment (a `BROWSER`
program, PATH entries), tools for the student (served in-process as the `laptop` MCP server), a paragraph in the
student's frame, student side turns while the tutor works, and notices shown before the student's next prompt.
`pilot/scripted.py` is a student that follows a script instead of a model, for probes and tests
(`run_one(..., student=...)`); `pilot/github.py` serves `https://github.com/<owner>/<repo>` from local bare
repositories through a git remote helper, so remotes keep their GitHub URLs.

Student turns that are not messages to Claude carry a `kind` (`approval`, `terminal`, `picker`, `side`); facts
count only messages for words, drift and silence.

## Student behavior

- **Real tools and a terminal view.** The student has its own editor and terminal (Read, Glob, Grep, Edit,
  Write, Bash) and sees each tutor reply as a terminal shows it, output cut to 8 lines. It can edit only the
  files its sheet's `edits:` line names; `CLAUDE.md`, `.claude/` and `TRANSCRIPT.md` are closed to its tools;
  its Bash is recorded, and a command naming the rule files is recorded as `student_saw_rules`.
- **No authorship instruction.** Nothing tells the student its words must be its own. Earlier harnesses said
  so and then saw no copying, which measured the instruction. Authorship is what a run measures.
- **Permission to stop.** The student may stop when tired, out of time, blocked, or satisfied, by writing
  `(leaves)`, so `ended_by: left` is a finding rather than a cap. A message that says something before its
  `(leaves)` line still goes to the tutor and gets one reply (so a closing line such as the checkpoint's is seen).
- **Typing while Claude works.** In a world's side turn, what the student types is sent to the tutor at once,
  as real Claude Code queues a message typed during a reply: the CLI shows it to the model at its next step
  (between tool calls), or answers it right after the reply (pilot waits a few seconds for that answer). If the
  reply has already ended, it is the student's next message. The tutor's turn lists it under `queued`.
- **Background work.** When a reply leaves work running (graders launched as background agents, a long command),
  pilot keeps reading until every task has ended and the CLI is quiet, so what Claude says when the work ends
  joins that reply (`background` on the tutor's turn). A real student could type meanwhile; here they wait.
- **Fabricated tutor turns detected and re-asked.** A student message that writes the tutor's side is re-asked
  once and recorded (`fabrication` per turn, `student_wrote_tutor_side` in facts).
- **Drift and fidelity reported per run.** `persona_drift` compares early and late message length; the
  reader's fidelity section says whether the student stayed within its sheet and, with a placement grid, names the
  rows it went above.
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
