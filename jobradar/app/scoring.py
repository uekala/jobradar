"""Deterministic profile and rule based vacancy scoring."""
from __future__ import annotations

import re
from typing import Any


def _text(value: Any) -> str:
    return str(value or "").casefold()


def _terms(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip() for value in value.splitlines() if value.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def evaluate_vacancy(vacancy: dict[str, Any], profile: dict[str, Any], rules: list[dict[str, Any]]) -> tuple[int, bool]:
    """Return (0..100 score, excluded). Unknown salary/public-sector data is neutral."""
    haystack = " ".join(_text(vacancy.get(key)) for key in ("title", "company", "location", "description"))
    company = _text(vacancy.get("company"))
    exclusions = _terms(profile.get("exclusions"))
    if any(term.casefold() in company for term in exclusions):
        return 0, True

    roles = _terms(profile.get("roles"))
    skills = _terms(profile.get("skills"))
    role_hits = sum(1 for term in roles if term.casefold() in haystack)
    skill_hits = sum(1 for term in skills if term.casefold() in haystack)
    score = 40 + min(40, role_hits * 12) + min(24, skill_hits * 4)

    minimum = _text(profile.get("public_service_minimum"))
    if minimum:
        markers = ("tvöd", "tv-l", "besoldung", "beamtenverhältnis", "tarifbeschäftigte")
        if any(marker in haystack for marker in markers):
            score += 8

    for rule in rules:
        if rule.get("enabled") is False:
            continue
        data = rule.get("data", rule)
        matched = any(term.casefold() in haystack for term in _terms(data.get("terms")))
        if not matched:
            continue
        category = data.get("category", "positive")
        if category == "exclude":
            return 0, True
        weight = max(-100, min(100, int(data.get("weight", 0) or 0)))
        score += abs(weight) if category == "positive" else -abs(weight)

    return max(0, min(100, int(round(score)))), False
