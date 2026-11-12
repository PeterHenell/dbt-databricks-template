"""Set one scalar in a YAML file by its key path, keeping the file's comments and layout.

A targeted line edit, not a YAML round-trip: it finds the line of the key under its
parent mappings (by indentation) and replaces only the value. That is enough for
hand-written config files like databricks.yml, where every value it sets is a plain
scalar on the key's own line, and it needs no extra dependency.
"""

from __future__ import annotations

import json
import re

from dbtp.devenv import SetupError

# `key: value  # comment`, `key:` (a mapping follows) or `- …` (skipped: lists aren't paths).
_KEY_LINE = re.compile(r"^(?P<indent> *)(?P<key>[A-Za-z0-9_.-]+):(?P<rest>.*)$")
_PLAIN = re.compile(r"^[A-Za-z0-9_./:@+-]+$")


def _split_value(rest: str) -> tuple[str, str]:
    """`rest` after `key:` → (value with its leading space, trailing ` # comment` or "")."""
    value, comment = rest, ""
    in_quote = None
    for index, char in enumerate(rest):
        if char in "\"'" and in_quote in (None, char):
            in_quote = None if in_quote else char
        elif char == "#" and in_quote is None and (index == 0 or rest[index - 1] in " \t"):
            value, comment = rest[:index], rest[index:]
            break
    stripped = value.rstrip()
    return stripped, value[len(stripped):] + comment


def format_scalar(value: str, quoted: bool = False) -> str:
    """`value` as a YAML scalar: plain when that is safe, else double-quoted."""
    if not quoted and _PLAIN.match(value) and not value.startswith(("-", ":", "@")):
        return value
    return json.dumps(value)


def set_value(text: str, path: tuple[str, ...], value: str) -> str:
    """Return `text` with the scalar at `path` (e.g. targets, prod, variables, catalog) set.

    Keeps the value's quoting style (a quoted value stays quoted). Raises SetupError if
    the key isn't there or holds a mapping instead of a scalar.
    """
    lines = text.splitlines(keepends=True)
    stack: list[tuple[int, str]] = []  # (indent, key) of the mappings around the line
    for number, line in enumerate(lines):
        body = line.rstrip("\r\n")
        if not body.strip() or body.lstrip().startswith("#"):
            continue
        match = _KEY_LINE.match(body)
        if not match:
            continue
        indent = len(match["indent"])
        while stack and stack[-1][0] >= indent:
            stack.pop()
        stack.append((indent, match["key"]))
        if tuple(key for _, key in stack) != path:
            continue
        old, tail = _split_value(match["rest"])
        if not old.strip():
            raise SetupError(f"{'.'.join(path)} holds a mapping, not a value.")
        quoted = old.strip()[:1] in ("\"", "'")
        newline = line[len(body):]
        lines[number] = (f"{match['indent']}{match['key']}: "
                         f"{format_scalar(value, quoted)}{tail}{newline}")
        return "".join(lines)
    raise SetupError(f"no `{'.'.join(path)}` to fill in.")
