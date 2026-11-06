"""Vergütung erkennen und mit der Gehaltsvorstellung vergleichen.

Die Jobbörse liefert bei etwa jeder fünften Stelle ein Gehalt:
verguetungsangabe = JAHRESGEHALT (sonst KEINE_ANGABEN), dazu
artDerVerguetung = GEHALTSSPANNE mit gehaltsspanneVon/-Bis oder
FESTGEHALT mit festgehalt. Stellen im öffentlichen Dienst nennen
stattdessen meist eine Entgeltgruppe im Text ("Entgeltgruppe 11 TVöD").
"""

from __future__ import annotations

import re
from typing import Any

# Plausibler Bereich für ein Jahresbrutto; "festgehalt": 1 kommt als Platzhalter vor
MIN_ANNUAL = 12_000
MAX_ANNUAL = 500_000
HOURS_PER_YEAR = 2080  # 40 Stunden × 52 Wochen


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(".", "").replace(",", ".")) if "," in value else float(value)
        except ValueError:
            return None
    return None


def _annual(value: Any, kind: str) -> int | None:
    number = _number(value)
    if number is None or number <= 0:
        return None
    if "STUNDE" in kind:
        number *= HOURS_PER_YEAR
    elif "MONAT" in kind or number < 15_000:
        # Monatsbetrag, auch wenn er versehentlich als Jahresgehalt markiert ist
        number *= 12
    annual = round(number)
    return annual if MIN_ANNUAL <= annual <= MAX_ANNUAL else None


def pay_from_item(item: dict[str, Any]) -> tuple[int | None, int | None]:
    """Jahresbrutto (von, bis) aus einem Treffer oder einer Detailansicht."""
    kind = str(item.get("verguetungsangabe") or "").upper()
    if not kind or kind == "KEINE_ANGABEN":
        return None, None
    art = str(item.get("artDerVerguetung") or "").upper()
    if art == "GEHALTSSPANNE" or "gehaltsspanneVon" in item or "gehaltsspanneBis" in item:
        low = _annual(item.get("gehaltsspanneVon"), kind)
        high = _annual(item.get("gehaltsspanneBis"), kind)
        if low and high and low > high:
            low, high = high, low
        return low, high
    fixed = _annual(item.get("festgehalt"), kind)
    return fixed, fixed


_SCALE = r"(?:tv[öo]e?d(?:-[a-z]+)?|tv[\s-]?l|tv[\s-]?h|tv[\s-]?v|avr|tarif\w*)"
_GRADE_PATTERNS = (
    # "Entgeltgruppe 11", "Entgeltgruppe E 11", "EG 11", "Entgeltgr. 9b"
    re.compile(r"\b(?:entgeltgruppe|entgeltgr\.?|eg)\s*e?\s*(\d{1,2})\s*[a-c]?\b", re.I),
    # "E 11 TVöD", "E11 TV-L"
    re.compile(rf"\be\s?(\d{{1,2}})\s*[a-c]?\s*(?:\(|,|/)?\s*{_SCALE}", re.I),
    # "TVöD E 11", "TV-L E11", "nach TVöD-VKA in E 10"
    re.compile(rf"{_SCALE}[^.\n]{{0,25}}?\be\s?(\d{{1,2}})\s*[a-c]?\b", re.I),
    # zweite Gruppe einer Spanne: "Entgeltgruppe 9b oder 10", "EG 10 bis 11", "E 9c/10"
    re.compile(
        r"\b(?:entgeltgruppe|entgeltgr\.?|eg|e)\s?e?\s?\d{1,2}\s*[a-c]?\s*"
        r"(?:bis|oder|bzw\.?|/|–|-)\s*(?:entgeltgruppe|eg|e)?\s?(\d{1,2})\b",
        re.I,
    ),
    # Beamte: "Besoldungsgruppe A 11", "BesGr. A 12", "A 11 LBesO"
    re.compile(r"\b(?:besoldungsgruppe|besgr\.?)\s*a\s?(\d{1,2})\b", re.I),
    re.compile(r"\ba\s?(\d{1,2})\s*(?:l?besg?o|bbeso|übesg)\b", re.I),
)


def grade_from_text(text: str) -> tuple[int | None, str]:
    """Höchste genannte Entgelt- oder Besoldungsgruppe und der Tarif dazu."""
    if not text:
        return None, ""
    grades = [
        int(match.group(1))
        for pattern in _GRADE_PATTERNS
        for match in pattern.finditer(text)
        if 1 <= int(match.group(1)) <= 16
    ]
    if not grades:
        return None, ""
    lower = text.lower()
    if re.search(r"besold|\bbes(?:gr)?\.|\bbbeso\b|\blbeso\b", lower):
        scale = "Besoldung A"
    elif re.search(r"tv[\s-]?l\b", lower):
        scale = "TV-L"
    elif re.search(r"tv[öo]e?d", lower):
        scale = "TVöD"
    elif re.search(r"tv[\s-]?h\b", lower):
        scale = "TV-H"
    else:
        scale = "Tarif"
    return max(grades), scale


def pay_label(low: int | None, high: int | None, grade: int | None, scale: str) -> str:
    """Kurze Angabe für Meldung und Sensor."""

    def euro(value: int) -> str:
        return f"{value:,}".replace(",", ".") + " €"

    if low and high and low != high:
        return f"{euro(low).removesuffix(' €')}–{euro(high)}"
    if low or high:
        return euro(low or high)  # type: ignore[arg-type]
    if grade:
        prefix = "A" if scale == "Besoldung A" else "E"
        name = "Besoldung" if scale == "Besoldung A" else scale
        return f"{name} {prefix}{grade}".strip()
    return ""


def pay_matches(
    low: int | None,
    high: int | None,
    grade: int | None,
    expectation: int,
    min_grade: int,
) -> bool | None:
    """True = passt, False = darunter, None = keine Angabe oder kein Vergleich eingestellt."""
    if low or high:
        if not expectation:
            return None
        return (high or low or 0) >= expectation
    if grade and min_grade:
        return grade >= min_grade
    return None
