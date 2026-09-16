#!/usr/bin/env python3
"""Find interface literals in the Rust UI crates and wrap them for translation.

  scan   report the candidates and write data/i18n/ui/sources.json
  wrap   rewrite the call sites as tr("...")

Interface text in this codebase rarely reaches a renderer directly; it is
passed into local helpers like `point_stat("tree-used", "Tree nodes", ..)`, so
there is no call name to key on. Candidates are chosen by what the literal
looks like and by what surrounds it instead.

Wrapping the wrong literal is the failure that matters: `tr` is identity for
anything absent from the catalogue, so an over-wrapped string is harmless until
someone adds that exact text as a catalogue entry, at which point an identifier
or a comparison quietly changes meaning. Hence two independent guards — reject
anything shaped like a key, and reject anything sitting in a comparison,
lookup or match arm, where the literal is being matched rather than shown.

Run:  python tools/i18n_extract_ui.py scan
      python tools/i18n_extract_ui.py wrap
"""

from __future__ import annotations

import collections
import json
import os
import re
import sys

CRATES = "crates"
OUT_DIR = os.path.join("data", "i18n", "ui")

LITERAL = re.compile(r'"(?:[^"\\\n]|\\.)*"')

# Shapes that are identifiers, paths, config keys or colours — never prose.
REJECT_SHAPE = (
    re.compile(r"^[a-z0-9_-]+$"),                  # snake/kebab ids
    re.compile(r"^[A-Z0-9_]+$"),                   # env vars, SCREAMING consts
    re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$"),    # dotted keys
    re.compile(r"^[a-z0-9_.-]+/[a-z0-9_/.-]+$"),   # paths and mime types
    re.compile(r"^#?[0-9a-fA-F]{3,8}$"),           # colours
    re.compile(r"^\W+$"),                          # punctuation only
    re.compile(r"^\d"),                            # starts with a number
    # camelCase serialisation keys (allocatedTreeNodes, maxSubskillPoints).
    # Interface text of more than one word always carries a space.
    re.compile(r"^[a-z]+(?:[A-Z][a-z0-9]*)+$"),
)

# Fragments of generated Rust or of serialisation plumbing.
REJECT_SUBSTRING = ("=>", "::", "();", "&[", "include_", "cargo:", "sha256:")

# Relative paths and file names; these reach `include_bytes!` and friends.
REJECT_PATHISH = (
    re.compile(r"^\.{1,2}/"),
    re.compile(r"\.(ttf|otf|png|jpg|jpeg|svg|gif|md|json|toml|rs|exe|dmg|deb)$"),
    re.compile(r"^#\S"),                           # anchors like #does-not-exist
)

# The literal is being compared or looked up, not displayed.
MATCHING_CONTEXT = re.compile(
    r"(==|!=|\.get|\.contains|\.starts_with|\.ends_with|\.eq|\.strip_prefix"
    r"|\.strip_suffix|\.split|\.trim_matches|\.trim_start_matches|\.trim_end_matches"
    r"|matches!|\.insert|\.entry|\.remove|\.any|\.position|\.find|\.iter\(\)"
    r"|env!|var\(|var_os\(|rename\(|serde"
    r"|include_bytes!|include_str!|Path::new|PathBuf::from|join|expect)\s*\(?\s*$"
)
MATCH_ARM = re.compile(r"^\s*(=>|\|)")
# `["Sword", "Mace"].contains(&item.base_type)` — the literal is an operand of a
# membership test further along the line, so it is data being matched, not a
# label. Wrapping these compiles fine and then silently fails once the strings
# are translated; tools/i18n_lint.py exists to catch any that slip through.
MEMBERSHIP_LATER = re.compile(r"\.(contains|starts_with|ends_with|eq)\(")
# `"a" | "b" | "c"` alternations wrap across lines, so the literal that opens a
# continuation line is a pattern even though nothing follows it on that line.
PATTERN_ALTERNATION = re.compile(r"\|\s*$")


def is_prose(text: str) -> bool:
    if not 2 <= len(text) <= 200:
        return False
    if not re.search(r"[A-Za-z]{2}", text):
        return False
    if any(rx.match(text) for rx in REJECT_SHAPE):
        return False
    if any(frag in text for frag in REJECT_SUBSTRING):
        return False
    if any(rx.search(text) for rx in REJECT_PATHISH):
        return False
    # A format placeholder means the call site assembles the string itself.
    if "{" in text or "}" in text:
        return False
    # Multi-line blobs are fixtures and generated markup, not labels. The
    # escapes are already decoded here, so match the real characters.
    if any(ch in text for ch in "\n\t\r\""):
        return False
    return True


def sources():
    for root, _dirs, files in os.walk(CRATES):
        # Integration tests are fixtures, not interface text.
        if os.path.basename(root) == "tests" or f"{os.sep}tests{os.sep}" in root + os.sep:
            continue
        for name in sorted(files):
            # build.rs emits Rust source; its literals are code, not interface.
            if name.endswith(".rs") and name != "build.rs":
                yield os.path.join(root, name)


def mask_noise(text: str) -> str:
    """Blank line comments and #[..] attributes so neither gets rewritten."""
    out = []
    for line in text.split("\n"):
        stripped = line.lstrip()
        blank = stripped.startswith("//") or stripped.startswith("#[")
        out.append(" " * len(line) if blank else line)
    return "\n".join(out)


CONST_ITEM = re.compile(
    r"^[ \t]*(?:pub(?:\([^)]*\))?[ \t]+)?(?:const|static)[ \t]+[A-Za-z_][A-Za-z0-9_]*[ \t]*:",
    re.MULTILINE,
)

# Diagnostics, not interface text. Several of these also require their format
# argument to be a literal, so wrapping them does not even compile.
DEV_MACRO = re.compile(
    r"\b(?:panic|assert|assert_eq|assert_ne|debug_assert|unreachable|todo|unimplemented"
    r"|format|write|writeln|print|println|eprint|eprintln|json)!\s*\("
)


def closing_span(text: str, open_at: int, terminator: str) -> tuple[int, int]:
    """Range from `open_at` to the terminator that closes it at depth zero."""
    depth = 0
    for index in range(open_at, len(text)):
        char = text[index]
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
            if terminator == ")" and depth == 0:
                return open_at, index
        elif char == terminator == ";" and depth <= 0:
            return open_at, index
    return open_at, len(text)


def const_spans(text: str) -> list[tuple[int, int]]:
    """Byte ranges covered by `const`/`static` items.

    Their literals are compile-time data — serialisation field names, table
    keys, embedded paths — never interface text. `tr` is a normal function, so
    the compiler rejects these outright; excluding them here keeps the wrap from
    producing code that cannot build.
    """
    return [closing_span(text, m.start(), ";") for m in CONST_ITEM.finditer(text)]


def dev_macro_spans(text: str) -> list[tuple[int, int]]:
    return [closing_span(text, m.end() - 1, ")") for m in DEV_MACRO.finditer(text)]


CFG_TEST = re.compile(r"#\[cfg\(test\)\]")


def cfg_test_spans(raw: str) -> list[tuple[int, int]]:
    """Ranges covered by `#[cfg(test)]` items.

    Not everything after the first marker: `#[cfg(test)]` also tags individual
    test-only helpers inside ordinary impl blocks, and treating the first one as
    a cutoff silently skipped the remaining 1,385 lines of library/src/lib.rs —
    the whole builds sidebar stayed English. Each item is bounded by its own
    braces instead.
    """
    spans = []
    for m in CFG_TEST.finditer(raw):
        brace = raw.find("{", m.end())
        if brace == -1:
            spans.append((m.start(), len(raw)))
            continue
        depth = 0
        for index in range(brace, len(raw)):
            if raw[index] == "{":
                depth += 1
            elif raw[index] == "}":
                depth -= 1
                if depth == 0:
                    spans.append((m.start(), index))
                    break
        else:
            spans.append((m.start(), len(raw)))
    return spans


def candidates(text: str, test_spans: list[tuple[int, int]]):
    """Yield (start, end, value) for each literal that should be translated.

    `test_spans` is measured on the unmasked source — `mask_noise` blanks
    attribute lines, `#[cfg(test)]` among them, so the marker cannot be found
    here. Masking preserves length, so the offsets still line up.
    """
    excluded = const_spans(text) + dev_macro_spans(text) + test_spans
    for m in LITERAL.finditer(text):
        # b"bytes" and r"raw" are not display strings, and wrapping one splices
        # tr( into the middle of the token: b"x" becomes btr("x").
        if m.start() > 0 and text[m.start() - 1] in "br#":
            continue
        if any(start <= m.start() < end for start, end in excluded):
            continue
        try:
            value = json.loads(m.group(0))
        except json.JSONDecodeError:
            continue
        if not is_prose(value):
            continue
        before = text[max(0, m.start() - 48):m.start()]
        after = text[m.end():m.end() + 6]
        line_end = text.find(chr(10), m.end())
        rest_of_line = text[m.end():line_end if line_end != -1 else len(text)]
        if (
            MATCHING_CONTEXT.search(before)
            or MATCH_ARM.match(after)
            or PATTERN_ALTERNATION.search(before)
            or MEMBERSHIP_LATER.search(rest_of_line)
        ):
            continue
        yield m.start(), m.end(), value


def scan():
    found: collections.Counter = collections.Counter()
    per_file: dict[str, int] = {}
    for path in sources():
        raw = open(path, encoding="utf-8").read()
        hits = [value for _, _, value in candidates(mask_noise(raw), cfg_test_spans(raw))]
        if hits:
            per_file[path.replace(os.sep, "/")] = len(hits)
            found.update(hits)

    os.makedirs(OUT_DIR, exist_ok=True)
    payload = {k: {"count": v} for k, v in sorted(found.items())}
    with open(os.path.join(OUT_DIR, "sources.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    for path, count in sorted(per_file.items(), key=lambda kv: -kv[1])[:20]:
        print(f"{count:>5}  {path}")
    print(f"\nunique interface strings: {len(found)}")
    print(f"call sites: {sum(found.values())}")
    return found


IMPORT = "use hsplanner_engine::calc::i18n::tr;"


def add_import(text: str) -> str:
    """Put the import with the file's other top-level `use` lines, or below the
    leading doc comments and attributes when the file has none."""
    if IMPORT in text:
        return text
    lines = text.split("\n")
    for index, line in enumerate(lines):
        if line.startswith("use "):
            lines.insert(index, IMPORT)
            return "\n".join(lines)
    index = 0
    while index < len(lines) and (
        lines[index].startswith(("//", "#!", "#[")) or not lines[index].strip()
    ):
        index += 1
    lines.insert(index, IMPORT)
    lines.insert(index + 1, "")
    return "\n".join(lines)


def wrap():
    total = touched = 0
    for path in sources():
        original = open(path, encoding="utf-8").read()
        spans = list(candidates(mask_noise(original), cfg_test_spans(original)))
        if not spans:
            continue
        text = original
        # Back to front, so the offsets ahead of each edit stay valid.
        for start, end, _ in sorted(spans, key=lambda s: -s[0]):
            text = f"{text[:start]}tr({text[start:end]}){text[end:]}"
        open(path, "w", encoding="utf-8", newline="").write(add_import(text))
        total += len(spans)
        touched += 1
    print(f"wrapped {total} literals across {touched} files")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "scan"
    if mode == "scan":
        scan()
    elif mode == "wrap":
        wrap()
    else:
        raise SystemExit(f"unknown mode {mode!r}; use scan or wrap")
