"""Config helpers."""
from __future__ import annotations

from datetime import date


def financial_year(d: date | None = None) -> str:
    """Indian FY label, e.g. 2026-27 for dates from Apr 2026 – Mar 2027."""
    d = d or date.today()
    if d.month >= 4:
        return f"{d.year}-{str(d.year + 1)[-2:]}"
    return f"{d.year - 1}-{str(d.year)[-2:]}"
