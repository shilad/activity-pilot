"""One model call reads a finished run against the assignment's rubric and writes scorecard.md and scorecard.json."""
from __future__ import annotations

import hashlib, json, os, re  # noqa: E401
from pathlib import Path

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, query

from . import inventory
from .run import OTHER_TOOLS, STUDENT_TOOLS, clean_env

ITEM_RE = re.compile(r"^- \*\*([A-Za-z][A-Za-z0-9_]*)\*\*")  # a rubric item line: - **ID** text
ROW_RE = re.compile(r"^\|\s*([A-Za-z][A-Za-z0-9_]*)\s*\|([^|]*)\|([^|]*)\|(.*?)\|?\s*$")  # item | grade | turns | evidence
GRADES = {"C": "C", "P": "P", "I": "I", "N/O": "n/o", "N-O": "n/o", "N.O": "n/o", "NO": "n/o"}
RETRY = "Your scorecard was missing: {missing}. Write the whole scorecard again, complete, in the required format."


def brief() -> str:
    here = Path(__file__).resolve().parent
    for path in (here / "prompts" / "reader.md", here.parent / "prompts" / "reader.md"):
        if path.exists():
            return path.read_text(encoding="utf-8")
    raise FileNotFoundError("prompts/reader.md is missing from the pilot package and the repository")


def rubric_items(text: str) -> list[str]:
    """Item ids from `- **ID** text` lines. ONE_LEVER is the scorecard's final line, not a table row."""
    return [m.group(1) for line in text.splitlines() if (m := ITEM_RE.match(line)) and m.group(1) != "ONE_LEVER"]


def rules_file(run: dict, cfg) -> Path:
    """The tutor's rules as this run had them: CLAUDE.md in the run's repository (copied from the template when the
    run started), else the template's CLAUDE.md as it is now (the run's folder is gone, or an older run.json)."""
    repo = run.get("repo")
    if repo and (Path(repo) / "CLAUDE.md").is_file():
        return Path(repo) / "CLAUDE.md"
    return Path(cfg.template) / "CLAUDE.md"


def materials(run_dir: Path, cfg, run: dict, rubric_file: Path | None = None) -> tuple[str, list[str]]:
    """The user message: the rubric (`rubric_file`, else rubric.md), the tutor's rules as the run had them, the persona
    sheet (and the persona's column of the placement grid, when personas/INVENTORY.md has one), the facts and the
    transcript."""
    rubric = (rubric_file or cfg.runs_dir.parent / "rubric.md").read_text(encoding="utf-8")
    persona = run_dir / "persona.md"  # the sheet as the run was given it; older runs fall back to the live sheet
    if not persona.exists():
        persona = cfg.runs_dir.parent / "personas" / f"{run.get('persona', '')}.md"
    rules = rules_file(run, cfg)
    parts = [("rubric.md", rubric), ("CLAUDE.md (the tutor's rules)", rules.read_text(encoding="utf-8")),
             ("persona sheet", persona.read_text(encoding="utf-8") if persona.exists() else "(missing)")]
    key = run.get("persona")
    if (grid := inventory.column(cfg.runs_dir.parent, key)) is not None:
        parts.append((f"placement grid for this persona ({inventory.PATH}, column {grid['key']})",
                      inventory.as_text(grid)))
    parts += [("facts.json", (run_dir / "facts.json").read_text() if (run_dir / "facts.json").exists() else "{}"),
              ("transcript.md", (run_dir / "transcript.md").read_text(encoding="utf-8"))]
    return "\n\n".join(f"===== {name} =====\n{body}" for name, body in parts), rubric_items(rubric)


def parse(text: str, ids: list[str]) -> dict:
    items, seen = [], set()
    for line in text.splitlines():
        m = ROW_RE.match(line)
        if m and m.group(1) in ids and m.group(1) not in seen:
            grade = GRADES.get(m.group(2).strip().upper(), m.group(2).strip())
            items.append({"id": m.group(1), "grade": grade, "turns": [int(n) for n in re.findall(r"\d+", m.group(3))],
                          "evidence": m.group(4).strip()})
            seen.add(m.group(1))
    fid = re.search(r"^Fidelity:\s*(hold|drifted|broke)", text, re.M | re.I)
    lever = re.search(r"^ONE[ _]LEVER:\s*(.+)$", text, re.M | re.I)
    missing = [i for i in ids if i not in seen] + ([] if lever else ["the ONE LEVER line"]) + \
        ([] if fid else ["the Fidelity line"])
    return {"items": items, "fidelity": fid.group(1).lower() if fid else None,
            "one_lever": lever.group(1).strip() if lever else None, "missing": missing}


async def read(run_dir: Path, cfg, rubric: str | None = None) -> Path:
    """Write scorecard.md (the reader's text) and scorecard.json (its table, parsed). One retry when incomplete.
    The rubric is `rubric` (a file in the assignment directory), else the one the run names, else rubric.md."""
    from .facts import rubric_path
    run = json.loads((run_dir / "run.json").read_text())
    rubric_file = rubric_path(run_dir, cfg, rubric)
    env, _ = clean_env(cfg)
    os.environ.clear()
    os.environ.update(env)
    config_dir = (run.get("config_dirs") or {}).get("student")
    opts = ClaudeAgentOptions(system_prompt=brief(), setting_sources=[], allowed_tools=[], permission_mode="default",
                              disallowed_tools=OTHER_TOOLS + STUDENT_TOOLS + ["Bash"], max_turns=1,
                              model=cfg.reader_model or None, effort=getattr(cfg, "reader_effort", "") or None,
                              max_budget_usd=cfg.max_usd, cwd=str(run_dir),
                              env={"CLAUDE_CONFIG_DIR": config_dir} if config_dir else {})
    text, ids = materials(run_dir, cfg, run, rubric_file)
    total, model, prompt = 0.0, None, text
    for attempt in range(2):
        out = []
        async for msg in query(prompt=prompt, options=opts):
            if isinstance(msg, AssistantMessage):
                out += [b.text for b in msg.content if isinstance(b, TextBlock)]
                model = msg.model or model
            elif isinstance(msg, ResultMessage):
                total += msg.total_cost_usd or 0.0
                if msg.is_error:
                    raise RuntimeError(f"reader call failed: {msg.subtype}: {msg.result or msg.errors}")
        card = "\n".join(out).strip() + "\n"
        parsed = parse(card, ids)
        if not parsed["missing"]:
            break
        prompt = text + "\n\n" + RETRY.format(missing=", ".join(parsed["missing"]))
    (run_dir / "scorecard.md").write_text(card, encoding="utf-8")
    rubric_sha = hashlib.sha256(rubric_file.read_bytes()).hexdigest()
    rules = rules_file(run, cfg)
    result = {"cost_usd": round(total, 4), "model": model, "valid": not parsed["missing"], "rubric": rubric_file.name,
              "rubric_sha256": rubric_sha, "rules": str(rules), "rules_sha256": hashlib.sha256(rules.read_bytes()).hexdigest(),
              **parsed}
    (run_dir / "scorecard.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    return run_dir / "scorecard.md"
