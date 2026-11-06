from app.scoring import evaluate_vacancy


def test_profile_and_rules_contribute_to_match_score():
    vacancy = {
        "title": "Linux Systemadministrator",
        "company": "Land NRW",
        "location": "Düsseldorf",
        "description": "VMware vSphere und TVöD EG 11",
    }
    profile = {
        "roles": ["Systemadministrator"],
        "skills": ["Linux", "VMware"],
        "public_service_minimum": "TVöD EG 11",
        "exclusions": ["Stadt Krefeld"],
    }
    rules = [
        {"id": "linux", "data": {"category": "positive", "terms": ["Linux"], "weight": 10}},
        {"id": "agency", "data": {"category": "negative", "terms": ["Zeitarbeit"], "weight": 8}},
    ]

    score, excluded = evaluate_vacancy(vacancy, profile, rules)
    assert excluded is False
    assert score == 78


def test_profile_and_rule_exclusions_reject_vacancy():
    vacancy = {"title": "IT Administrator", "company": "Stadt Krefeld", "description": ""}
    profile = {"exclusions": ["Stadt Krefeld"]}
    assert evaluate_vacancy(vacancy, profile, []) == (0, True)

    rules = [{"data": {"category": "exclude", "terms": ["IT Administrator"], "enabled": True}}]
    assert evaluate_vacancy(vacancy, {}, rules) == (0, True)


def test_disabled_rules_are_ignored_and_scores_are_bounded():
    vacancy = {"title": "Principal Linux Kubernetes VMware Architect", "company": "Example"}
    rules = [
        {"data": {"category": "positive", "terms": ["Linux"], "weight": 1000, "enabled": False}},
        {"data": {"category": "positive", "terms": ["Kubernetes"], "weight": 100}},
    ]
    score, excluded = evaluate_vacancy(vacancy, {"roles": ["Linux"], "skills": ["Kubernetes"]}, rules)
    assert excluded is False
    assert score == 100
