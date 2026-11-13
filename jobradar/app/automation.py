"""Daily search schedule and Home Assistant notifications.

The app runs as a Home Assistant app (add-on). Its options arrive in
``/data/options.json``; without that file (local development, tests) nothing
is scheduled and nothing is sent.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
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

_TIME = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_SERVICE = re.compile(r"^[a-z0-9_]+$")


def load_options(path: str | None = None) -> dict[str, Any]:
    """Read the app options. A missing file switches schedule and push off."""
    file = Path(path or os.environ.get("JOBRADAR_OPTIONS_PATH", DEFAULT_OPTIONS_PATH))
    options: dict[str, Any] = {"search_time": "", "notify_service": "", "notify_min_score": 70}
    try:
        raw = json.loads(file.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return options
    except (OSError, ValueError) as err:
        _LOGGER.warning("Optionen nicht lesbar (%s); Zeitplan und Push bleiben aus", err)
        return options
    if not isinstance(raw, dict):
        return options

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
    """Current time in the time zone Home Assistant passes to the app (``TZ``)."""
    name = os.environ.get("TZ", "").strip()
    if name:
        try:
            return datetime.now(ZoneInfo(name))
        except (ZoneInfoNotFoundError, ValueError):
            _LOGGER.warning("Zeitzone %r unbekannt; der Zeitplan rechnet in UTC", name)
    return datetime.now(timezone.utc)


def search_due(now: datetime, search_time: str, last_date: str | None) -> bool:
    """True once per day from ``search_time`` on.

    A run missed because the app was stopped is caught up after the start,
    as long as it is still the same day.
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
    """Title and text for a finished run, or None if there is nothing to report."""
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


def _supervisor(method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        raise RuntimeError("Kein Zugriff auf Home Assistant (SUPERVISOR_TOKEN fehlt)")
    request = Request(
        f"{SUPERVISOR_URL}{path}",
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


def panel_url() -> str | None:
    """Address of the Jobradar panel inside Home Assistant, for the tap on the push."""
    try:
        info = _supervisor("GET", "/addons/self/info")
    except RuntimeError:
        return None
    data = info.get("data") if isinstance(info, dict) else None
    slug = data.get("slug") if isinstance(data, dict) else None
    return f"/hassio/ingress/{slug}" if isinstance(slug, str) and slug else None


def send_notification(service: str, title: str, message: str) -> None:
    """Send through a Home Assistant notify service, e.g. ``mobile_app_pixel``."""
    if service == "persistent_notification":
        _supervisor(
            "POST",
            "/core/api/services/persistent_notification/create",
            {"title": title, "message": message, "notification_id": "jobradar"},
        )
        return
    payload: dict[str, Any] = {"title": title, "message": message}
    url = panel_url()
    if url:
        # "url" opens the panel on iOS, "clickAction" on Android.
        payload["data"] = {"url": url, "clickAction": url, "tag": "jobradar"}
    _supervisor("POST", f"/core/api/services/notify/{service}", payload)


def notify_result(result: dict[str, Any], options: dict[str, Any]) -> bool:
    """Push the outcome of a run if a service is configured. Never raises."""
    service = options.get("notify_service")
    if not service:
        return False
    notification = build_notification(result, int(options.get("notify_min_score", 70)))
    if notification is None:
        return False
    try:
        send_notification(service, *notification)
    except Exception as err:  # noqa: BLE001 - a failed push must not fail the run
        _LOGGER.error("Benachrichtigung fehlgeschlagen: %s", err)
        return False
    return True


def run_scheduled_search(
    run: Callable[[str], dict[str, Any]],
    options: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Run the daily search if it is due. Never raises."""
    now = now or local_now()
    try:
        if not search_due(now, options.get("search_time", ""), last_scheduled_date()):
            return None
        # Marked before the run: a run that fails or is interrupted is not
        # repeated every minute, the next attempt is tomorrow.
        mark_scheduled(now.date().isoformat())
        result = run("schedule")
    except Exception as err:  # noqa: BLE001 - the service keeps running
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
    """Check every minute whether the daily search is due."""
    while True:
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
            return
        except TimeoutError:
            pass
        await asyncio.to_thread(run_scheduled_search, run, options)
