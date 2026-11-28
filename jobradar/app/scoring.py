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


def evaluate_vacancy_detailed(
    vacancy: dict[str, Any], profile: dict[str, Any], rules: list[dict[str, Any]]
) -> dict[str, Any]:
    """Return the score, exclusion flag and an auditable list of score contributions."""
    haystack = " ".join(_text(vacancy.get(key)) for key in ("title", "company", "location", "description"))
    company = _text(vacancy.get("company"))
    excluded_by = next((term for term in _terms(profile.get("exclusions")) if term.casefold() in company), None)
    if excluded_by:
        return {"score": 0, "excluded": True, "base_score": 0, "breakdown": [{"label": "Unternehmens-Ausschluss", "points": 0, "detail": excluded_by}]}

    roles = _terms(profile.get("roles"))
    skills = _terms(profile.get("skills"))
    role_matches = [term for term in roles if term.casefold() in haystack]
    skill_matches = [term for term in skills if term.casefold() in haystack]
    role_points = min(40, len(role_matches) * 12)
    skill_points = min(24, len(skill_matches) * 4)
    score = 40 + role_points + skill_points
    breakdown = [
        {"label": "Grundwert", "points": 40, "detail": "Startwert jeder nicht ausgeschlossenen Anzeige"},
        {"label": "Zielpositionen", "points": role_points, "detail": f"{len(role_matches)} Treffer: {', '.join(role_matches) if role_matches else 'keine'}"},
        {"label": "Kenntnisse", "points": skill_points, "detail": f"{len(skill_matches)} Treffer: {', '.join(skill_matches) if skill_matches else 'keine'}"},
    ]

    target_salary = profile.get("salary_min")
    actual_min, actual_max = vacancy.get("salary_min"), vacancy.get("salary_max")
    salary_points = 0
    salary_detail = "Keine ausreichenden Gehaltsangaben – neutral"
    if isinstance(target_salary, (int, float)) and target_salary > 0:
        if isinstance(actual_min, (int, float)) and actual_min >= target_salary:
            salary_points, salary_detail = 8, f"Mindestgehalt {actual_min:,.0f} € erreicht das Ziel {target_salary:,.0f} €"
        elif isinstance(actual_max, (int, float)) and actual_max < target_salary:
            salary_points, salary_detail = -8, f"Höchstgehalt {actual_max:,.0f} € liegt unter dem Ziel {target_salary:,.0f} €"
    score += salary_points
    breakdown.append({"label": "Gehaltsziel", "points": salary_points, "detail": salary_detail})

    target_grade = _eg_level(_text(profile.get("public_service_minimum")))
    vacancy_grade = _eg_level(haystack)
    grade_points = 0
    grade_detail = "Keine vergleichbare Entgeltgruppe erkannt – neutral"
    if target_grade is not None and vacancy_grade is not None:
        grade_points = 8 if vacancy_grade >= target_grade else -8
        grade_detail = f"Erkannte EG {vacancy_grade}, Ziel EG {target_grade}"
    score += grade_points
    breakdown.append({"label": "Öffentlicher Dienst", "points": grade_points, "detail": grade_detail})

    for rule in rules:
        data = rule.get("data", rule)
        if rule.get("enabled") is False or data.get("enabled") is False:
            continue
        # scope "title": nur im Titel suchen, z. B. für „Junior“ oder „Praktikum“, die in
        # Beschreibungen guter Stellen oft nebenbei vorkommen.
        text = _text(vacancy.get("title")) if data.get("scope") == "title" else haystack
        matches = [term for term in _terms(data.get("terms")) if term.casefold() in text]
        if not matches:
            continue
        category = data.get("category", "positive")
        if category == "exclude":
            return {"score": 0, "excluded": True, "base_score": 0, "breakdown": [*breakdown, {"label": "Ausschlussregel", "points": 0, "detail": ", ".join(matches)}]}
        weight = max(-100, min(100, int(data.get("weight", 0) or 0)))
        points = abs(weight) if category == "positive" else -abs(weight)
        score += points
        breakdown.append({"label": str(data.get("name") or rule.get("id") or "Bewertungsregel"), "points": points, "detail": f"{category}: {', '.join(matches)}"})

    base_score = max(0, min(100, round(score)))
    return {"score": base_score, "base_score": base_score, "excluded": False, "breakdown": breakdown}


def evaluate_vacancy(vacancy: dict[str, Any], profile: dict[str, Any], rules: list[dict[str, Any]]) -> tuple[int, bool]:
    """Backward-compatible score API."""
    result = evaluate_vacancy_detailed(vacancy, profile, rules)
    return result["score"], result["excluded"]
