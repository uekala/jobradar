"""Jobradar in einem echten Test-Home-Assistant."""

from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_time_changed,
)

from custom_components.jobradar.const import (
    CONF_EXCLUDED_EMPLOYERS,
    CONF_LOCATION,
    CONF_MIN_GRADE,
    CONF_MIN_SCORE,
    CONF_NOTIFY,
    CONF_RADIUS,
    CONF_REMOTE,
    CONF_SALARY,
    CONF_SEARCH_TERMS,
    CONF_SKILLS,
    DOMAIN,
    EVENT_NEW_JOB,
)

from .conftest import days_ago, job

BASE = {
    CONF_LOCATION: "Krefeld",
    CONF_RADIUS: 50,
    CONF_REMOTE: True,
    CONF_SEARCH_TERMS: (
        "Systemadministrator, IT-Administrator, Administrator, Cloud Engineer, VMware"
    ),
    CONF_SKILLS: "VMware, Ansible, Linux, Windows Server, Kubernetes",
    CONF_EXCLUDED_EMPLOYERS: "Stadt Krefeld, KRZN",
    CONF_MIN_SCORE: 50,
    CONF_NOTIFY: "notify.mobile_app_handy",
}

pytestmark = pytest.mark.usefixtures("no_pause", "at_home")


@pytest.fixture
def pushes(hass: HomeAssistant) -> list[ServiceCall]:
    calls: list[ServiceCall] = []

    async def capture(call: ServiceCall) -> None:
        calls.append(call)

    hass.services.async_register("notify", "mobile_app_handy", capture)
    return calls


async def _setup(hass: HomeAssistant, **overrides) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title="Jobradar Krefeld", data={**BASE, **overrides})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    return entry


async def _next_run(hass: HomeAssistant) -> None:
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=31))
    await hass.async_block_till_done(wait_background_tasks=True)


def _state(hass: HomeAssistant, key: str):
    return hass.states.get(f"sensor.jobradar_krefeld_{key}")


async def test_first_run_lists_matches_and_sends_one_summary(hass, jobboerse, pushes) -> None:
    await _setup(hass)

    new = _state(hass, "new_jobs")
    assert new.state == "2"
    listed = {s["titel"]: s for s in new.attributes["stellen"]}
    assert set(listed) == {
        "Systemadministrator (m/w/d) Linux und VMware",
        "Cloud Engineer (m/w/d) Kubernetes",
    }
    admin = listed["Systemadministrator (m/w/d) Linux und VMware"]
    assert admin["treffer"] == ["VMware", "Ansible", "Linux", "Windows Server"]
    assert admin["homeoffice"] is True  # aus der Detailansicht
    assert admin["gehalt"] == "nach Vereinbarung"
    assert 15 < admin["entfernung_km"] < 30
    assert admin["url"].endswith("/jobdetail/10000-0000000001-S")
    assert listed["Cloud Engineer (m/w/d) Kubernetes"]["homeoffice"] is True

    # Ausgeschlossener Arbeitgeber, Ausbildung, Vertrieb und Junior-Helpdesk tauchen nicht auf
    titles = " ".join(listed)
    assert "Stadt Krefeld" not in str(new.attributes)
    assert "Ausbildung" not in titles and "Vertrieb" not in titles and "Junior" not in titles

    assert len(pushes) == 1
    assert pushes[0].data["title"] == "Jobradar ist aktiv"
    assert "2 passende Stellen" in pushes[0].data["message"]

    first = next(c for c in jobboerse.search_calls if c.get("wo") == "Krefeld")
    assert first["umkreis"] == "50" and first["veroeffentlichtseit"] == "14"
    assert first["zeitarbeit"] == "false"
    remote = next(c for c in jobboerse.search_calls if c.get("arbeitszeit") == "ho")
    assert "wo" not in remote


async def test_diagnostics_show_hits_without_private_data(hass, jobboerse, pushes) -> None:
    from custom_components.jobradar.diagnostics import async_get_config_entry_diagnostics

    entry = await _setup(hass)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["hits"] >= 5 and diag["matching_jobs"] == 2
    shape = diag["response_shapes"]["/pc/v6/jobs"]
    assert "ergebnisliste" in shape["keys"] and "referenznummer" in shape["item_keys"]
    assert shape["item_nested"]["stellenlokationen.adresse"] == ["ort", "plz", "region"]
    assert "Stadt Krefeld" not in str(diag) and "KRZN" not in str(diag)


async def test_new_job_is_pushed_with_buttons_and_event(hass, jobboerse, pushes) -> None:
    await _setup(hass)
    events = async_capture_events(hass, EVENT_NEW_JOB)
    pushes.clear()
    jobboerse.local.append(
        job(
            "10000-0000000009-S",
            "Systemadministrator VMware (m/w/d)",
            "Neue Firma GmbH",
            "Krefeld",
            51.34,
            6.59,
        )
    )

    await _next_run(hass)

    assert len(pushes) == 1
    push = pushes[0].data
    assert push["title"] == "Systemadministrator VMware (m/w/d)"
    assert push["message"].startswith("Neue Firma GmbH, Krefeld, 0 km. Passt zu")
    actions = push["data"]["actions"]
    assert actions[0] == {"action": "URI", "title": "Öffnen", "uri": push["data"]["url"]}
    assert actions[1]["action"] == "JOBRADAR_HIDE::10000-0000000009-S"
    assert len(events) == 1 and events[0].data["refnr"] == "10000-0000000009-S"
    assert _state(hass, "new_jobs").state == "3"
    later = [c for c in jobboerse.search_calls if c.get("veroeffentlichtseit") == "2"]
    assert later, "nach dem ersten Lauf wird nur noch nach frischen Stellen gefragt"

    # Nichts Neues: keine weitere Meldung
    pushes.clear()
    await _next_run(hass)
    assert pushes == []

    # Knopf "Nicht interessant" in der Benachrichtigung blendet die Stelle aus
    hass.bus.async_fire(
        "mobile_app_notification_action", {"action": "JOBRADAR_HIDE::10000-0000000009-S"}
    )
    await hass.async_block_till_done()
    assert _state(hass, "matching_jobs").state == "2"


async def test_old_and_duplicate_postings_are_not_reported(hass, jobboerse, pushes) -> None:
    await _setup(hass)
    pushes.clear()
    # v6 liefert trotz veroeffentlichtseit=2 auch ältere Stellen
    jobboerse.local.append(
        job(
            "10000-0000000010-S",
            "Systemadministrator VMware (m/w/d)",
            "Alte Anzeige GmbH",
            "Krefeld",
            51.34,
            6.59,
            published=days_ago(9),
        )
    )
    # Dieselbe Stelle für zwei Standorte
    for refnr, place in (("10000-0000000011-S", "Neuss"), ("10000-0000000012-S", "Moers")):
        jobboerse.local.append(
            job(refnr, "Linux-Administrator (m/w/d)", "Doppel AG", place, 51.3, 6.6)
        )

    await _next_run(hass)

    assert [p.data["title"] for p in pushes] == ["Linux-Administrator (m/w/d)"]
    assert pushes[0].data["message"].startswith("Doppel AG, Neuss")


async def test_salary_expectation(hass, jobboerse, pushes) -> None:
    await _setup(hass, **{CONF_SALARY: 70000, CONF_MIN_GRADE: 11})
    pushes.clear()
    pay = {"verguetungsangabe": "JAHRESGEHALT", "artDerVerguetung": "GEHALTSSPANNE"}
    jobboerse.local += [
        job(
            "10000-0000000020-S",
            "Systemadministrator VMware (m/w/d)",
            "Gut Zahlend GmbH",
            "Krefeld",
            51.34,
            6.59,
            **pay,
            gehaltsspanneVon=65000,
            gehaltsspanneBis=80000,
        ),
        job(
            "10000-0000000021-S",
            "Systemadministrator VMware (m/w/d) Rechenzentrum",
            "Knapp Kasse AG",
            "Krefeld",
            51.34,
            6.59,
            **pay,
            gehaltsspanneVon=42000,
            gehaltsspanneBis=50000,
        ),
    ]

    await _next_run(hass)

    assert [p.data["title"] for p in pushes] == ["Systemadministrator VMware (m/w/d)"]
    assert "65.000–80.000 €" in pushes[0].data["message"]
    listed = {s["refnr"]: s for s in _state(hass, "matching_jobs").attributes["stellen"]}
    assert listed["10000-0000000020-S"]["gehalt_passt"] is True
    assert "10000-0000000021-S" not in listed  # 42–50 T€ kostet 30 Punkte


async def test_buttons_and_services(hass, jobboerse, pushes) -> None:
    await _setup(hass)
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.jobradar_krefeld_mark_all_as_read"}, blocking=True
    )
    assert _state(hass, "new_jobs").state == "0"
    assert _state(hass, "matching_jobs").state == "2"

    await hass.services.async_call(DOMAIN, "hide", {"refnr": "10000-0000000004-S"}, blocking=True)
    assert _state(hass, "matching_jobs").state == "1"

    pushes.clear()
    await hass.services.async_call(DOMAIN, "reset", {}, blocking=True)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert _state(hass, "matching_jobs").state == "2"
    assert pushes[0].data["title"] == "Jobradar ist aktiv"


async def test_outage_keeps_known_jobs(hass, jobboerse, pushes) -> None:
    entry = await _setup(hass)
    jobboerse.fail = True
    await _next_run(hass)
    assert entry.runtime_data.last_update_success is False
    state = _state(hass, "matching_jobs")
    assert state.state == "2"


async def test_jobs_survive_restart_and_follow_new_exclusions(hass, jobboerse, pushes) -> None:
    entry = await _setup(hass)
    hass.config_entries.async_update_entry(
        entry, options={**BASE, CONF_EXCLUDED_EMPLOYERS: "Stadt Krefeld, Remote AG"}
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    state = _state(hass, "matching_jobs")
    assert state.state == "1"
    assert state.attributes["stellen"][0]["arbeitgeber"] == "Muster IT GmbH"
    # Kein zweiter Start-Hinweis nach dem Neuladen
    assert [c.data["title"] for c in pushes].count("Jobradar ist aktiv") == 1


async def test_without_phone_uses_ha_notification(hass, jobboerse) -> None:
    calls: list[ServiceCall] = []

    async def capture(call: ServiceCall) -> None:
        calls.append(call)

    hass.services.async_register("persistent_notification", "create", capture)
    await _setup(hass, **{CONF_NOTIFY: ""})
    assert calls[0].data["title"] == "Jobradar ist aktiv"
    assert calls[0].data["notification_id"] == "jobradar_info"


async def test_config_flow(hass) -> None:
    hass.services.async_register("notify", "mobile_app_handy", lambda call: None)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    bad = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**BASE, CONF_SEARCH_TERMS: " , "}
    )
    assert bad["errors"] == {CONF_SEARCH_TERMS: "no_terms"}
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("custom_components.jobradar.async_setup_entry", _ok)
        done = await hass.config_entries.flow.async_configure(result["flow_id"], BASE)
    assert done["type"] is FlowResultType.CREATE_ENTRY
    assert done["title"] == "Jobradar Krefeld"
    assert done["data"][CONF_NOTIFY] == "notify.mobile_app_handy"


async def _ok(hass, entry) -> bool:
    return True
