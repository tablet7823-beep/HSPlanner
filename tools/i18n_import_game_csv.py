#!/usr/bin/env python3
"""Fill the Korean catalogue from Hero Siege's own translation tables.

The game ships `translations*.csv` next to `Hero_Siege.exe`, one row per string
as `key|en|fi|pt|ru|zh|ja|ko|de|fr|sp|pl`. Those are the names Korean players
actually see in game, so matching the planner's English strings against the
`en` column and taking `ko` beats anything composed from a glossary: the terms
are the game's own, and a player reading the planner sees the same words as on
their screen.

Matching is exact first, then on a normalised form (case, spacing, trailing
punctuation and the `%`/`+` decorations that the planner's copies carry but the
game's do not). A normalised key that maps to more than one distinct Korean
string is dropped rather than guessed at — a stat named two different things in
two contexts is exactly the case where picking one silently would be wrong.

Run:  python tools/i18n_import_game_csv.py [--write] [--game <bin dir>]
"""

from __future__ import annotations

import collections
import json
import os
import re
import sys
from pathlib import Path

SOURCES = "data/i18n/sources.json"
CATALOG = "data/i18n/ko.json"
UI_SOURCES = "data/i18n/ui/sources.json"
UI_CATALOG = "data/i18n/ui/ko.json"

# Where Steam usually puts it; --game overrides.
DEFAULT_GAME_DIRS = [
    Path(r"D:\SteamLibrary\steamapps\common\HeroSiege\bin"),
    Path(r"C:\Program Files (x86)\Steam\steamapps\common\HeroSiege\bin"),
    Path(r"C:\SteamLibrary\steamapps\common\HeroSiege\bin"),
]

EN, KO = 1, 7  # column offsets after the leading key


def find_game_dir(override: str | None) -> Path | None:
    if override:
        path = Path(override)
        return path if path.is_dir() else None
    for candidate in DEFAULT_GAME_DIRS:
        if candidate.is_dir():
            return candidate
    return None


def read_tables(game_dir: Path) -> dict[str, str]:
    """English -> Korean across every shipped table."""
    pairs: dict[str, str] = {}
    for path in sorted(game_dir.glob("translations*.csv")):
        with open(path, encoding="utf-8", errors="replace") as handle:
            for line in handle:
                line = line.rstrip("\n").rstrip("\r")
                if not line or line.startswith("["):
                    continue
                cells = line.split("|")
                if len(cells) <= KO:
                    continue
                english, korean = cells[EN].strip(), cells[KO].strip()
                # A blank `ko` means the game itself has no translation yet.
                if not english or not korean or english == korean:
                    continue
                pairs.setdefault(english, korean)
    return pairs


# Decorations the planner's copy of a stat carries but the game's table does not.
TRIM = re.compile(r"^[+\-•\s]+|[\s:.]+$")
COLLAPSE = re.compile(r"\s+")


def normalise(text: str) -> str:
    text = TRIM.sub("", text)
    text = COLLAPSE.sub(" ", text)
    return text.casefold()


def build_index(pairs: dict[str, str]) -> dict[str, str]:
    """Normalised English -> Korean, minus anything ambiguous."""
    grouped: dict[str, set[str]] = collections.defaultdict(set)
    for english, korean in pairs.items():
        grouped[normalise(english)].add(korean)
    return {key: next(iter(values)) for key, values in grouped.items() if len(values) == 1}


def fill(sources_path: str, catalog_path: str, pairs: dict[str, str],
         index: dict[str, str], write: bool, label: str,
         overwrite: bool) -> None:
    """Merge the game's Korean into one catalogue.

    `overwrite` is on for game data, where the game's wording is authoritative
    and should replace anything composed from the local glossary. It is off for
    the interface, where the same English word can mean something else: the
    planner's "Save" is a file operation, the game's is a checkpoint, and a
    hand-written interface string was already chosen for this screen.
    """
    sources = json.load(open(sources_path, encoding="utf-8"))
    catalog = json.load(open(catalog_path, encoding="utf-8"))

    exact = fuzzy = kept = 0
    for msgid in sources:
        if not overwrite and catalog.get(msgid):
            kept += 1
            continue
        korean = pairs.get(msgid)
        if korean:
            exact += 1
        else:
            korean = index.get(normalise(msgid))
            if korean:
                fuzzy += 1
        if korean:
            catalog[msgid] = korean

    done = sum(1 for key in sources if catalog.get(key))
    kept_note = f", kept {kept} existing" if kept else ""
    print(f"{label}: exact {exact}, normalised {fuzzy}{kept_note} "
          f"-> {done}/{len(sources)} ({100 * done / len(sources):.1f}%)")

    if write:
        with open(catalog_path, "w", encoding="utf-8", newline="\n") as handle:
            json.dump({k: catalog.get(k, "") for k in sources}, handle,
                      ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")


def main(argv: list[str]) -> int:
    write = "--write" in argv
    override = None
    if "--game" in argv:
        override = argv[argv.index("--game") + 1]

    game_dir = find_game_dir(override)
    if not game_dir:
        print("Hero Siege install not found; pass --game <bin dir>", file=sys.stderr)
        return 1

    pairs = read_tables(game_dir)
    index = build_index(pairs)
    print(f"game tables: {game_dir}")
    print(f"english->korean pairs: {len(pairs)} ({len(index)} unambiguous normalised)")

    fill(SOURCES, CATALOG, pairs, index, write, "game data", overwrite=True)
    if os.path.exists(UI_SOURCES):
        fill(UI_SOURCES, UI_CATALOG, pairs, index, write, "interface", overwrite=False)
    if not write:
        print("(dry run — pass --write to save)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
