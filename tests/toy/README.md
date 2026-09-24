# The toy assignment

A small assignment in the template contract's shape, for checking the library end to end on Haiku for a few
cents. Nothing here is course material.

| Path | What it is |
|---|---|
| `template/` | The template repo the tutor and student work in: `CLAUDE.md` (four tutor rules), `.claude/settings.json` (allowlist and hooks), `.claude/hooks/` (portable sh), `.claude/commands/status.md`, `README.md` (the student's brief), `WRITEUP.md` (three slots in two parts), `part1.py` (prints 385), `part2.py` (prints 25), `run_all.py` (the gate) |
| `pilot.toml` | `template = "template"`, Haiku on both sides, 4 exchanges, $1 cap |
| `personas/jordan.md` | One persona sheet |
| `rubric.md` | Three tutor rules to grade plus `ONE_LEVER` |

The hooks write `.hooklog` in the working copy: `SessionStart` and `Stop` append their event name, and the
`PreToolUse` hook on Bash refuses any command containing `rm ` (exit 2). `template/.gitignore` ignores
`.hooklog`, so a tutor's `git add -A` does not commit it.

## Exporting a template that is a subdirectory of a repo

`template/` is not a repo of its own; it is a subdirectory of the library's repo, and it must be committed
before a run can export it. Measured with git 2.43 on a scratch copy where the toy was committed at
`tests/toy/template/` (with an untracked `.hooklog` and `sims/` planted beside the tracked files):

| Command | Result |
|---|---|
| `git -C <repo-root> archive HEAD:tests/toy/template` | Correct: the 14 template entries, paths relative to the template |
| `git -C <template> archive HEAD` | Correct: git limits an archive run from a subdirectory to that subtree, with relative paths |
| `git -C <template> archive HEAD:tests/toy/template` | **Empty archive, exit 0.** Run from the subdirectory, git applies the subdirectory prefix a second time and finds nothing |
| `git -C <template> archive HEAD:./` | Empty archive, exit 0, for the same reason |
| `git -C <template> ls-files -z` | Correct: the 11 tracked files, paths relative to the template |

**Recommended: copy the files `git -C <template> ls-files -z` lists** (skipping any entry that is a directory,
which is a submodule), with `shutil.copy2` so modes survive, after refusing the export when
`git -C <template> status --porcelain --untracked-files=no -- .` prints anything. It is the simplest because:

- the same two calls work whether the template is a whole repo or a subdirectory, with no prefix arithmetic;
- there is no tar stream to extract, so no second tool and no silent empty-archive failure;
- the refusal check is needed anyway, and once it passes the listed files in the working tree equal `HEAD`;
- untracked files (`.hooklog`, `sims/`, `settings.local.json`) are never listed, which is the point of the export.

Record the commit with `git -C <template> rev-parse HEAD`. If `git archive` is preferred, use the plain
`git -C <template> archive HEAD` form, never `HEAD:<subdir>` from inside the subdirectory.
