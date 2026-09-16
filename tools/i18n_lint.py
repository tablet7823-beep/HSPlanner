#!/usr/bin/env python3
"""Flag `tr("...")` calls whose result is compared instead of displayed.

`tr` is identity for anything absent from the interface catalogue, so wrapping
a string that is never translated costs nothing. The moment that same text does
get a translation, though, every comparison against it starts failing — in
Korean `[tr("Sword"), tr("Mace"), ..].contains(&item.base_type)` is checking
English base types against Korean labels and is always false. Nothing panics
and no test that runs in English notices; the feature just stops working.

The same trap has a second shape. `.header(tr("Accept"), ..)` shipped for a
while: "Accept" is also a button label, so the catalogue translated it and the
update check started sending a header named 확인. Protocol text is not prose,
and where it sits is the only way to tell.

So: a `tr()` call is a bug when its text is in the catalogue **and** it sits in
a comparison, or when it sits in a protocol position at all. Exit code 1 if any
such site exists.

Run:  python tools/i18n_lint.py
"""

from __future__ import annotations

import json
import os
import re
import sys

UI_CATALOG = "data/i18n/ui/ko.json"
CRATES = "crates"

TR_CALL = re.compile(r'tr\("((?:[^"\\]|\\.)*)"\)')

# Producing a value is fine — `Section::Library => tr("Library")` and
# `.ok_or(tr("..."))` both just build something to show later. What matters is
# the result being tested, which shows up two ways on the line itself.
MEMBERSHIP = re.compile(r"\.(contains|starts_with|ends_with|eq|eq_ignore_ascii_case)\(")
EQUALITY_BEFORE = re.compile(r"(==|!=)\s*$")
EQUALITY_AFTER = re.compile(r"^\s*(==|!=)")

# Arguments to these are read by something other than a person, so no entry in
# the catalogue is ever the right answer — unlike a comparison, this is a bug
# whether or not the string happens to be translated today.
PROTOCOL = re.compile(
    r"\.(?:header|set_header|append_header|insert_header|content_type|mime|uri|url)\s*\("
)


def compares(line: str, start: int, end: int) -> bool:
    """Is the tr() spanning [start, end) an operand of a comparison?"""
    if EQUALITY_BEFORE.search(line[:start]) or EQUALITY_AFTER.match(line[end:]):
        return True
    # `[tr("Sword"), tr("Mace")].contains(..)` — the receiver is everything to
    # the left, so any membership test later on the line is testing this value.
    return any(m.start() >= end for m in MEMBERSHIP.finditer(line))


def protocol_position(line: str, start: int) -> bool:
    """Is the tr() anywhere inside the parentheses of a machine-facing call?

    Both arguments count: the name and the value of a header are equally not
    prose, and `.header(ACCEPT, tr("application/json"))` is the same bug.
    """
    for call in PROTOCOL.finditer(line):
        depth = 0
        for index in range(call.end() - 1, len(line)):
            if line[index] == "(":
                depth += 1
            elif line[index] == ")":
                depth -= 1
                if depth == 0:
                    break
            if depth and index == start:
                return True
    return False


def catalogues() -> set[str]:
    """Every source string that some locale actually translates."""
    translated: set[str] = set()
    directory = os.path.dirname(UI_CATALOG)
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".json") or name == "sources.json":
            continue
        with open(os.path.join(directory, name), encoding="utf-8") as handle:
            for source, target in json.load(handle).items():
                if target:
                    translated.add(source)
    return translated


def main() -> int:
    translated = catalogues()
    findings = []
    for root, _dirs, files in os.walk(CRATES):
        for name in sorted(files):
            if not name.endswith(".rs"):
                continue
            path = os.path.join(root, name)
            lines = open(path, encoding="utf-8").read().split("\n")
            for index, line in enumerate(lines):
                for match in TR_CALL.finditer(line):
                    if protocol_position(line, match.start()):
                        reason = "reaches a protocol, not a person"
                    elif match.group(1) not in translated:
                        continue
                    elif compares(line, match.start(), match.end()):
                        reason = "is compared, not displayed"
                    else:
                        continue
                    findings.append(
                        (path.replace(os.sep, "/"), index + 1,
                         match.group(1), reason, line.strip())
                    )

    for path, line_no, text, reason, line in findings:
        print(f"{path}:{line_no}: tr({text!r}) {reason}")
        print(f"    {line[:110]}")
    if findings:
        print(f"\n{len(findings)} site(s) use tr() for something other than display.")
        return 1
    print(f"clean: no translated tr() sits in a comparison, none reach a protocol "
          f"({len(translated)} translated strings checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
