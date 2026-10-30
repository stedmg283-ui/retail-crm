"""Convert amounts to Indian-English words (Rupees)."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

ONES = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen",
]
TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _two(n: int) -> str:
    if n < 20:
        return ONES[n]
    return (TENS[n // 10] + (" " + ONES[n % 10] if n % 10 else "")).strip()


def _three(n: int) -> str:
    h = n // 100
    r = n % 100
    parts = []
    if h:
        parts.append(ONES[h] + " Hundred")
    if r:
        parts.append(_two(r))
    return " ".join(parts)


def amount_in_words(amount) -> str:
    """e.g. 1250.50 -> 'Rupees One Thousand Two Hundred Fifty and Fifty Paise Only'."""
    d = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if d < 0:
        d = -d
    rupees = int(d)
    paise = int((d - rupees) * 100)

    if rupees == 0:
        words = "Zero"
    else:
        crore = rupees // 10000000
        lac = (rupees % 10000000) // 100000
        thousand = (rupees % 100000) // 1000
        hundred = rupees % 1000
        parts = []
        if crore:
            parts.append(_two(crore) + " Crore")
        if lac:
            parts.append(_two(lac) + " Lakh")
        if thousand:
            parts.append(_two(thousand) + " Thousand")
        if hundred:
            parts.append(_three(hundred))
        words = " ".join(parts)

    result = f"Rupees {words}"
    if paise:
        result += f" and {_two(paise)} Paise"
    return result + " Only"
