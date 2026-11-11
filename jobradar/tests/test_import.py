import copy
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from app.database import connect
from app.importer import split_list
from app.main import app
from app.scoring import evaluate_vacancy
from fastapi.testclient import TestClient

FIXTURE = Path(__file__).parent / "fixtures" / "export_beispiel.json"


def load_export():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBRADAR_DB_PATH", str(tmp_path / "jobradar.sqlite3"))
    monkeypatch.setenv("JOBRADAR_BACKUP_DIR", str(tmp_path / "backups"))
    with TestClient(app) as test_client:
        yield test_client


def counts(db_path):
    with connect(db_path) as db:
        return {
            table: db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("jobs", "runs", "profile", "search_rules", "imports", "import_archive")
        }


def test_split_list_keeps_commas_inside_parentheses():
    assert split_list("Linux, VMware vSphere (Cluster, viele VMs), Ansible") == [
        "Linux",
        "VMware vSphere (Cluster, viele VMs)",
        "Ansible",
    ]
    assert split_list("a\nb, c") == ["a", "b", "c"]
    assert split_list("") == []


def test_dry_run_reports_everything_and_writes_nothing(client, tmp_path):
    response = client.post("/api/import", json=load_export())

    assert response.status_code == 200
    report = response.json()
    assert report["dry_run"] is True
    assert report["applied"] is False
    assert report["errors"] == []
    assert report["collections"]["jobs"] == {"found": 3, "already_imported": 0, "to_import": 3}
    assert report["archive_documents"] == 8
    statuses = {job["id"]: job["status_new"] for job in report["jobs"]}
    assert statuses == {
        "beispiel-a-systemadministrator": "neu",
        "beispiel-b-cloud-engineer": "gemerkt",
        "beispiel-c-helpdesk": "verworfen",
    }
    assert any("abgeschnitten" in warning for warning in report["warnings"])
    assert any("karriereseiten" in warning for warning in report["warnings"])
    assert "pflege/stand" in report["archived_only"]
    assert counts(tmp_path / "jobradar.sqlite3") == {
        "jobs": 0, "runs": 0, "profile": 0, "search_rules": 0, "imports": 0, "import_archive": 0,
    }


def test_import_keeps_ids_status_notes_scores_and_archives_every_document(client, tmp_path):
    export = load_export()
    response = client.post("/api/import?dry_run=false", json=export)

    assert response.status_code == 200
    report = response.json()
    assert report["applied"] is True
    assert report["import_id"] == 1

    db_file = tmp_path / "jobradar.sqlite3"
    with connect(db_file) as db:
        jobs = {row["id"]: dict(row) for row in db.execute("SELECT * FROM jobs")}
        runs = [dict(row) for row in db.execute("SELECT * FROM runs ORDER BY id")]
        profile = json.loads(db.execute("SELECT data_json FROM profile WHERE id = 1").fetchone()[0])
        rules = {row["id"]: json.loads(row["data_json"]) for row in db.execute("SELECT * FROM search_rules")}
        archive = {row["path"]: dict(row) for row in db.execute("SELECT * FROM import_archive")}

    a = jobs["beispiel-a-systemadministrator"]
    assert a["title"] == "Systemadministrator Linux (m/w/d)"
    assert a["company"] == "Beispiel Werke GmbH"
    assert a["status"] == "neu"
    assert (a["score"], a["base_score"], a["imported_score"]) == (88, 88, 88)
    assert a["remote_type"] == "homeoffice"
    assert a["published_at"] == "2025-12-30"
    assert a["first_seen_at"] == "2026-01-02T06:00:00Z"
    b = jobs["beispiel-b-cloud-engineer"]
    assert b["status"] == "gemerkt"
    assert b["notes"] == "Ansprechpartnerin angerufen, Rückmeldung bis Freitag"
    assert b["updated_at"] == "2026-01-02T09:29:59Z"
    c = jobs["beispiel-c-helpdesk"]
    assert c["status"] == "verworfen"
    assert c["url"].endswith("-inline.")  # stored as exported, not repaired
    assert c["published_at"] is None

    assert [run["started_at"] for run in runs] == ["2026-01-01T06:00:00Z", "2026-01-02T06:00:00Z"]
    assert runs[0]["jobs_found"] == 1 and runs[0]["note"] == "Erster Lauf."
    assert runs[1]["jobs_found"] == 15 and runs[1]["jobs_new"] == 2

    assert profile == {
        "location": "Musterstadt",
        "radius_km": 40,
        "nationwide_remote": True,
        "roles": ["Systemadministrator", "Cloud- oder Platform-Engineer"],
        "skills": ["Linux", "VMware vSphere (Cluster, viele VMs)", "Ansible"],
        "salary_min": 65000,
        "public_service_minimum": "EG 10",
        "exclusions": ["Beispiel Behörde", "Muster Rechenzentrum"],
        "preferences_raw": "zwei Tage Homeoffice",
    }
    assert rules == {
        "uebernommen-abwerten": {
            "name": "Abwerten (übernommen)",
            "category": "negative",
            "terms": ["Junior", "Helpdesk", "1st Level"],
            "weight": 25,
            "description": "Aus dem bisherigen Jobradar übernommen; dort −25 Punkte je Wort im Titel.",
            "enabled": True,
        }
    }

    assert len(archive) == 8
    for name, entries in export["collections"].items():
        for entry in entries:
            stored = archive[f"{name}/{entry['id']}"]
            assert json.loads(stored["data_json"]) == entry["data"]
            assert stored["version"] == entry["version"]
            assert stored["updated_at"] == entry["updatedAt"]
    original = json.loads(jobs["beispiel-b-cloud-engineer"]["import_json"])
    assert original == export["collections"]["jobs"][1]


def test_second_import_changes_nothing(client, tmp_path):
    export = load_export()
    assert client.post("/api/import?dry_run=false", json=export).json()["applied"] is True
    before = counts(tmp_path / "jobradar.sqlite3")

    again = client.post("/api/import?dry_run=false", json=export)

    assert again.status_code == 200
    report = again.json()
    assert report["applied"] is False
    assert report["errors"] == []
    assert all(item["to_import"] == 0 for item in report["collections"].values())
    assert counts(tmp_path / "jobradar.sqlite3") == before


def test_unknown_status_blocks_the_whole_import(client, tmp_path):
    export = load_export()
    export["collections"]["jobs"][0]["data"]["status"] = "vielleicht"

    dry = client.post("/api/import", json=export).json()
    assert any("vielleicht" in error for error in dry["errors"])
    response = client.post("/api/import?dry_run=false", json=export)

    assert response.status_code == 422
    assert response.json()["applied"] is False
    assert counts(tmp_path / "jobradar.sqlite3")["jobs"] == 0
    assert counts(tmp_path / "jobradar.sqlite3")["import_archive"] == 0


def test_document_count_mismatch_is_an_error(client):
    export = load_export()
    del export["collections"]["jobs"][2]

    report = client.post("/api/import", json=export).json()

    assert any("8 Dokumente" in error for error in report["errors"])
    assert any("Sammlung 'jobs'" in error for error in report["errors"])


def test_foreign_export_type_is_rejected(client):
    report = client.post("/api/import", json={"_export": {"typ": "etwas-anderes"}, "collections": {}}).json()
    assert any("Exporttyp" in error for error in report["errors"])


def test_existing_profile_is_only_replaced_on_request(client, tmp_path):
    own = {"location": "Eigene Stadt", "radius_km": 10, "roles": ["Eigene Rolle"]}
    assert client.put("/api/profile", json={"data": own}).status_code == 200
    export = load_export()

    first = client.post("/api/import?dry_run=false", json=export).json()
    assert first["profile"]["action"] == "nicht_ersetzt"
    assert client.get("/api/profile").json()["data"] == own

    second = client.post("/api/import?dry_run=false&overwrite_profile=true", json=export)
    assert second.status_code == 200
    assert second.json()["profile"]["action"] == "ersetzen"
    assert second.json()["profile"]["previous"] == own
    assert client.get("/api/profile").json()["data"]["location"] == "Musterstadt"
    assert counts(tmp_path / "jobradar.sqlite3")["jobs"] == 3


def test_imported_job_detail_shows_previous_assessment(client):
    client.post("/api/import?dry_run=false", json=load_export())

    detail = client.get("/api/jobs/beispiel-a-systemadministrator").json()

    assert detail["score_breakdown"][0] == {
        "label": "Übernommene Bewertung",
        "points": 88,
        "detail": "Punkte aus dem bisherigen Jobradar, unverändert übernommen",
    }
    assert detail["calculated_base_score"] is None
    assert detail["imported"]["why"] == "Linux, VMware und Ansible im Betrieb – passt sehr gut."
    assert detail["imported"]["concerns"] == "Bereitschaftsdienst; Homeoffice nur nach Absprache."
    assert detail["imported"]["salary"] == "TV-L E 12"
    assert detail["imported"]["status"] == "neu"


def test_learning_keeps_the_imported_score_as_base(client, tmp_path):
    client.post("/api/import?dry_run=false", json=load_export())

    client.patch("/api/jobs/beispiel-a-systemadministrator", json={"status": "gemerkt"})

    with connect(tmp_path / "jobradar.sqlite3") as db:
        row = db.execute(
            "SELECT score, base_score, imported_score FROM jobs WHERE id = 'beispiel-c-helpdesk'"
        ).fetchone()
    assert (row["base_score"], row["imported_score"]) == (57, 57)
    detail = client.get("/api/jobs/beispiel-c-helpdesk").json()
    assert sum(item["points"] for item in detail["score_breakdown"]) == detail["score"]


def test_import_log_lists_the_import(client):
    client.post("/api/import?dry_run=false", json=load_export())

    log = client.get("/api/imports").json()

    assert log["archived_documents"] == 8
    assert len(log["items"]) == 1
    assert log["items"][0]["export_created"] == "2026-01-03T08:00:00Z"
    assert log["items"][0]["collections"]["laeufe"]["to_import"] == 2


def test_import_does_not_change_the_input(client):
    export = load_export()
    snapshot = copy.deepcopy(export)
    client.post("/api/import?dry_run=false", json=export)
    assert export == snapshot


def test_paused_rule_is_not_applied():
    vacancy = {"title": "Junior Administrator", "company": "Beispiel", "description": ""}
    active = [{"id": "r", "data": {"category": "negative", "terms": ["Junior"], "weight": 25, "enabled": True}}]
    paused = [{"id": "r", "data": {"category": "negative", "terms": ["Junior"], "weight": 25, "enabled": False}}]

    assert evaluate_vacancy(vacancy, {}, paused)[0] - evaluate_vacancy(vacancy, {}, active)[0] == 25


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js nicht installiert")
def test_dashboard_script_is_valid_javascript(client, tmp_path):
    html = client.get("/").text
    script = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    path = tmp_path / "dashboard.js"
    path.write_text(script, encoding="utf-8")

    result = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
    assert "import-check" in html and "imported-info" in html
