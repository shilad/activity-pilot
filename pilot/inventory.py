"""The optional placement grid: one persona's column of <assignment>/personas/INVENTORY.md.

The file's shape is set out in personas/FORMAT.md, "Optional: the placement grid": demand tables whose first header
cell is `#`, each under a `## ` heading naming its group; one grid table whose header names the persona keys; a
numbered list under a heading containing "wrong beliefs"; and an optional "Open rulings" section with one bullet per
ruling, `- **<row id>** (<persona keys>): ...`. Standard library only.
"""
import re
from pathlib import Path

PATH = "personas/INVENTORY.md"  # relative to the assignment directory
PLACEMENTS = ("solid", "shaky", "wrong", "never")
SUPERSCRIPT_DIGITS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
CELL = re.compile(r"([^\s⁰¹²³⁴⁵⁶⁷⁸⁹\d(]*)\s*([⁰¹²³⁴⁵⁶⁷⁸⁹]+|\d+)?\s*(.*)$")  # placement word, footnote, any note
DRAFT = re.compile(r"\s*\(draft\)", re.IGNORECASE)
DELIMITER_ROW = re.compile(r"\|[ \t|:-]*-[ \t|:-]*")  # the |---|---| line that makes the line above a table header
BELIEF = re.compile(r"\s{0,3}(\d+)\.\s+(.*)")  # an item of the wrong-beliefs list; its wrapped lines are indented more
RULING = re.compile(r"[-*]\s+\*\*(.+?)\*\*\s*(?:\(([^)]*)\))?")  # - **<row id>** (<persona keys>): ...


def column(assignment_dir: Path, key: str | None) -> dict | None:
    """One persona's column, joined to what each row demands; None when there is no file, no column or no rows.

    A key the grid has no column for uses the column of another sheet for the same student: the sheet in
    personas/ whose first line (`# Name <email>`) is the same, such as careful for careful-p1, a later sitting.

    Returns {"key", "rows", "beliefs", "open_rulings"}: the column used; rows in grid order, each {"id", "group",
    "demand", "where", "teaches", "placement", "footnote", "draft", "note"}; beliefs maps a footnote number to its
    text; and open_rulings lists the row ids an Open rulings bullet names for this persona.
    """
    if not key:
        return None
    try:
        text = (assignment_dir / PATH).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    col = _parse(text, key)
    if col is None and (same := _same_student(assignment_dir, key, text)):
        col = _parse(text, same)
    return col


def _same_student(assignment_dir: Path, key: str, text: str) -> str | None:
    """The grid column of another sheet whose first line names the same student (name and email), if exactly one."""
    def first(sheet: Path) -> str:
        try:
            return sheet.read_text(encoding="utf-8").splitlines()[0].strip()
        except (OSError, UnicodeDecodeError, IndexError):
            return ""
    folder = assignment_dir / "personas"
    mine = first(folder / f"{key}.md")
    if not mine:
        return None
    columns = {cell for table in _tables(text.splitlines()) if table["head"][:1] == ["#"] for cell in table["head"][1:]}
    same = [s.stem for s in sorted(folder.glob("*.md")) if s.stem != key and s.stem in columns and first(s) == mine]
    return same[0] if len(same) == 1 else None


def as_text(col: dict) -> str:
    """The column as the reader receives it, one line per row: `S4 shaky: <demand> (first bites: <where>)`."""
    return "\n".join(_row_text(row, col) for row in col["rows"])


def _row_text(row: dict, col: dict) -> str:
    line = f"{row['id']} {row['placement']}"
    if row["footnote"] is not None:
        line += f" (belief {row['footnote']})"
    if row["note"]:
        line += f" {row['note']}"
    line += f": {row['demand']}".rstrip()
    if row["where"]:
        line += f" (first bites: {row['where']})"
    if row["footnote"] in col["beliefs"]:
        line += f". Belief {row['footnote']}: {col['beliefs'][row['footnote']]}"
    if row["draft"]:
        line += " [draft]"
    if row["id"] in col["open_rulings"]:
        line += " [open ruling]"
    return line


def _parse(text: str, key: str) -> dict | None:
    lines = text.splitlines()
    tables = _tables(lines)
    grid = next((table for table in tables if key in table["head"][1:]), None)
    if grid is None:
        return None
    rows = _grid_rows(grid, key, _demands(tables, grid))
    if not rows:
        return None
    ruled = _open_rulings(lines, grid["head"][1:], key, {row["id"] for row in rows})
    return {"key": key, "rows": rows, "beliefs": _beliefs(lines), "open_rulings": ruled}


def _plain(text: str) -> str:
    return text.replace("**", "").strip()


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _tables(lines: list[str]) -> list[dict]:
    """Every Markdown table: its header cells, its rows, and its group, the nearest `## ` heading above it."""
    tables, group, n = [], "", 0
    while n < len(lines):
        line = lines[n].strip()
        if line.startswith("## "):
            group = _plain(line[3:])
        if line.startswith("|") and n + 1 < len(lines) and DELIMITER_ROW.fullmatch(lines[n + 1].strip()):
            table = {"head": [_plain(cell) for cell in _cells(line)], "rows": [], "group": group}
            n += 2
            while n < len(lines) and lines[n].strip().startswith("|"):
                table["rows"].append(_cells(lines[n]))
                n += 1
            tables.append(table)
        else:
            n += 1
    return tables


def _demands(tables: list[dict], grid: dict) -> dict:
    """Row id to its group, demand, where it first bites, and whether the handout teaches it, read from the demand
    tables: every table whose first header cell is `#`, except the grid."""
    demands = {}
    for table in tables:
        if table is grid or table["head"][0] != "#":
            continue
        where = next((n for n, header in enumerate(table["head"]) if header.lower().startswith("where")), None)
        teaches = next((n for n, header in enumerate(table["head"]) if "teaches" in header.lower()), None)
        for row in table["rows"]:
            demands.setdefault(_plain(row[0]), {"group": table["group"], "demand": _cell(row, 1),
                                                "where": _cell(row, where), "teaches": _cell(row, teaches)})
    return demands


def _cell(row: list[str], n: int | None) -> str:
    return _plain(row[n]) if n is not None and n < len(row) else ""


def _grid_rows(grid: dict, key: str, demands: dict) -> list[dict]:
    """The grid's rows in this persona's column; a row no demand table lists keeps empty demand text."""
    k = grid["head"].index(key)
    blank = {"group": "", "demand": "", "where": "", "teaches": ""}
    return [{"id": _plain(row[0]), **demands.get(_plain(row[0]), blank), **_placement(row[k])}
            for row in grid["rows"] if len(row) > k and _plain(row[0])]


def _placement(cell: str) -> dict:
    """A cell such as `shaky`, `wrong³`, `never (draft)` or `shaky (asked once)`, taken apart."""
    text = _plain(cell)
    word, digits, rest = CELL.match(DRAFT.sub("", text).strip()).groups()
    placement = word.lower() if word.lower() in PLACEMENTS else word
    if digits and placement == "wrong":  # a wrong placement's footnote numbers its belief
        footnote, note = int(digits.translate(SUPERSCRIPT_DIGITS)), rest
    else:  # any other footnote stays in the note as written
        footnote, note = None, f"{digits or ''} {rest}".strip()
    return {"placement": placement, "footnote": footnote, "draft": DRAFT.search(text) is not None, "note": note}


def _section(lines: list[str], words: str) -> list[str]:
    """The lines under the first heading that contains `words` (any case), up to the next heading."""
    start = next((n + 1 for n, line in enumerate(lines) if line.startswith("#") and words in line.lower()), len(lines))
    end = next((n for n in range(start, len(lines)) if lines[n].startswith("#")), len(lines))
    return lines[start:end]


def _beliefs(lines: list[str]) -> dict:
    """Footnote number to belief text: item N of the wrong-beliefs list, its wrapped lines joined."""
    beliefs, current = {}, None
    for line in _section(lines, "wrong beliefs"):
        item = BELIEF.match(line)
        if item:
            current = int(item[1])
            beliefs[current] = _plain(item[2])
        elif line.strip() and current is not None:
            beliefs[current] += " " + _plain(line)
        else:
            current = None
    return beliefs


def _open_rulings(lines: list[str], keys: list[str], key: str, row_ids: set) -> list[str]:
    """Row ids named by an Open rulings bullet that concerns this persona; a bullet naming no persona key concerns
    every column."""
    ruled = []
    for line in _section(lines, "open rulings"):
        bullet = RULING.match(line)
        if not bullet:
            continue
        named = set(re.findall(r"[\w-]+", bullet[2] or "")) & set(keys)
        if named and key not in named:
            continue
        ruled += [row_id for row_id in re.split(r"[,\s]+", bullet[1]) if row_id in row_ids and row_id not in ruled]
    return ruled
