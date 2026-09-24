"""Check WRITEUP.md: list any blank answer, or print the finish line when none is blank."""

import re
import sys
from pathlib import Path

SLOT = re.compile(r"^\*\*(.+?):\*\*\s*(.*)$")
PART = re.compile(r"^## Part (\d+)")


def blank_slots(text):
    part = None
    blanks = []
    for line in text.splitlines():
        heading = PART.match(line)
        if heading:
            part = heading.group(1)
            continue
        slot = SLOT.match(line.strip())
        if part and slot and (not slot.group(2).strip() or "XXXX" in slot.group(2)):
            blanks.append(f"Part {part}: {slot.group(1)}")
    return blanks


def main():
    path = Path(__file__).resolve().parent / "WRITEUP.md"
    blanks = blank_slots(path.read_text(encoding="utf-8"))
    if blanks:
        print("These answers in WRITEUP.md are still blank:")
        for item in blanks:
            print(f"  - {item}")
        return 1
    print("YOU ARE FINISHED!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
