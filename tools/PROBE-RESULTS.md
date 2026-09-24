# What the live toy runs verified (Sep 24, 2026)

The plan's step 1 was a probe script answering eight questions about the Claude Agent SDK before the run loop
was built. The probe's agent was cancelled; the questions were answered instead by the run loop's own live toy
runs (`tests/toy`, Haiku on both sides, Claude Code 2.1.281, claude-agent-sdk 0.2.159) in a Linux cloud
container. Total spend about $0.60. Items marked "not verified" still need a run on the instructor's Mac.

| # | Question | Answer | Evidence |
|---|---|---|---|
| a | Does the tutor get the `claude_code` preset and the template's project settings? | Yes. The init message lists the CLI's full tool set (Task, Skill, AskUserQuestion included); SessionStart, PreToolUse and Stop hooks from the toy's `.claude/settings.json` fired in exchange 1. | `tests/toy/runs/jordan-0924-1833/turns.jsonl`, tutor line 1: `hooks` = SessionStart, PreToolUse, Stop; `facts.json` `settings_loaded: true` |
| b | Preset proven by first-turn token size (preset vs none) | Not measured as a pair. The preset run's tutor tokens over three exchanges were 1,001 input plus 11,255 cache-creation plus 280,473 cache-read; a no-preset control was not run. | `facts.json` `tokens.tutor` |
| c | Hook events arrive through the SDK | Yes: `HookEventMessage` with `subtype == "hook_response"`; recorded per turn. The toy's hooks wrote `.hooklog`. | same run, `hooks` on tutor lines |
| d | Permission callback fires for non-allowlisted commands and not for allowlisted ones | Yes. `uv run python part1.py` (allowlisted) never reached the callback; `python3 -c ...` and `mkdir` did and were approved with the suggested rule, which the CLI wrote to `.claude/settings.local.json`. `echo hello` is auto-approved by CLI 2.1.281 and never prompts, so it is a bad probe command. | run-loop agent's probe runs (scratchpad) |
| e | Cost and usage fields | `ResultMessage.total_cost_usd` is a running total per session (0.004 → 0.015 → 0.022 on the student's three turns); `usage` is per turn; `model_usage` is keyed by served model with camelCase token fields and is cumulative. Facts take the last value per actor. | `turns.jsonl` `result` fields |
| f | AskUserQuestion routed to the student | Yes: the callback runs one student turn and returns `PermissionResultAllow(updated_input={..., "answers": {question: answer}})`; the CLI echoed the answer into the tutor's next text. | run-loop agent's live probe |
| g | Slash command through `query()` | The toy's `/status` command expanded and ran. | run-loop agent's live probe |
| h | Trust entry shape | `.claude.json` with `hasCompletedOnboarding: true` and `projects.<repo path>.hasTrustDialogAccepted: true` in the per-run config dir; `run.log` never carried "has not been trusted". | every toy run's `run.log` |
| i | Minimal environment passthrough in this container | Empty: with every `CLAUDE*` and `ANTHROPIC_*` variable stripped, a nested `claude` still authenticated through the container's proxy. The default `env_keep` stays `CLAUDE_CODE_OAUTH_TOKEN`, `ANTHROPIC_BASE_URL`. Fifty names are stripped per run; no run reused the parent's session id. | `run.json` `env_stripped` (50 names) |
| j | Session JSONL lands under the per-run config dir | Yes, under `<work_dir>/.home/<run-id>/a/projects/` and `.../b/projects/`. | workspace listing |
| — | Student file policy | An `allowed_tools` entry approves the tool before `can_use_tool` runs, so the policy is an SDK `PreToolUse` hook; denials read "PreToolUse:Read hook error: You have never opened that." The student's tool list is exactly Bash, Edit, Glob, Grep, Read, Write. | run-loop agent's live probe |
| — | Kill and crash | `kill -9`: completed turns on disk, `run.json` left `running`, `report` shows `crashed`; one orphaned `claude` child exited on its own within about 18 s. SIGTERM: the gate runs and `run.json` says `failed` / `killed`. | runs `jordan-0924-1836`, `jordan-0924-1837` |
| — | Finish rule | A tutor Read of the README, which quotes the finish string, ended a run in exchange 1; the rule now requires the string as a whole line of a Bash result. | run `jordan-0924-1832` |

Not verified here: macOS Keychain login from a per-run config dir; `shared_config` against a real host config;
`upstream_url` with a template whose setup adds the remote (HW1 will be the first); a `setup` command; the
`student_loop` and `budget` stops; a live fabrication trigger.
