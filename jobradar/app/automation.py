"""Täglicher Suchplan und Benachrichtigungen über Home Assistant.

Die App läuft als Home-Assistant-App (Add-on). Ihre Optionen stehen in
``/data/options.json``; ohne diese Datei (lokale Entwicklung, Tests) wird
nichts geplant und nichts gesendet.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .database import connect

_LOGGER = logging.getLogger("jobradar")

DEFAULT_OPTIONS_PATH = "/data/options.json"
SUPERVISOR_URL = "http://supervisor"
LAST_SCHEDULED_KEY = "last_scheduled_search"
CHECK_SECONDS = 60.0
MAX_LISTED = 3

# Im eigenständigen Betrieb (Docker ohne Home Assistant OS) lassen sich die Optionen auch so setzen.
ENV_OPTIONS = {
    "search_time": "JOBRADAR_SEARCH_TIME",
    "notify_service": "JOBRADAR_NOTIFY_SERVICE",
    "notify_min_score": "JOBRADAR_NOTIFY_MIN_SCORE",
}

_TIME = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_SERVICE = re.compile(r"^[a-z0-9_]+$")


def load_options(path: str | None = None) -> dict[str, Any]:
    """Liest die App-Optionen. Fehlt die Datei, sind Zeitplan und Push aus.

    Gesetzte Umgebungsvariablen (``JOBRADAR_SEARCH_TIME``, ``JOBRADAR_NOTIFY_SERVICE``,
    ``JOBRADAR_NOTIFY_MIN_SCORE``) haben Vorrang vor der Datei.
    """
    file = Path(path or os.environ.get("JOBRADAR_OPTIONS_PATH", DEFAULT_OPTIONS_PATH))
    options: dict[str, Any] = {"search_time": "", "notify_service": "", "notify_min_score": 70}
    raw: Any = {}
    try:
        raw = json.loads(file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        pass
    except (OSError, ValueError) as err:
        _LOGGER.warning("Optionen nicht lesbar (%s); es gelten nur die Umgebungsvariablen", err)
    if not isinstance(raw, dict):
        raw = {}
    for key, variable in ENV_OPTIONS.items():
        value = os.environ.get(variable, "").strip()
        if value:
            raw[key] = value

    search_time = str(raw.get("search_time") or "").strip()
    if search_time and not _TIME.fullmatch(search_time):
        _LOGGER.warning("search_time=%r ist keine Uhrzeit (HH:MM); Zeitplan bleibt aus", search_time)
        search_time = ""
    options["search_time"] = search_time

    service = str(raw.get("notify_service") or "").strip().lower()
    service = service.removeprefix("notify.")
    if service and not _SERVICE.fullmatch(service):
        _LOGGER.warning("notify_service=%r ist kein gültiger Dienstname; Push bleibt aus", service)
        service = ""
    options["notify_service"] = service

    try:
        options["notify_min_score"] = max(0, min(100, int(raw.get("notify_min_score", 70))))
    except (TypeError, ValueError):
        options["notify_min_score"] = 70
    return options


def local_now() -> datetime:
    """Aktuelle Zeit in der Zeitzone, die Home Assistant der App übergibt (``TZ``)."""
    name = os.environ.get("TZ", "").strip()
    if name:
        try:
            return datetime.now(ZoneInfo(name))
        except (ZoneInfoNotFoundError, ValueError):
            _LOGGER.warning("Zeitzone %r unbekannt; der Zeitplan rechnet in UTC", name)
    return datetime.now(UTC)


def search_due(now: datetime, search_time: str, last_date: str | None) -> bool:
    """Einmal pro Tag ab ``search_time`` wahr.

    Ein Lauf, der verpasst wurde, weil die App gestoppt war, wird nach dem
    Start nachgeholt, solange noch derselbe Tag ist.
    """
    match = _TIME.fullmatch(search_time or "")
    if not match:
        return False
    if last_date == now.date().isoformat():
        return False
    return (now.hour, now.minute) >= (int(match.group(1)), int(match.group(2)))


def last_scheduled_date() -> str | None:
    with connect() as db:
        row = db.execute(
            "SELECT value FROM schema_meta WHERE key = ?", (LAST_SCHEDULED_KEY,)
        ).fetchone()
    return row["value"] if row else None


def mark_scheduled(day: str) -> None:
    with connect() as db:
        db.execute(
            "INSERT INTO schema_meta(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (LAST_SCHEDULED_KEY, day),
        )


def build_notification(result: dict[str, Any], min_score: int) -> tuple[str, str] | None:
    """Titel und Text zu einem beendeten Lauf, oder None, wenn es nichts zu melden gibt."""
    run = result.get("run") or {}
    if run.get("status") == "failed":
        detail = "; ".join(result.get("errors") or []) or "Keine Quelle lieferte Stellen."
        return "Jobradar: Suchlauf fehlgeschlagen", detail[:400]
    jobs = [job for job in result.get("new_jobs") or [] if (job.get("score") or 0) >= min_score]
    if not jobs:
        return None
    title = "1 neue Stelle im Jobradar" if len(jobs) == 1 else f"{len(jobs)} neue Stellen im Jobradar"
    lines = []
    for job in jobs[:MAX_LISTED]:
        place = ", ".join(part for part in (job.get("company"), job.get("location")) if part)
        lines.append(f"{job.get('title')} – {place} ({job.get('score')})" if place
                     else f"{job.get('title')} ({job.get('score')})")
    if len(jobs) > MAX_LISTED:
        lines.append(f"… und {len(jobs) - MAX_LISTED} weitere")
    return title, "\n".join(lines)


def _request(url: str, token: str, method: str, payload: dict[str, Any] | None = None) -> Any:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=15) as response:
            body = response.read().decode("utf-8")
    except (HTTPError, URLError, TimeoutError) as err:
        raise RuntimeError(f"Home Assistant antwortet nicht wie erwartet: {err}") from err
    try:
        return json.loads(body) if body else None
    except ValueError:
        return None


def _supervisor(method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    """Anfrage an den Supervisor; nur als Home-Assistant-App möglich."""
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        raise RuntimeError("Kein Zugriff auf Home Assistant (SUPERVISOR_TOKEN fehlt)")
    return _request(f"{SUPERVISOR_URL}{path}", token, method, payload)


def home_assistant_address() -> tuple[str, str] | None:
    """Adresse und Token für den eigenständigen Betrieb (``HA_URL``, ``HA_TOKEN``), sonst ``None``.

    Als Home-Assistant-App zählt immer der Supervisor.
    """
    if os.environ.get("SUPERVISOR_TOKEN"):
        return None
    url = os.environ.get("HA_URL", "").strip().rstrip("/")
    token = os.environ.get("HA_TOKEN", "").strip()
    if token and url.startswith(("http://", "https://")):
        return url, token
    return None


def _home_assistant(method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    """Ruft die API von Home Assistant auf, z. B. ``/api/services/notify/…``."""
    direct = home_assistant_address()
    if direct is None:
        return _supervisor(method, f"/core{path}", payload)
    url, token = direct
    return _request(f"{url}{path}", token, method, payload)


def panel_url() -> str | None:
    """Adresse des Jobradar-Panels in Home Assistant, für das Antippen der Push-Nachricht."""
    try:
        info = _supervisor("GET", "/addons/self/info")
    except RuntimeError:
        return None
    data = info.get("data") if isinstance(info, dict) else None
    slug = data.get("slug") if isinstance(data, dict) else None
    return f"/hassio/ingress/{slug}" if isinstance(slug, str) and slug else None


def send_notification(service: str, title: str, message: str) -> None:
    """Sendet über einen Notify-Dienst von Home Assistant, z. B. ``mobile_app_pixel``."""
    if service == "persistent_notification":
        _home_assistant(
            "POST",
            "/api/services/persistent_notification/create",
            {"title": title, "message": message, "notification_id": "jobradar"},
        )
        return
    payload: dict[str, Any] = {"title": title, "message": message}
    url = panel_url()
    if url:
        # "url" öffnet das Panel unter iOS, "clickAction" unter Android.
        payload["data"] = {"url": url, "clickAction": url, "tag": "jobradar"}
    _home_assistant("POST", f"/api/services/notify/{service}", payload)


def notify_result(result: dict[str, Any], options: dict[str, Any]) -> bool:
    """Meldet das Ergebnis eines Laufs per Push, wenn ein Dienst eingerichtet ist. Wirft nie."""
    service = options.get("notify_service")
    if not service:
        return False
    notification = build_notification(result, int(options.get("notify_min_score", 70)))
    if notification is None:
        return False
    try:
        send_notification(service, *notification)
    except Exception as err:
        _LOGGER.error("Benachrichtigung fehlgeschlagen: %s", err)
        return False
    return True


def run_scheduled_search(
    run: Callable[[str], dict[str, Any]],
    options: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Startet die tägliche Suche, wenn sie fällig ist. Wirft nie."""
    now = now or local_now()
    try:
        if not search_due(now, options.get("search_time", ""), last_scheduled_date()):
            return None
        # Vor dem Lauf markiert: Ein Lauf, der scheitert oder abbricht, wird
        # nicht jede Minute wiederholt, der nächste Versuch ist morgen.
        mark_scheduled(now.date().isoformat())
        result = run("schedule")
    except Exception as err:
        _LOGGER.error("Täglicher Suchlauf fehlgeschlagen: %s", err)
        return None
    summary = result.get("run") or {}
    _LOGGER.info(
        "Täglicher Suchlauf: %s, %s Anzeigen, %s neu",
        summary.get("status"), summary.get("jobs_found"), summary.get("jobs_new"),
    )
    notify_result(result, options)
    return result


async def search_loop(
    stop: asyncio.Event,
    run: Callable[[str], dict[str, Any]],
    options: dict[str, Any],
    interval: float = CHECK_SECONDS,
) -> None:
    """Prüft jede Minute, ob die tägliche Suche fällig ist."""
    while True:
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
            return
        except TimeoutError:
            pass
        await asyncio.to_thread(run_scheduled_search, run, options)
