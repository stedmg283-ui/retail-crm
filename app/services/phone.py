"""Phone normalization to E.164 (default India +91)."""
from __future__ import annotations

import re


def normalize_phone(raw: str | None, default_cc: str = "91") -> str | None:
    """Return E.164 phone or None if empty/invalid."""
    if not raw:
        return None
    s = re.sub(r"[^\d+]", "", str(raw).strip())
    if not s:
        return None
    if s.startswith("+"):
        digits = re.sub(r"\D", "", s)
        if len(digits) < 10:
            return None
        return f"+{digits}"
    digits = re.sub(r"\D", "", s)
    # Strip leading 0 for Indian mobiles
    if digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) == 10:
        return f"+{default_cc}{digits}"
    if digits.startswith(default_cc) and len(digits) >= 12:
        return f"+{digits}"
    if len(digits) >= 10:
        return f"+{digits}"
    return None
