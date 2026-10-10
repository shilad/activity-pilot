"""Offline tests of pilot.inventory over tests/fixtures_viewer/personas/INVENTORY.md, and of the reader's use of it."""
import shutil
from pathlib import Path
from types import SimpleNamespace

from pilot import inventory, reader

HERE = Path(__file__).parent
FIXTURE = HERE / "fixtures_viewer"
BELIEF_1 = ('Every number a script prints is an average. Fires when part1.py prints 42. Defended with "thats what '
            'numbers are". Changed by reading the line that prints it.')


def test_column():
    col = inventory.column(FIXTURE, "jordan")
    assert sorted(col) == ["beliefs", "key", "open_rulings", "rows"] and col["key"] == "jordan"
    assert col["rows"][0] == {"id": "M1", "group": "Group A — Running things",
                              "demand": "Running a script from a terminal", "where": "Part 1", "teaches": "teaches",
                              "placement": "solid", "footnote": None, "draft": False, "note": ""}
    assert [(r["id"], r["group"][:7], r["placement"], r["footnote"], r["draft"]) for r in col["rows"]] == [
        ("M1", "Group A", "solid", None, False), ("M2", "Group A", "shaky", None, False),
        ("N1", "Group B", "wrong", 1, False), ("N2", "Group B", "never", None, True)]
    assert col["beliefs"] == {1: BELIEF_1, 2: "A count and a total are different things. Fires on the same line."}
    assert col["open_rulings"] == ["M2"]
    casey = inventory.column(FIXTURE, "casey")
    assert casey["open_rulings"] == [] and casey["rows"][2]["footnote"] == 2  # the ruling names jordan only


def test_missing_or_malformed_gives_none(tmp_path):
    assert inventory.column(tmp_path, "jordan") is None  # no personas/INVENTORY.md
    assert inventory.column(FIXTURE, "nobody") is None and inventory.column(FIXTURE, None) is None  # no such column
    grid = tmp_path / "personas" / "INVENTORY.md"
    grid.parent.mkdir()
    for text in ("| # | jordan |\n| M1 | solid |\n",  # no delimiter row, so not a table
                 "| # | jordan |\n|---|---|\n| M1 |\n",  # no cell in the jordan column
                 "| # | jordan |\n|---|---|\n"):  # no rows at all
        grid.write_text(text)
        assert inventory.column(tmp_path, "jordan") is None, text
    grid.write_bytes(b"\xff\xfe| # | jordan |")  # not UTF-8
    assert inventory.column(tmp_path, "jordan") is None


def test_as_text():
    assert inventory.as_text(inventory.column(FIXTURE, "jordan")).splitlines() == [
        "M1 solid: Running a script from a terminal (first bites: Part 1)",
        "M2 shaky: Committing with a message (first bites: Part 1) [open ruling]",
        "N1 wrong (belief 1): A number a script prints is a count, not a mean (first bites: Part 1). "
        f"Belief 1: {BELIEF_1}",
        "N2 never: A blank slot is not an answer (first bites: Part 2) [draft]"]


def test_reader_materials_carry_the_grid(tmp_path):
    root = tmp_path / "toy-assignment"
    shutil.copytree(FIXTURE, root)
    shutil.copy(HERE / "fixtures" / "rubric.md", root / "rubric.md")
    run_dir = root / "runs" / "jordan-0924-1412"
    (run_dir / "transcript.md").write_text("# jordan-0924-1412\n", encoding="utf-8")
    cfg = SimpleNamespace(runs_dir=root / "runs", template=HERE / "toy" / "template")
    text, ids = reader.materials(run_dir, cfg, {"persona": "jordan"})
    heading = "===== placement grid for this persona (personas/INVENTORY.md, column jordan) ====="
    assert text.index("===== persona sheet =====") < text.index(heading) < text.index("===== facts.json =====")
    assert "M2 shaky: Committing with a message (first bites: Part 1) [open ruling]" in text
    assert ids == ["T1", "T2", "T3"]
    (root / "personas" / "INVENTORY.md").unlink()
    assert "placement grid" not in reader.materials(run_dir, cfg, {"persona": "jordan"})[0]


def test_reader_uses_the_rules_the_run_had(tmp_path):
    """The tutor's rules come from the run's own repository, not from a template edited since."""
    cfg = SimpleNamespace(template=HERE / "toy" / "template")
    repo = tmp_path / "repo"
    repo.mkdir()
    assert reader.rules_file({"repo": str(repo)}, cfg) == cfg.template / "CLAUDE.md"
    (repo / "CLAUDE.md").write_text("# rules as the run had them\n", encoding="utf-8")
    assert reader.rules_file({"repo": str(repo)}, cfg) == repo / "CLAUDE.md"
    assert reader.rules_file({}, cfg) == cfg.template / "CLAUDE.md"



def test_a_later_sitting_uses_the_same_students_column(tmp_path):
    """jordan-p1 has no column; jordan.md names the same student, so jordan's column is used."""
    a = tmp_path / "course"
    shutil.copytree(FIXTURE, a)
    first = (a / "personas" / "jordan.md").read_text().splitlines()[0]
    (a / "personas" / "jordan-p1.md").write_text(first + "\n## Who you are\nlater\n")
    col = inventory.column(a, "jordan-p1")
    assert col is not None and col["key"] == "jordan" and col["rows"] == inventory.column(a, "jordan")["rows"]
    (a / "personas" / "stranger.md").write_text("# Someone Else <s@example.edu>\n")
    assert inventory.column(a, "stranger") is None
    assert inventory.column(a, "nobody") is None
