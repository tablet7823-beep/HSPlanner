#!/usr/bin/env python3
"""Extract every translatable game-data string into a msgid catalog.

The catalog is keyed by the English source text (gettext style) rather than by
a JSON path. Data files come from upstream and get reshuffled every season, so
path keys rot; the English text is what actually identifies a message. It also
deduplicates the very repetitive tree stat lines and guarantees that the same
English phrase renders identically everywhere.

Outputs (relative to the repo root):

  data/i18n/sources.json   translator-facing template: msgid -> {ctx, count}
  data/i18n/<lang>.json    msgid -> translation; regenerated preserving edits

Run:  python tools/i18n_extract.py [lang ...]
"""

from __future__ import annotations

import collections
import json
import os
import sys

DATA_ROOT = "data"
OUT_DIR = os.path.join(DATA_ROOT, "i18n")

# Fields holding human-readable prose, shared by every collection.
#
# `tree` is the skill subtree heading ("Berserker"). It doubles as a join key
# between a skill and an item's random-skill pool, but both sides are the same
# English string and so share a catalogue entry — they move together. `tags` is
# deliberately absent: those are matched against affix-tags.json, whose own tag
# lists are JSON keys and would stay English, breaking the match.
TEXT_FIELDS = {
    "name", "description", "desc", "label", "title", "flavor", "tree", "details",
}

# Lists of prose. `uniqueEffects` is extracted but deliberately *not* applied by
# the overlay: the planner filters those strings against a sentinel ("Unholy")
# and splits `Name: formula` entries against skill names, all on the raw value.
# Translating them in the data would break that, so the tooltip translates them
# where it draws them instead.
TEXT_LIST_FIELDS = {"descriptions", "uniqueEffects"}

# `t` and `l` are the incarnation node title and its stat-line list. The key is
# file-scoped on purpose: the *tree* files reuse `t` for the node size
# (root/small/big), which is a layout enum, not prose.
SHORT_FIELDS = {
    "data/incarnation-nodes.json": ({"t"}, {"l"}),
}

# Fixtures exist to pin the season-patch merge; translating them would break the
# parity tests without putting a single string on screen.
SKIP_FILES = {"data/seasons/parity-fixture.json"}


def is_translatable(text: str) -> bool:
    """Reject ids, stat keys and pure punctuation that share the text fields."""
    stripped = text.strip()
    if len(stripped) < 2:
        return False
    if not any(ch.isalpha() for ch in stripped):
        return False
    # snake_case ids such as "poison_skill_damage" live in `name` on a few
    # collections; they are lookup keys, never displayed prose.
    if " " not in stripped and "_" in stripped and stripped.islower():
        return False
    return True


def collect(path: str, doc, sink: collections.OrderedDict) -> None:
    """Walk one document, recording each translatable string under its context."""
    label = path[len(DATA_ROOT) + 1:].removesuffix(".json").replace(os.sep, "/")
    short_str, short_list = SHORT_FIELDS.get(path.replace(os.sep, "/"), (set(), set()))
    str_fields = TEXT_FIELDS | short_str

    def visit(node, trail):
        if isinstance(node, dict):
            for key, value in node.items():
                here = trail + [key]
                if isinstance(value, str) and key in str_fields:
                    if is_translatable(value):
                        sink.setdefault(value, []).append(f"{label}:{key}")
                elif (key in short_list or key in TEXT_LIST_FIELDS) and isinstance(
                    value, list
                ):
                    for item in value:
                        if isinstance(item, str) and is_translatable(item):
                            sink.setdefault(item, []).append(f"{label}:{key}[]")
                else:
                    visit(value, here)
        elif isinstance(node, list):
            for item in node:
                visit(item, trail)

    visit(doc, [])


def load_existing(path: str) -> dict:
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: str, payload) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def main(langs: list[str]) -> int:
    sink: collections.OrderedDict = collections.OrderedDict()
    files = 0
    for root, _dirs, names in os.walk(DATA_ROOT):
        if os.path.normpath(root).startswith(os.path.normpath(OUT_DIR)):
            continue
        for name in sorted(names):
            if not name.endswith(".json"):
                continue
            path = os.path.join(root, name)
            if path.replace(os.sep, "/") in SKIP_FILES:
                continue
            with open(path, encoding="utf-8") as handle:
                collect(path, json.load(handle), sink)
            files += 1

    sources = {
        msgid: {"ctx": sorted(set(ctxs))[:4], "count": len(ctxs)}
        for msgid, ctxs in sink.items()
    }
    write_json(os.path.join(OUT_DIR, "sources.json"), sources)

    total_chars = sum(len(m) for m in sink)
    print(f"scanned {files} data files")
    print(f"unique msgids: {len(sink)}  ({total_chars} chars)")
    print(f"occurrences:   {sum(len(c) for c in sink.values())}")

    for lang in langs:
        target = os.path.join(OUT_DIR, f"{lang}.json")
        existing = load_existing(target)
        merged = {m: existing.get(m, "") for m in sink}
        stale = sorted(set(existing) - set(sink))
        write_json(target, merged)
        done = sum(1 for v in merged.values() if v)
        pct = 100.0 * done / len(merged) if merged else 0.0
        print(
            f"{lang}: {done}/{len(merged)} translated ({pct:.1f}%)"
            + (f", dropped {len(stale)} stale" if stale else "")
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:] or ["ko"]))
