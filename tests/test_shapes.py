"""Slot shapes and the no-op rule, both learned from the first HW1 run."""
from pilot.facts import slots
from pilot.run import NOOP

WRITEUP = """# Writeup
**Name:** XXXX
## Part 0. Predictions
**(2) Out of every 100 people, how many tagged?** 60
**(2) Why you think so:** XXXX
**My rule for cutting the ratings** (written before reading the script): keep heavy raters
**My ten movies:**

XXXX

**One thing I learned, and one thing that
got in the way:** XXXX
## Part 1. Data
**Answered below:**

Toy Story, Heat, Casino
and two more

Replace every XXXX with your answer.
"""


def test_every_label_shape():
    got = {s["label"]: s for s in slots(WRITEUP, "XXXX", r"^## Part (\d+)")}
    assert len(got) == 7, sorted(got)
    assert got["Name"]["blank"] and got["Name"]["part"] is None
    assert not got["(2) Out of every 100 people, how many tagged?"]["blank"]
    assert got["(2) Why you think so"]["blank"] and got["(2) Why you think so"]["part"] == 0
    assert not got["My rule for cutting the ratings"]["blank"]
    assert got["My ten movies"]["blank"]
    assert got["One thing I learned, and one thing that got in the way"]["blank"]
    assert not got["Answered below"]["blank"] and got["Answered below"]["part"] == 1


def test_noop_commands():
    assert all(NOOP.match(c) for c in ("true", " : ", "echo", 'echo "placeholder"', "sleep 5"))
    assert not any(NOOP.match(c) for c in ("uv run python part1.py", "git commit -m x", "echo hi > f.txt && ls"))
