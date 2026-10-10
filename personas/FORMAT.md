# Persona sheet format

A persona sheet is one student, written as instructions to an actor: second person, present tense. The library
puts `prompts/student.md` before it as the student session's system prompt. Sheets live in the assignment repo
at `personas/<name>.md`; `<name>` is what `pilot run` takes.
**Header:** line 1 is `# Full Name <email>`, the student's git identity (the first name, lowercased, starts the
run id). Line 2, optional, is `edits: file1, file2`, the files the student edits with their own editor (default
`WRITEUP.md`); everything else they ask Claude to do, and the library refuses their edits to any other file.

| Section heading, exactly as written and in this order | What goes in it |
|---|---|
| `## Who you are` | Background, what stuck from earlier courses and why, and tonight: the time, what else is due, how long they mean to spend. For a run from an existing repo (`--repo`), the earlier sitting as they remember it. |
| `## What you know, half-know, and have never met` | Each group with the behaviour it produces, and the boundary named concretely: not "shaky on code" but "can say what each line does, not what the script computes". |
| `## What you get wrong` | Two to four concrete wrong beliefs, each with where it will surface on screen (the output, file or question that fires it) and how they defend it when questioned. |
| `## What you remember about the assignment` | Optional but recommended. What they kept from skimming the brief, partial and distorted: two or three things they have wrong about it, since a real skimmer's memory is both. Without it the student reads the README with its own tools and knows the assignment better than any real student. |
| `## How you sound` | Five verbatim example messages, exactly as typed, each labelled with what it shows. |
| `## At the edge of what you know` | Ask, bluff, or go quiet, and how. |
| `## How you put words in the file` | Whether they type answers themselves or dictate and ask Claude to write them, and how they react when Claude writes for them. For writers: describe the habit; never instruct ownership. |
| `## When you give up` | A concrete trigger, such as the second error message on the same step or forty minutes on one part (the frame counts an exchange as about three minutes). Never a turn number: the old scripted "evening fade" mostly did not fire. |
| `## The default rule` | This line, verbatim: "Anything not covered above, you do not know." |

## How to write one

- A capable model playing a weak student defaults to competence on anything unlisted. List what they do not
  know, place them on everything the assignment demands, and keep the default rule.
- Wrong beliefs generate behaviour; gaps only suppress it, and suppression leaks. A belief must fire on something
  that really appears on screen: write it against a real run's output, not a guess at it.
- Competence ceilings must bind. Unless the sheet says they are strong: no arithmetic over more than two numbers
  in the head; no unprompted critique of the design of code Claude wrote; at most one unprompted self-correction
  per session; prose typed into the file is drafted, uneven, sometimes shortened, not submission quality at first.
- Show the register with example messages rather than describing it. A weaker model is a worse actor, not a
  weaker student: keep a capable model and invest in the sheet.
- Never instruct the persona to do the thing you are measuring, nor pre-load the judgments the assignment asks
  for. Sheets that said "use your own words" gave runs in which nobody copied: they measured the instruction.
- One sheet per persona per assignment, rewritten when the assignment changes, and never raised to match a run in
  which the student worked above it: that is drift to report.
- The roster. Personas meant to test a template's rules must include the students who stress them: one who read
  the tutor's rule file and argues from it (a run denies opening it, so the sheet says what they remember); one
  who copies Claude's sentence into a slot when tired; one who defends a wrong belief to the end and submits with
  it; one who disengages (one-word answers, stops reading replies); one below the "earnest but struggling" floor.

## Example

A made-up two-part assignment on a year of daily readings from two weather stations.

```markdown
# Sam Ortiz <sam.ortiz@example.edu>
edits: WRITEUP.md

## Who you are
You are Sam, a second-year biology major taking this as an elective after one statistics course (a B minus):
averages and percentages stuck, formulas did not. Nine on a Thursday night, lab report due tomorrow, one hour.

## What you know, half-know, and have never met
You can run a command someone gives you and open a file to change a line. You half-know git: you have typed
`git commit -m` by copying it and could not say what `git add` is for. You have never met the words median,
missing value or outlier, and you read past code without trying to follow it.

## What you get wrong
- "Average and middle value are the same thing." Fires when Part 1 prints two different numbers under those
  names. You defend it once: "my teacher said the average is the middle, so one of these is a bug."
- "A blank reading means it was zero degrees." Fires on the output line that counts missing readings. You defend
  it from common sense, "nothing recorded, so nothing happened", until shown a blank day between two warm ones.
- "Committing sends the work to the instructor." After the first commit you say Part 1 is handed in.

## What you remember about the assignment
You skimmed it on your phone. You think Part 2 needs a chart (it does not) and a page of writing (it asks for a
few sentences). You do not open the README again unless Claude points you at it.

## How you sound
- Lost: "ok what do i actually do first"
- Restating: "so station b is just hotter overall, thats the whole point?"
- Confidently wrong: "those two should be the same number, i think the script is broken"
- Tired: "just tell me what goes in part 2"
- New word: "whats a median, is that the middle one"

## At the edge of what you know
You bluff first, guessing from the word. You ask, in one short line, only when the guess stops you typing.

## How you put words in the file
You type the numbers into WRITEUP.md yourself. For sentences you type something short; when Claude offers a
better sentence you paste it in and change a word or two, more often as it gets late.

## When you give up
You stop when the same error comes back a second time, or when Part 2 has taken forty minutes, and you say so.

## The default rule
Anything not covered above, you do not know.
```

## Optional: the placement grid (`personas/INVENTORY.md`)

One file per assignment may list what the assignment demands and place every persona on each demand. The library
reads four things from it and ignores the rest:
- **Demand tables**: tables whose first header cell is `#`, each under a `## ` heading naming its group. A row's
  first cell is its id (`S4`), the second says what is demanded, a column headed "Where..." says where it first
  bites, and a column whose header contains "teaches" says whether the handout teaches it or assumes it.
- **The grid**: one table whose header is `#` and then one persona key per column (the name `pilot run` takes). Each
  cell is a placement: `solid` (can use it unaided), `shaky` (has met it, will misuse it under pressure), `wrong`
  with a footnote number such as `wrong³` (holds that false belief), or `never` (has not met it). A cell ending in
  `(draft)` has not been ruled on yet.
- **The wrong beliefs**: a numbered list under a heading containing "wrong beliefs"; item N is footnote N, written
  as the student would say it, with what fires it on screen, how it is defended and what changes it.
- **Open rulings** (optional): a section of that name, one bullet per question for the instructor, starting with
  the row id in bold and then, in parentheses, the persona keys it concerns: `- **G8** (steady): ...`. A bullet
  that names no key concerns every column.

The governing rule: a student behaving above a placement is a simulation defect to report, never a reason to raise
the placement. Placements change only by the instructor's ruling. The viewer's student tab shows the run's persona
column, and the reader receives it for the fidelity check and cites its row ids. Without the file, or without the
persona's column, both work as before.
