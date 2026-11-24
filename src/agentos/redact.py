"""Secret redaction applied before anything is written to the audit log, memory or handovers."""

import re

MASK = "[REDACTED]"

_TOKEN_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}"),
]
_KEYWORD = re.compile(r"(?i)\b(password|passwd|secret|api[_-]?key|token)\b(\s*[:=]\s*)(\S+)")


def redact(text: str) -> tuple[str, int]:
    count = 0
    for pattern in _TOKEN_PATTERNS:
        text, n = pattern.subn(MASK, text)
        count += n

    def _mask_value(m: re.Match) -> str:
        nonlocal count
        if m.group(3) == MASK:
            return m.group(0)
        count += 1
        return f"{m.group(1)}{m.group(2)}{MASK}"

    text = _KEYWORD.sub(_mask_value, text)
    return text, count


def redact_obj(obj):
    if isinstance(obj, str):
        return redact(obj)[0]
    if isinstance(obj, dict):
        return {k: redact_obj(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [redact_obj(v) for v in obj]
    return obj
