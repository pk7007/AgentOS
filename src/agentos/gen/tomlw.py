"""Minimal TOML writer for the generated host files (stdlib only reads TOML)."""

import re

_BARE = re.compile(r"^[A-Za-z0-9_-]+$")
_ESCAPES = {"\\": "\\\\", '"': '\\"', "\b": "\\b", "\t": "\\t", "\n": "\\n", "\f": "\\f", "\r": "\\r"}


def _key(k: str) -> str:
    return k if _BARE.match(k) else _basic(k)


def _ctrl(ch: str) -> bool:
    return ord(ch) < 0x20 or ord(ch) == 0x7F


def _basic(s: str) -> str:
    out = []
    for ch in s:
        if ch in _ESCAPES:
            out.append(_ESCAPES[ch])
        elif _ctrl(ch):
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def _multiline(s: str) -> str:
    body = []
    for ch in s:
        if ch == "\\":
            body.append("\\\\")
        elif ch == "\n":
            body.append("\n")
        elif _ctrl(ch):
            body.append(_ESCAPES.get(ch) or f"\\u{ord(ch):04x}")
        else:
            body.append(ch)
    text = "".join(body).replace('"""', '""\\"')
    if text.endswith('"'):
        text = text[:-1] + '\\"'
    return '"""\n' + text + '"""'


def _value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return _multiline(v) if "\n" in v else _basic(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_value(x) for x in v) + "]"
    raise TypeError(f"unsupported TOML value: {type(v).__name__}")


def _emit(data: dict, prefix: list[str], lines: list[str]) -> None:
    scalars = {k: v for k, v in data.items() if not isinstance(v, dict)}
    tables = {k: v for k, v in data.items() if isinstance(v, dict)}
    if prefix and (scalars or not tables):
        if lines:
            lines.append("")
        lines.append("[" + ".".join(_key(p) for p in prefix) + "]")
    for k, v in scalars.items():
        lines.append(f"{_key(k)} = {_value(v)}")
    for k, v in tables.items():
        _emit(v, [*prefix, k], lines)


def dumps(data: dict) -> str:
    """Scalars first, then [tables]; only the types the generators need."""
    lines: list[str] = []
    _emit(data, [], lines)
    return "\n".join(lines) + "\n"
