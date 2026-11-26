"""Secret redaction applied before anything is written to the audit log, memory or handovers."""

import re

MASK = "[REDACTED]"

_TOKEN_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"xox[abeprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{10,}"),  # JWT
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"),                                          # Google API key
    re.compile(r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,}"),                            # Stripe secret keys
    re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}"),                                        # GitLab
    re.compile(r"\bnpm_[A-Za-z0-9]{30,}"),                                            # npm
]
# Patterns whose first group is kept as a label and the rest masked.
_LABELLED = [
    re.compile(r"(?i)(\bBearer\s+)[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"(?i)(\b[a-z][a-z0-9+.-]*://[^\s:/@]+:)[^\s@/]+(?=@)"),               # user:PASSWORD@host
]
# key=value / key: value / "key": "value", where the key contains a secret-ish word, e.g.
# client_secret, AWS_SECRET_ACCESS_KEY, db-password. "tokens" or "secretary" do not match.
_KEYWORD = re.compile(
    r"(?i)(?<![A-Za-z0-9])((?:[a-z0-9]+[_-])*(?:password|passwd|pwd|secret|api[_-]?key|access[_-]?key|"
    r"private[_-]?key|token|credentials?)(?:[_-][a-z0-9]+)*)(?![A-Za-z0-9])"
    r"([\"']?\s*[:=]\s*[\"']?)([^\s\"',;}]+)")


def redact(text: str) -> tuple[str, int]:
    count = 0
    for pattern in _TOKEN_PATTERNS:
        text, n = pattern.subn(MASK, text)
        count += n
    for pattern in _LABELLED:
        text, n = pattern.subn(lambda m: m.group(1) + MASK, text)
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
