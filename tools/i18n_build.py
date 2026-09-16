#!/usr/bin/env python3
"""Rebuild the Korean data catalogue from scratch, in priority order.

The catalogue has three sources and they disagree, so the order they are
applied in is the whole design:

  1. composed   glossary + phrase rules, for anything the other two miss
  2. game       Hero Siege's own translation tables — the words a Korean
                player sees in the client, so they outrank anything composed
  3. manual     data/i18n/manual/ko.json, hand-written for strings that exist
                only in the planner

Rebuilding rather than patching in place is what keeps this honest. Entries
composed before the glossary learned the game's wording said 피해 where every
imported line said 데미지, and nothing would ever have revisited them: the
composer skips whatever is already filled. Starting empty each time means the
wording can only be as inconsistent as the sources themselves.

Run:  python tools/i18n_build.py [--check]
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCES = "data/i18n/sources.json"
CATALOG = "data/i18n/ko.json"
MANUAL = "data/i18n/manual/ko.json"


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main(check_only: bool) -> int:
    extract = load("i18n_extract")
    game = load("i18n_import_game_csv")
    compose = load("i18n_translate_ko")

    # 0. Re-read the data files so new upstream strings appear.
    extract.main(["ko"])
    sources = json.load(open(SOURCES, encoding="utf-8"))
    catalog = {key: "" for key in sources}

    # 1. The game's own tables.
    game_dir = game.find_game_dir(None)
    if game_dir:
        pairs = game.read_tables(game_dir)
        index = game.build_index(pairs)
        for msgid in sources:
            korean = pairs.get(msgid) or index.get(game.normalise(msgid))
            if korean:
                catalog[msgid] = korean
        print(f"game tables:  {sum(1 for v in catalog.values() if v)}")
    else:
        print("game tables:  not found, skipping", file=sys.stderr)

    # 2. Compose the rest. Written out first so the composer, which reads the
    #    catalogue for vocabulary, sees the imported terms.
    write(catalog, sources)
    compose.main(True)
    catalog = json.load(open(CATALOG, encoding="utf-8"))
    print(f"composed:     {sum(1 for v in catalog.values() if v)}")

    # 3. Hand-written entries win.
    manual = json.load(open(MANUAL, encoding="utf-8")) if os.path.exists(MANUAL) else {}
    stale = sorted(key for key in manual if key not in sources)
    for key, value in manual.items():
        if key in sources and value:
            catalog[key] = value
    write(catalog, sources)

    done = sum(1 for v in catalog.values() if v)
    print(f"manual:       {done} ({len(manual)} entries, {len(stale)} no longer used)")
    for key in stale[:10]:
        print(f"  stale manual entry: {key!r}")
    print(f"\ncoverage: {done}/{len(sources)} ({100 * done / len(sources):.1f}%)")
    return 0


def write(catalog: dict, sources: dict) -> None:
    with open(CATALOG, "w", encoding="utf-8", newline="\n") as handle:
        json.dump({k: catalog.get(k, "") for k in sources}, handle,
                  ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


if __name__ == "__main__":
    raise SystemExit(main("--check" in sys.argv))
