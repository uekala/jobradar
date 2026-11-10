"""Übernahme eines Jobradar-Datenexports (Format ``jobradar-datenexport``, Version 1).

Der Import arbeitet in zwei Schritten: Ein Probelauf prüft den Export und
beschreibt, was passieren würde, ohne etwas zu schreiben. Erst ein Lauf mit
``dry_run=False`` schreibt – und auch nur, wenn der Probelauf fehlerfrei ist.

Jedes Dokument des Exports wird unverändert in ``import_archive`` abgelegt.
Stellen, Suchläufe, Suchprofil und Abwertungswörter werden zusätzlich in die
Tabellen der App übernommen. Ein erneuter Import desselben Exports ändert nichts.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

EXPORT_TYPE = "jobradar-datenexport"
EXPORT_FORMAT_VERSION = 1
SOURCE_TYPE = "jobradar-datenexport-v1"

STATUS_MAP = {
    "neu": "neu",
    "merken": "gemerkt",
    "beworben": "beworben",
    "absage": "absage",
    "verworfen": "verworfen",
}

KNOWN_COLLECTIONS = ("jobs", "laeufe", "profil", "regeln", "pflege")

# Felder aus regeln/aktuell, für die es in der App noch keine Entsprechung gibt.
RULE_FIELDS_ARCHIVE_ONLY = ("suchbegriffe_zusatz", "karriereseiten", "quellen_hinweise")

PROFILE_FIELD_MAP = {
    "ort": "location",
    "umkreis_km": "radius_km",
    "homeoffice": "nationwide_remote",
    "rollen": "roles",
    "faehigkeiten": "skills",
    "gehalt_wunsch": "salary_min",
    "min_entgeltgruppe": "public_service_minimum",
    "ausschliessen_arbeitgeber": "exclusions",
    "wuensche": "preferences_raw",
}


def split_list(value: Any) -> list[str]:
    """Split a comma or newline separated list, keeping commas inside parentheses."""
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if not isinstance(value, str):
        return []
    parts: list[str] = []
    depth = 0
    current = ""
    for char in value:
        if char in "([":
            depth += 1
        elif char in ")]" and depth:
            depth -= 1
        if char in ",\n" and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += char
    parts.append(current)
    return [part.strip() for part in parts if part.strip()]


def content_sha256(export: dict[str, Any]) -> str:
    canonical = json.dumps(export, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_iso(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _found_before_filter(je_quelle: Any, fallback: int) -> int:
    """Sum the 'found' part of 'Quelle 41/6, Quelle 12/2'; fall back to the stored count."""
    if not isinstance(je_quelle, str) or not je_quelle.strip():
        return fallback
    pairs = re.findall(r"(\d+)\s*/\s*\d+", je_quelle)
    return sum(int(found) for found in pairs) if pairs else fallback


class _Plan:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.archive: list[dict[str, Any]] = []
        self.jobs: list[dict[str, Any]] = []
        self.runs: list[dict[str, Any]] = []
        self.profile: dict[str, Any] | None = None
        self.rules: list[dict[str, Any]] = []
        self.archived_only: list[str] = []
        self.collections: dict[str, dict[str, int]] = {}


def _entries(export: dict[str, Any], plan: _Plan) -> dict[str, list[dict[str, Any]]]:
    meta = export.get("_export")
    collections = export.get("collections")
    if not isinstance(meta, dict) or not isinstance(collections, dict):
        plan.errors.append("Kein gültiger Export: Abschnitte '_export' und 'collections' fehlen.")
        return {}
    if meta.get("typ") != EXPORT_TYPE:
        plan.errors.append(f"Unbekannter Exporttyp '{meta.get('typ')}', erwartet '{EXPORT_TYPE}'.")
    if meta.get("formatversion") != EXPORT_FORMAT_VERSION:
        plan.errors.append(f"Nicht unterstützte Formatversion '{meta.get('formatversion')}'.")

    result: dict[str, list[dict[str, Any]]] = {}
    seen_paths: set[str] = set()
    for name, entries in collections.items():
        if not isinstance(entries, list):
            plan.errors.append(f"Sammlung '{name}' ist keine Liste von Dokumenten.")
            continue
        valid: list[dict[str, Any]] = []
        for index, entry in enumerate(entries):
            doc_id = entry.get("id") if isinstance(entry, dict) else None
            if not isinstance(doc_id, str) or not doc_id.strip() or not isinstance(entry.get("data"), dict):
                plan.errors.append(f"{name}[{index}]: Dokument ohne gültige ID oder ohne Daten.")
                continue
            path = f"{name}/{doc_id}"
            if path in seen_paths:
                plan.errors.append(f"{path}: Dokument-ID kommt doppelt vor.")
                continue
            seen_paths.add(path)
            valid.append(entry)
        result[name] = valid
        if name not in KNOWN_COLLECTIONS:
            plan.warnings.append(f"Unbekannte Sammlung '{name}': wird nur archiviert.")

    expected_total = meta.get("dokumente_exportiert")
    if isinstance(expected_total, int) and expected_total != len(seen_paths):
        plan.errors.append(
            f"Der Export nennt {expected_total} Dokumente, enthalten sind {len(seen_paths)}."
        )
    expected_counts = meta.get("anzahl_je_collection")
    if isinstance(expected_counts, dict):
        for name, expected in expected_counts.items():
            actual = len(result.get(name, []))
            if expected != actual:
                plan.errors.append(f"Sammlung '{name}': laut Export {expected} Dokumente, enthalten {actual}.")
    return result


def _plan_jobs(entries: list[dict[str, Any]], db: Any, archived: set[str], plan: _Plan, now: str) -> None:
    urls_in_export: dict[str, str] = {}
    for entry in entries:
        doc_id = entry["id"]
        path = f"jobs/{doc_id}"
        data = entry["data"]
        notes: list[str] = []
        item = {"id": doc_id, "title": data.get("titel"), "status_old": data.get("status"),
                "status_new": None, "score": data.get("punkte"), "action": "uebernehmen", "notes": notes}
        plan.jobs.append(item)
        if path in archived:
            item["action"] = "bereits_importiert"
            continue

        title = data.get("titel")
        if not isinstance(title, str) or not title.strip():
            plan.errors.append(f"{path}: Titel fehlt.")
        status_old = data.get("status")
        status_new = STATUS_MAP.get(status_old) if isinstance(status_old, str) else None
        if status_new is None:
            plan.errors.append(f"{path}: Unbekannter Status '{status_old}' – bitte zuordnen, bevor importiert wird.")
        item["status_new"] = status_new
        score = data.get("punkte")
        if score is not None and (isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100):
            plan.errors.append(f"{path}: Punkte '{score}' sind keine ganze Zahl von 0 bis 100.")

        url = data.get("url")
        if url:
            if not isinstance(url, str) or not url.startswith(("https://", "http://")):
                notes.append("Link ist keine http(s)-Adresse")
            elif url.endswith(".") or url.endswith("-inline."):
                notes.append("Link wirkt abgeschnitten")
            if isinstance(url, str):
                if url in urls_in_export:
                    notes.append(f"gleicher Link wie {urls_in_export[url]}")
                urls_in_export.setdefault(url, doc_id)
        found_at = data.get("gefunden")
        if not _is_iso(found_at):
            notes.append("Fundzeitpunkt fehlt oder ist kein ISO-Datum; Importzeitpunkt verwendet")

        if db.execute("SELECT 1 FROM jobs WHERE id = ?", (doc_id,)).fetchone():
            plan.errors.append(f"{path}: In der App gibt es schon eine Stelle mit dieser ID.")
        elif isinstance(url, str) and url:
            duplicate = db.execute("SELECT id FROM jobs WHERE url = ?", (url,)).fetchone()
            if duplicate:
                notes.append(f"mögliche Dublette der vorhandenen Stelle {duplicate['id']}")
        if notes:
            plan.warnings.extend(f"{path}: {note}." for note in notes)

        updated = data.get("geaendert") if _is_iso(data.get("geaendert")) else entry.get("updatedAt")
        plan.archive.append(entry | {"_path": path, "_collection": "jobs"})
        if status_new is None:
            continue
        plan.jobs[-1]["row"] = {
            "id": doc_id,
            "title": title,
            "company": data.get("arbeitgeber") or None,
            "location": data.get("ort") or None,
            "url": url or None,
            "source": data.get("quelle") or None,
            "remote_type": "homeoffice" if data.get("homeoffice") is True else None,
            "score": score,
            "base_score": score,
            "imported_score": score,
            "status": status_new,
            "notes": data.get("notiz") or "",
            "published_at": data.get("veroeffentlicht") or None,
            "first_seen_at": found_at if _is_iso(found_at) else now,
            "last_seen_at": found_at if _is_iso(found_at) else now,
            "created_at": found_at if _is_iso(found_at) else now,
            "updated_at": updated if _is_iso(updated) else now,
            "imported_at": now,
            "import_source": SOURCE_TYPE,
            "import_json": json.dumps(entry, ensure_ascii=False),
        }


def _plan_runs(entries: list[dict[str, Any]], archived: set[str], plan: _Plan, now: str) -> None:
    for entry in sorted(entries, key=lambda item: str(item["data"].get("datum") or "")):
        path = f"laeufe/{entry['id']}"
        data = entry["data"]
        item = {"id": entry["id"], "action": "uebernehmen"}
        plan.runs.append(item)
        if path in archived:
            item["action"] = "bereits_importiert"
            continue
        plan.archive.append(entry | {"_path": path, "_collection": "laeufe"})
        new = data.get("neu")
        if not _is_iso(data.get("datum")):
            plan.errors.append(f"{path}: Datum fehlt oder ist kein ISO-Zeitpunkt.")
            continue
        if isinstance(new, bool) or not isinstance(new, int) or new < 0:
            plan.errors.append(f"{path}: Anzahl neuer Stellen '{new}' ist ungültig.")
            continue
        item["row"] = {
            "started_at": data["datum"],
            "finished_at": data["datum"],
            "status": "success",
            "jobs_found": _found_before_filter(data.get("je_quelle"), new),
            "jobs_new": new,
            "sources": data.get("quellen") or None,
            "note": data.get("hinweis") or None,
            "imported_at": now,
            "import_json": json.dumps(entry, ensure_ascii=False),
        }


def _plan_profile(entries: list[dict[str, Any]], db: Any, archived: set[str], plan: _Plan,
                  overwrite_profile: bool) -> None:
    for entry in entries:
        path = f"profil/{entry['id']}"
        already_archived = path in archived
        if entry["id"] != "aktuell":
            if not already_archived:
                plan.archive.append(entry | {"_path": path, "_collection": "profil"})
                plan.archived_only.append(path)
            continue
        if already_archived and not overwrite_profile:
            plan.profile = {"action": "bereits_importiert"}
            continue
        if not already_archived:
            plan.archive.append(entry | {"_path": path, "_collection": "profil"})
        data = entry["data"]
        mapped: dict[str, Any] = {}
        for source_key, target_key in PROFILE_FIELD_MAP.items():
            if source_key not in data:
                continue
            value = data[source_key]
            if target_key in ("roles", "skills", "exclusions"):
                value = split_list(value)
            elif target_key == "nationwide_remote":
                value = value is True
            elif target_key == "salary_min":
                value = value if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 else None
            elif target_key == "public_service_minimum":
                value = f"EG {value}" if isinstance(value, int) and not isinstance(value, bool) and value > 0 else ""
            mapped[target_key] = value
        unmapped = sorted(set(data) - set(PROFILE_FIELD_MAP) - {"geaendert"})
        if unmapped:
            plan.archived_only.extend(f"{path}.{key}" for key in unmapped)

        existing = db.execute("SELECT data_json FROM profile WHERE id = 1").fetchone()
        existing_data = json.loads(existing["data_json"]) if existing else {}
        action = "uebernehmen"
        if existing_data:
            if overwrite_profile:
                action = "ersetzen"
            else:
                action = "nicht_ersetzt"
                plan.warnings.append(
                    "Die App hat schon ein Suchprofil; es bleibt unverändert. "
                    "Zum Ersetzen den Import mit 'Vorhandenes Suchprofil ersetzen' wiederholen."
                )
        plan.profile = {"action": action, "data": mapped,
                        "previous": existing_data if action == "ersetzen" else None}


def _plan_rules(entries: list[dict[str, Any]], db: Any, archived: set[str], plan: _Plan) -> None:
    for entry in entries:
        path = f"regeln/{entry['id']}"
        if path in archived:
            plan.rules.append({"id": None, "action": "bereits_importiert", "source": path})
            continue
        plan.archive.append(entry | {"_path": path, "_collection": "regeln"})
        if entry["id"] != "aktuell":
            plan.archived_only.append(path)
            continue
        data = entry["data"]
        candidates = (
            ("abwerten", "uebernommen-abwerten", "Abwerten (übernommen)", "negative", 25,
             "Aus dem bisherigen Jobradar übernommen; dort −25 Punkte je Wort im Titel."),
            ("bevorzugen", "uebernommen-bevorzugen", "Bevorzugen (übernommen)", "positive", 5,
             "Aus dem bisherigen Jobradar übernommen; dort +5 Punkte je Wort, höchstens +10."),
        )
        for field, rule_id, name, category, weight, description in candidates:
            terms = split_list(data.get(field))
            if not terms:
                continue
            if db.execute("SELECT 1 FROM search_rules WHERE id = ?", (rule_id,)).fetchone():
                plan.errors.append(f"{path}: Bewertungsregel '{rule_id}' gibt es in der App schon.")
                continue
            plan.rules.append({
                "id": rule_id,
                "action": "uebernehmen",
                "source": f"{path}.{field}",
                "data": {"name": name, "category": category, "terms": terms, "weight": weight,
                         "description": description, "enabled": True},
            })
        for field in RULE_FIELDS_ARCHIVE_ONLY:
            value = data.get(field)
            if isinstance(value, str) and value.strip():
                plan.archived_only.append(f"{path}.{field}")
                if field != "quellen_hinweise":
                    plan.warnings.append(
                        f"{path}.{field} ist gefüllt, hat in der App aber noch keine Funktion; nur im Archiv."
                    )


def _archive_rest(collections: dict[str, list[dict[str, Any]]], archived: set[str], plan: _Plan) -> None:
    for name, entries in collections.items():
        if name in ("jobs", "laeufe", "profil", "regeln"):
            continue
        for entry in entries:
            path = f"{name}/{entry['id']}"
            if path in archived:
                continue
            plan.archive.append(entry | {"_path": path, "_collection": name})
            plan.archived_only.append(path)


def run_import(db: Any, export: dict[str, Any], *, dry_run: bool, overwrite_profile: bool, now: str) -> dict[str, Any]:
    """Check (and unless ``dry_run``, apply) a Jobradar export. Returns the import report."""
    plan = _Plan()
    if not isinstance(export, dict):
        export = {}
    collections = _entries(export, plan)
    archived = {row["path"] for row in db.execute("SELECT path FROM import_archive")}

    _plan_jobs(collections.get("jobs", []), db, archived, plan, now)
    _plan_runs(collections.get("laeufe", []), archived, plan, now)
    _plan_profile(collections.get("profil", []), db, archived, plan, overwrite_profile)
    _plan_rules(collections.get("regeln", []), db, archived, plan)
    _archive_rest(collections, archived, plan)

    for name, entries in collections.items():
        already = sum(1 for entry in entries if f"{name}/{entry['id']}" in archived)
        plan.collections[name] = {"found": len(entries), "already_imported": already,
                                  "to_import": len(entries) - already}

    meta = export.get("_export") if isinstance(export.get("_export"), dict) else {}
    report: dict[str, Any] = {
        "dry_run": dry_run,
        "applied": False,
        "import_id": None,
        "export": {
            "type": meta.get("typ"),
            "created": meta.get("erstellt_utc"),
            "documents": sum(len(entries) for entries in collections.values()),
            "content_sha256": content_sha256(export),
        },
        "collections": plan.collections,
        "jobs": [{key: value for key, value in item.items() if key != "row"} for item in plan.jobs],
        "runs": [{key: value for key, value in item.items() if key != "row"} for item in plan.runs],
        "profile": {key: value for key, value in (plan.profile or {"action": "kein_profil"}).items()
                    if key != "previous"},
        "rules": [{key: value for key, value in rule.items() if key != "data"} for rule in plan.rules],
        "archived_only": plan.archived_only,
        "archive_documents": len(plan.archive),
        "errors": plan.errors,
        "warnings": plan.warnings,
    }
    profile_changes = bool(plan.profile and plan.profile.get("action") in ("uebernehmen", "ersetzen"))
    if dry_run or plan.errors or not (plan.archive or profile_changes):
        return report

    cursor = db.execute(
        "INSERT INTO imports (imported_at, source_type, export_created, content_sha256, report_json) "
        "VALUES (?, ?, ?, ?, '{}')",
        (now, SOURCE_TYPE, meta.get("erstellt_utc"), report["export"]["content_sha256"]),
    )
    import_id = cursor.lastrowid

    for entry in plan.archive:
        db.execute(
            "INSERT INTO import_archive "
            "(path, collection, doc_id, version, updated_at, data_json, import_id, imported_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (entry["_path"], entry["_collection"], entry["id"], entry.get("version"), entry.get("updatedAt"),
             json.dumps(entry["data"], ensure_ascii=False), import_id, now),
        )
    for item in plan.jobs:
        row = item.get("row")
        if row:
            columns = ", ".join(row)
            db.execute(f"INSERT INTO jobs ({columns}) VALUES ({', '.join('?' for _ in row)})", list(row.values()))
    for item in plan.runs:
        row = item.get("row")
        if row:
            columns = ", ".join(row)
            db.execute(f"INSERT INTO runs ({columns}) VALUES ({', '.join('?' for _ in row)})", list(row.values()))
    if plan.profile and plan.profile.get("action") in ("uebernehmen", "ersetzen"):
        db.execute(
            """INSERT INTO profile (id, data_json, updated_at) VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET data_json = excluded.data_json, updated_at = excluded.updated_at""",
            (json.dumps(plan.profile["data"], ensure_ascii=False), now),
        )
        if plan.profile.get("previous") is not None:
            report["profile"]["previous"] = plan.profile["previous"]
    for rule in plan.rules:
        if rule.get("action") == "uebernehmen":
            db.execute(
                "INSERT INTO search_rules (id, data_json, updated_at) VALUES (?, ?, ?)",
                (rule["id"], json.dumps(rule["data"], ensure_ascii=False), now),
            )

    report["applied"] = True
    report["import_id"] = import_id
    db.execute("UPDATE imports SET report_json = ? WHERE id = ?", (json.dumps(report, ensure_ascii=False), import_id))
    return report


def imported_details(import_json: str | None) -> dict[str, Any] | None:
    """Return the original assessment of an imported job for the detail view."""
    if not import_json:
        return None
    try:
        entry = json.loads(import_json)
    except ValueError:
        return None
    data = entry.get("data", {}) if isinstance(entry, dict) else {}
    return {
        "original_id": entry.get("id"),
        "original_version": entry.get("version"),
        "original_updated_at": entry.get("updatedAt"),
        "why": data.get("warum") or "",
        "concerns": data.get("bedenken") or "",
        "salary": data.get("gehalt") or "",
        "homeoffice": data.get("homeoffice"),
        "published": data.get("veroeffentlicht") or "",
        "source": data.get("quelle") or "",
        "points": data.get("punkte"),
        "status": data.get("status"),
    }
