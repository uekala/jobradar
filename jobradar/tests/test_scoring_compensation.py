from app.scoring import evaluate_vacancy


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
    assert evaluate_vacancy(lower, profile, []) == (32, False)


def test_unknown_salary_and_tariff_grade_do_not_change_base_score():
    profile = {"salary_min": 70000, "public_service_minimum": "TVöD EG 11"}
    vacancy = {"title": "Systemadministrator", "company": "Land NRW", "description": "IT-Infrastruktur"}
    assert evaluate_vacancy(vacancy, profile, []) == (40, False)
