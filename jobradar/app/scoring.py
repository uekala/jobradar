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


def _eg_level(value: str) -> int | None:
    match = re.search(r"\b(?:eg|e)\s*(\d{1,2})\b", value.casefold())
    return int(match.group(1)) if match else None


def evaluate_vacancy(vacancy: dict[str, Any], profile: dict[str, Any], rules: list[dict[str, Any]]) -> tuple[int, bool]:
    """Return (0..100 score, excluded). Missing salary/tariff data stays neutral."""
    haystack = " ".join(_text(vacancy.get(key)) for key in ("title", "company", "location", "description"))
    company = _text(vacancy.get("company"))
    if any(term.casefold() in company for term in _terms(profile.get("exclusions"))):
        return 0, True

    roles = _terms(profile.get("roles"))
    skills = _terms(profile.get("skills"))
    role_hits = sum(1 for term in roles if term.casefold() in haystack)
    skill_hits = sum(1 for term in skills if term.casefold() in haystack)
    score = 40 + min(40, role_hits * 12) + min(24, skill_hits * 4)

    target_salary = profile.get("salary_min")
    actual_min = vacancy.get("salary_min")
    actual_max = vacancy.get("salary_max")
    if isinstance(target_salary, (int, float)) and target_salary > 0:
        if isinstance(actual_min, (int, float)) and actual_min >= target_salary:
            score += 8
        elif isinstance(actual_max, (int, float)) and actual_max < target_salary:
            score -= 8

    target_grade = _eg_level(_text(profile.get("public_service_minimum")))
    vacancy_grade = _eg_level(haystack)
    if target_grade is not None and vacancy_grade is not None:
        score += 8 if vacancy_grade >= target_grade else -8

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
