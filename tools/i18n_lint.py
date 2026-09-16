#!/usr/bin/env python3
"""Flag `tr("...")` calls whose result is compared instead of displayed.

`tr` is identity for anything absent from the interface catalogue, so wrapping
a string that is never translated costs nothing. The moment that same text does
get a translation, though, every comparison against it starts failing — in
Korean `[tr("Sword"), tr("Mace"), ..].contains(&item.base_type)` is checking
English base types against Korean labels and is always false. Nothing panics
and no test that runs in English notices; the feature just stops working.

So: a `tr()` call is a bug when its text is in the catalogue **and** it sits in
a comparison. Exit code 1 if any such site exists.

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


def compares(line: str, start: int, end: int) -> bool:
    """Is the tr() spanning [start, end) an operand of a comparison?"""
    if EQUALITY_BEFORE.search(line[:start]) or EQUALITY_AFTER.match(line[end:]):
        return True
    # `[tr("Sword"), tr("Mace")].contains(..)` — the receiver is everything to
    # the left, so any membership test later on the line is testing this value.
    return any(m.start() >= end for m in MEMBERSHIP.finditer(line))


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
                    if match.group(1) not in translated:
                        continue
                    if compares(line, match.start(), match.end()):
                        findings.append(
                            (path.replace(os.sep, "/"), index + 1,
                             match.group(1), line.strip())
                        )

    for path, line_no, text, source in findings:
        print(f"{path}:{line_no}: tr({text!r}) is compared, not displayed")
        print(f"    {source[:110]}")
    if findings:
        print(f"\n{len(findings)} site(s) compare a translated string.")
        return 1
    print(f"clean: no translated tr() sits in a comparison "
          f"({len(translated)} translated strings checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
