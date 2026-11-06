"""Gehalt erkennen und vergleichen."""

from __future__ import annotations

import pytest

from custom_components.jobradar.pay import (
    grade_from_text,
    pay_from_item,
    pay_label,
    pay_matches,
)
from custom_components.jobradar.scoring import Job, Profile, score_job


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        # So liefert /pc/v6/jobs Gehälter (Werte aus echten Antworten, Nov 2026)
        (
            {
                "verguetungsangabe": "JAHRESGEHALT",
                "artDerVerguetung": "GEHALTSSPANNE",
                "gehaltsspanneVon": 60000,
                "gehaltsspanneBis": 65000.0,
            },
            (60000, 65000),
        ),
        (
            {
                "verguetungsangabe": "JAHRESGEHALT",
                "artDerVerguetung": "FESTGEHALT",
                "festgehalt": 61284.0,
            },
            (61284, 61284),
        ),
        ({"verguetungsangabe": "KEINE_ANGABEN"}, (None, None)),
        ({}, (None, None)),
        # Platzhalter "1" ist kein Gehalt
        (
            {
                "verguetungsangabe": "JAHRESGEHALT",
                "artDerVerguetung": "FESTGEHALT",
                "festgehalt": 1,
            },
            (None, None),
        ),
        # Monatsbetrag
        (
            {
                "verguetungsangabe": "MONATSGEHALT",
                "artDerVerguetung": "FESTGEHALT",
                "festgehalt": 5000,
            },
            (60000, 60000),
        ),
        # Spanne verdreht
        (
            {
                "verguetungsangabe": "JAHRESGEHALT",
                "gehaltsspanneVon": 80000,
                "gehaltsspanneBis": 70000,
            },
            (70000, 80000),
        ),
    ],
)
def test_pay_from_item(item, expected) -> None:
    assert pay_from_item(item) == expected


@pytest.mark.parametrize(
    ("text", "grade", "scale"),
    [
        ("Die Vergütung erfolgt nach Entgeltgruppe 11 TVöD.", 11, "TVöD"),
        ("Eingruppierung je nach Qualifikation bis EG 12 TV-L", 12, "TV-L"),
        ("Bezahlung nach TVöD-VKA in der E 10", 10, "TVöD"),
        ("Systemadministrator (m/w/d) E11 TV-L", 11, "TV-L"),
        ("Entgeltgruppe 9b oder 10 TVöD", 10, "TVöD"),
        ("Besoldungsgruppe A 11 LBesO", 11, "Besoldung A"),
        ("Wir bieten 30 Tage Urlaub und über 5.000 Mitarbeitende", None, ""),
        ("Kenntnisse in E-Mail-Systemen und Exchange 2019", None, ""),
    ],
)
def test_grade_from_text(text, grade, scale) -> None:
    assert grade_from_text(text) == (grade, scale)


def test_label() -> None:
    assert pay_label(60000, 65000, None, "") == "60.000–65.000 €"
    assert pay_label(61284, 61284, None, "") == "61.284 €"
    assert pay_label(None, None, 11, "TVöD") == "TVöD E11"
    assert pay_label(None, None, 12, "Besoldung A") == "Besoldung A12"
    assert pay_label(None, None, None, "") == ""


def test_matches() -> None:
    assert pay_matches(60000, 75000, None, 70000, 11) is True  # Spanne reicht hinauf
    assert pay_matches(55000, 65000, None, 70000, 11) is False
    assert pay_matches(None, None, 11, 70000, 11) is True
    assert pay_matches(None, None, 9, 70000, 11) is False
    assert pay_matches(None, None, None, 70000, 11) is None
    assert pay_matches(55000, 65000, None, 0, 11) is None  # kein Vergleich eingestellt


def test_low_pay_costs_points_and_good_pay_adds() -> None:
    profile = Profile(
        search_terms=("Systemadministrator",),
        skills=("VMware",),
        salary_expectation=70000,
        min_pay_grade=11,
    )
    base = {"refnr": "1", "title": "Systemadministrator VMware (m/w/d)"}
    neutral = score_job(Job(**base), profile)
    low = score_job(Job(**base, pay_low=50000, pay_high=60000), profile)
    good = score_job(Job(**base, pay_low=65000, pay_high=80000), profile)
    grade = score_job(Job(**base, description="Vergütung nach Entgeltgruppe 9a TVöD"), profile)
    assert neutral.pay_ok is None and neutral.score == 60
    assert low.pay_ok is False and low.score == 30
    assert good.pay_ok is True and good.score == 65
    assert grade.pay_ok is False and grade.pay == "TVöD E9"
