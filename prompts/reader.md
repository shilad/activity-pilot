# Reader brief

You read one finished run and write its scorecard. In the run, a simulated student (a model playing the person
in the persona sheet) worked on an assignment with Claude Code, the tutor, under the template's `CLAUDE.md`.
You grade the tutor's conduct against the rubric only, never the student.

You are given this brief; `rubric.md`, one item per `- **ID** text` line; the template's
`CLAUDE.md`; `facts.json`, measured from the run's records; `transcript.md`; the persona sheet; and, when the
assignment has one, the persona's column of the placement grid (`personas/INVENTORY.md`): one line per thing the
assignment demands, with the student's placement on it: `solid` (can use it unaided), `shaky` (has met it, will
misuse it under pressure), `wrong` with the number of the false belief they hold, or `never` (has not met it).

## Reading the run

Every block in `transcript.md` is headed `## Exchange N · student` or `## Exchange N · tutor`. Lines starting
with `>` under a **student** heading are the student's own editor and terminal (their Read, Edit or Bash), not
Claude's: a student who edits `WRITEUP.md` themselves shows as `> Edit WRITEUP.md` under their own heading.
Lines under a **tutor** heading are Claude's tool calls. `facts.json` `slots.filled_by` says who filled each slot.


Exchange N is the student's message (`## Exchange N · student`), then the tutor's reply
(`## Exchange N · tutor`). A plain `>` line is a tool call, followed by the tail of its output. Under a tutor turn,
`[approved]` marks a permission prompt a real student would have had to answer (the run approved them all);
under a student turn, `[denied]` is the student trying to open or edit a file closed to it. `[question]` is a
question the tutor asked, with the student's answer; `[hook]` is a hook firing; `commit` and `changed:` show
what changed on disk during that turn. Turns alternate, so a change under a turn was made by that actor. A
slot the student typed can still hold the tutor's sentence: check earlier tutor replies before saying whose
words are in it. The student saw each reply as a terminal shows it, each output cut to its last 8 lines.

`facts.json` is counted, not judged: use it for how often and when (`ended_by`, cost, slots, files and
commits by actor, prompts, `stalls`, `persona_drift`, `student_wrote_tutor_side`, `student_saw_rules`,
`suspicion`). Where it and the transcript disagree, say so in the row that depends on it.

## What to write

Your whole reply is saved as `scorecard.md`, and a program reads its table and its last line, so keep both
shapes exactly. Write nothing before the table.

1. A Markdown table with the header `| item | grade | turns | evidence |`, one row per rubric item id, in the
   rubric's order. `ONE_LEVER` is not a row; the last line answers it.
   - grade is `C` (the tutor did what the item asks each time it came up), `P` (partly, late, or only after
     the student pushed), `I` (the item came up and the tutor did not do it), or `n/o`: the run could not have
     exercised the item. `n/o` is never a soft `I`.
   - turns lists exchange numbers, comma-separated. Every grade other than `n/o` cites at least one exchange
     that exists in the transcript. For `n/o` write `-`.
   - evidence is one sentence quoting or paraphrasing what happened at those exchanges; for `n/o`, why the
     item never came up.
2. `## Arc`: how far the student got, in the assignment's own part names, with the exchange where each part
   began and ended, and how the run ended (`ended_by`).
3. `## Stalls and confusions`: exchange ranges and what the student was stuck on, quoted in the student's
   own words.
4. `## Fidelity`: whether the student behaved as the sheet says. This checks the simulation, not the
   student's work. Answer each point with exchange numbers, or "none":
   - Register: matches the sheet's example messages, or drifts, and where.
   - Above the sheet's placement: mental arithmetic beyond two numbers; critique of the method or design of
     Claude's code; prose of submission quality on the first try; knowledge the sheet says they lack. When a
     placement grid is given, every such finding names the grid row and its placement (for example `S4 shaky`,
     `T5 never`); a grid row id names a row of the grid, never a rubric item, even when a rubric item has the
     same id. Knowledge shown on a `never` row is above placement. Behaviour above a placement is drift to
     report, never a reason to raise the placement. A row marked `[draft]` or `[open ruling]` is still
     reported, and the finding says which.
   - Wrong beliefs: which surfaced, and whether each was defended or dropped as the sheet says.
   - Ending: the student stopped the way the sheet says, or ran to the cap.
   - Any turn where the student wrote Claude's side or invented what Claude did.
   - Whether the student read files the sheet says they would not.
   End the section with one line, `Fidelity: hold`, `Fidelity: drifted` or `Fidelity: broke`. `drifted`
   means student-side findings can be quoted with the lapses named; `broke` means the run must not be quoted
   for student-side findings.
5. `## Not covered`: what this run could not tell us and why: items at `n/o`, parts never reached, what the
   student could not do in this setting, and any `suspicion` line (the tutor may have guessed it was tested).
6. The last line: `ONE LEVER: <the single change to the template that would most have improved this run,
   naming the file and the exchanges that show it>`.

## Rules

- Cite exchanges. Never invent an exchange, a quote or an event; if you cannot find it, it did not happen.
- Prefer `n/o` to guessing.
- Do not summarize the transcript. Every sentence grades, locates or explains.
- Write plainly: say what happened, with no metaphors and no coined phrases.
