from app.scoring import evaluate_vacancy, evaluate_vacancy_detailed


def test_salary_and_public_service_grade_are_scored_only_when_known():
    profile = {"salary_min": 70000, "public_service_minimum": "TVöD EG 11"}
    vacancy = {
        "title": "Systemadministrator",
        "company": "Land NRW",
        "description": "TVöD EG 12",
        "salary_min": 72000,
    }
    assert evaluate_vacancy(vacancy, profile, []) == (56, False)

    lower = {**vacancy, "description": "TVöD EG 9", "salary_max": 65000, "salary_min": None}
    assert evaluate_vacancy(lower, profile, []) == (24, False)


def test_unknown_salary_and_tariff_grade_do_not_change_base_score():
    profile = {"salary_min": 70000, "public_service_minimum": "TVöD EG 11"}
    vacancy = {"title": "Systemadministrator", "company": "Land NRW", "description": "IT-Infrastruktur"}
    assert evaluate_vacancy(vacancy, profile, []) == (40, False)



def test_detailed_evaluation_explains_compensation_and_role_matches():
    profile = {
        "roles": ["Systemadministrator"],
        "skills": ["VMware"],
        "salary_min": 70000,
        "public_service_minimum": "TVöD EG 11",
    }
    vacancy = {
        "title": "Systemadministrator VMware",
        "company": "Land NRW",
        "description": "TVöD EG 12",
        "salary_min": 72000,
    }

    result = evaluate_vacancy_detailed(vacancy, profile, [])

    assert result["score"] == 72
    assert result["excluded"] is False
    assert [item["label"] for item in result["breakdown"]] == [
        "Grundwert",
        "Zielpositionen",
        "Kenntnisse",
        "Gehaltsziel",
        "Öffentlicher Dienst",
    ]
    assert sum(item["points"] for item in result["breakdown"]) == result["score"]
    assert result["breakdown"][3]["points"] == 8
    assert result["breakdown"][4]["points"] == 8


def test_detailed_evaluation_explains_exclusion_rule():
    rules = [{
        "id": "agency-exclusion",
        "data": {
            "name": "Zeitarbeit ausschließen",
            "category": "exclude",
            "terms": ["Zeitarbeit"],
            "weight": 0,
        },
    }]
    result = evaluate_vacancy_detailed(
        {"title": "Systemadministrator", "company": "Zeitarbeit GmbH"},
        {},
        rules,
    )

    assert result["excluded"] is True
    assert result["score"] == 0
    assert result["breakdown"][-1]["label"] == "Ausschlussregel"
