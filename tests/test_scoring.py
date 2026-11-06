"""Bewertung von Stellen."""

from __future__ import annotations

from custom_components.jobradar.scoring import Job, Profile, normalize, parse_list, score_job

PROFILE = Profile(
    search_terms=("Systemadministrator", "IT-Administrator", "VMware", "Cloud Engineer"),
    skills=("VMware", "Ansible", "Linux", "Windows Server", "Kubernetes"),
    unwanted=("Junior", "Helpdesk", "Vertrieb"),
    excluded_words=("Ausbildung", "Werkstudent"),
    excluded_employers=("Stadt Krefeld", "KRZN"),
)


def scored(title: str, **kwargs) -> Job:
    return score_job(Job(refnr="1", title=title, **kwargs), PROFILE)


def test_normalize_and_lists() -> None:
    assert normalize("IT-Administrator (m/w/d)") == normalize("IT Administrator mwd")
    assert normalize("Straße") == "strasse"
    assert parse_list("VMware, Linux\nAnsible;  , vmware") == ["VMware", "Linux", "Ansible"]
    assert parse_list(None) == []


def test_role_in_title_is_enough_for_a_notification() -> None:
    job = scored("System-Administrator (m/w/d)")
    assert job.score == 50
    assert job.excluded is None


def test_generic_role_word_with_skill_counts_as_role() -> None:
    job = scored("Administrator Linux (m/w/d)")
    assert job.score == 60
    assert job.matches == ["Linux"]


def test_skills_from_title_and_description_are_capped() -> None:
    job = scored(
        "VMware Systemadministrator Linux Kubernetes Ansible Windows Server",
        description="viel VMware und Ansible",
    )
    assert job.score == 90  # 50 Rolle + 40 Fähigkeiten (gedeckelt)
    job = scored("Systemadministrator", description="Wir nutzen Ansible und Windows Server.")
    assert job.score == 60
    assert job.matches == ["Ansible", "Windows Server"]


def test_unwanted_words_lower_the_score() -> None:
    assert scored("Junior Systemadministrator Helpdesk").score == 0


def test_excluded_employer_and_words() -> None:
    assert scored(
        "IT-Administrator", employer="Stadt Krefeld – Fachbereich IT"
    ).excluded.startswith("Arbeitgeber")
    assert scored("Werkstudent Systemadministrator").excluded.startswith("Ausschlusswort")


def test_remote_and_nearby_bonus() -> None:
    assert scored("Systemadministrator", remote=True).score == 55
    assert scored("Systemadministrator", distance_km=12.0).score == 55
    assert scored("Systemadministrator", distance_km=40.0).score == 50


def test_unrelated_title_scores_low() -> None:
    assert scored("Vertriebsmitarbeiter Innendienst").score == 0
    assert scored("Kaufmann im Einzelhandel").score == 0


def test_round_trip_dict() -> None:
    job = scored("Systemadministrator", employer="Muster GmbH", remote=True, distance_km=3.2)
    again = Job.from_dict(job.as_dict())
    assert again == job
    assert again.url.endswith("/jobdetail/1")
