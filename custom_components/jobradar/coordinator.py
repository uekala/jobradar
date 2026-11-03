"""Regelmäßige Suche, Bewertung, Gedächtnis und Benachrichtigung."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import JobsucheClient, JobsucheError
from .const import (
    ACTION_HIDE,
    CONF_EXCLUDED_EMPLOYERS,
    CONF_EXCLUDED_WORDS,
    CONF_INTERVAL,
    CONF_LOCATION,
    CONF_MIN_SCORE,
    CONF_NO_TEMP_AGENCIES,
    CONF_NOTIFY,
    CONF_RADIUS,
    CONF_REMOTE,
    CONF_SEARCH_TERMS,
    CONF_SKILLS,
    CONF_UNWANTED,
    DEFAULT_EXCLUDED_WORDS,
    DEFAULT_INTERVAL,
    DEFAULT_MIN_SCORE,
    DEFAULT_RADIUS,
    DEFAULT_SEARCH_TERMS,
    DEFAULT_SKILLS,
    DEFAULT_UNWANTED,
    DOMAIN,
    EVENT_NEW_JOB,
    FIRST_RUN_DAYS,
    KEEP_DAYS,
    MAX_DETAILS_PER_RUN,
    MAX_PUSHES_PER_RUN,
    MIN_INTERVAL,
    NOTIFICATION_ID,
    RUN_DAYS,
    SEEN_DAYS,
    STORAGE_VERSION,
)
from .scoring import (
    Job,
    Profile,
    distance_km,
    normalize,
    parse_list,
    published_date,
    score_job,
)

_LOGGER = logging.getLogger(__name__)

type JobradarConfigEntry = ConfigEntry[JobradarCoordinator]


@dataclass
class Snapshot:
    """Was Sensoren und Diagnose anzeigen."""

    jobs: list[Job] = field(default_factory=list)
    unread: set[str] = field(default_factory=set)
    last_search: datetime | None = None
    queries: int = 0
    errors: int = 0
    requests: int = 0
    new_matches: int = 0
    found: int = 0
    best: list[dict[str, Any]] = field(default_factory=list)


def settings(entry: ConfigEntry) -> dict[str, Any]:
    """Optionen überschreiben die Erstdaten."""
    return {**entry.data, **entry.options}


def profile_from(conf: dict[str, Any]) -> Profile:
    return Profile(
        search_terms=tuple(parse_list(conf.get(CONF_SEARCH_TERMS, DEFAULT_SEARCH_TERMS))),
        skills=tuple(parse_list(conf.get(CONF_SKILLS, DEFAULT_SKILLS))),
        unwanted=tuple(parse_list(conf.get(CONF_UNWANTED, DEFAULT_UNWANTED))),
        excluded_words=tuple(parse_list(conf.get(CONF_EXCLUDED_WORDS, DEFAULT_EXCLUDED_WORDS))),
        excluded_employers=tuple(parse_list(conf.get(CONF_EXCLUDED_EMPLOYERS, ""))),
    )


def _sort_key(job: Job) -> tuple:
    return (-job.score, job.title.lower())


class JobradarCoordinator(DataUpdateCoordinator[Snapshot]):
    """Sucht neue Stellen und merkt sich, was schon gemeldet wurde."""

    config_entry: JobradarConfigEntry

    def __init__(self, hass: HomeAssistant, entry: JobradarConfigEntry) -> None:
        conf = settings(entry)
        interval = max(MIN_INTERVAL, int(conf.get(CONF_INTERVAL, DEFAULT_INTERVAL)))
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=interval),
        )
        self.client = JobsucheClient(async_get_clientsession(hass))
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self._seen: dict[str, str] = {}
        self._hidden: set[str] = set()
        self._unread: set[str] = set()
        self._jobs: dict[str, Job] = {}
        self._initialized = False
        self._last_search: datetime | None = None

    @property
    def conf(self) -> dict[str, Any]:
        return settings(self.config_entry)

    @property
    def profile(self) -> Profile:
        return profile_from(self.conf)

    @property
    def min_score(self) -> int:
        return int(self.conf.get(CONF_MIN_SCORE, DEFAULT_MIN_SCORE))

    async def async_load(self) -> None:
        stored = await self._store.async_load() or {}
        self._initialized = bool(stored.get("initialized"))
        self._seen = dict(stored.get("seen") or {})
        self._hidden = set(stored.get("hidden") or [])
        self._unread = set(stored.get("unread") or [])
        self._jobs = {}
        profile, min_score = self.profile, self.min_score
        for item in stored.get("jobs") or []:
            try:
                job = Job.from_dict(item)
            except (KeyError, TypeError, ValueError):
                continue
            # Das Profil kann sich seit dem letzten Lauf geändert haben
            score_job(job, profile)
            if not job.excluded and job.score >= min_score:
                self._jobs[job.refnr] = job

    async def _async_save(self) -> None:
        await self._store.async_save(
            {
                "initialized": self._initialized,
                "seen": self._seen,
                "hidden": sorted(self._hidden),
                "unread": sorted(self._unread & set(self._jobs)),
                "jobs": [job.as_dict() for job in self._jobs.values()],
            }
        )

    @staticmethod
    def _same_posting(job: Job) -> tuple[str, str] | None:
        """Gleiche Stelle, mehrfach ausgeschrieben (etwa für mehrere Standorte)."""
        if not job.employer:
            return None
        return normalize(job.title), normalize(job.employer)

    def _set_distance(self, job: Job) -> None:
        if job.remote or job.lat is None or job.lon is None:
            return
        home = (self.hass.config.latitude, self.hass.config.longitude)
        job.distance_km = round(distance_km(home[0], home[1], job.lat, job.lon), 1)

    def _snapshot(self, **extra: Any) -> Snapshot:
        jobs = sorted(
            self._jobs.values(), key=lambda j: (j.refnr not in self._unread, *_sort_key(j))
        )
        return Snapshot(
            jobs=jobs,
            unread=set(self._unread & set(self._jobs)),
            last_search=self._last_search,
            requests=self.client.requests,
            **extra,
        )

    def stored_snapshot(self) -> Snapshot:
        return self._snapshot()

    def _prune(self, now: datetime) -> None:
        keep_seen = (now - timedelta(days=SEEN_DAYS)).isoformat()
        self._seen = {r: t for r, t in self._seen.items() if t >= keep_seen}
        oldest = (now - timedelta(days=KEEP_DAYS)).date()
        for refnr, job in list(self._jobs.items()):
            published = published_date(job)
            if published and published < oldest:
                self._jobs.pop(refnr)
                self._unread.discard(refnr)

    async def _async_search(self, days: int) -> tuple[dict[str, Job], int, int]:
        conf = self.conf
        location = str(conf.get(CONF_LOCATION, "")).strip()
        radius = int(conf.get(CONF_RADIUS, DEFAULT_RADIUS))
        include_remote = bool(conf.get(CONF_REMOTE, True))
        no_temp = bool(conf.get(CONF_NO_TEMP_AGENCIES, True))
        found: dict[str, Job] = {}
        queries = errors = 0
        variants = [False, True] if include_remote else [False]
        if not location:
            variants = [True]
        for term in self.profile.search_terms:
            for remote in variants:
                queries += 1
                try:
                    jobs = await self.client.search(
                        term,
                        location=None if remote else location,
                        radius=None if remote else radius,
                        remote=remote,
                        days=days,
                        exclude_temp_agencies=no_temp,
                    )
                except JobsucheError as err:
                    errors += 1
                    _LOGGER.debug("Suche nach %s fehlgeschlagen: %s", term, err)
                    continue
                for job in jobs:
                    if job.refnr in found:
                        found[job.refnr].remote |= job.remote
                    else:
                        found[job.refnr] = job
        return found, queries, errors

    async def _async_update_data(self) -> Snapshot:
        first_run = not self._initialized
        self.client.new_run()
        days = FIRST_RUN_DAYS if first_run else RUN_DAYS
        found, queries, errors = await self._async_search(days)
        if queries and errors == queries:
            raise UpdateFailed("Die Jobbörse der Bundesagentur ist gerade nicht erreichbar")

        now = dt_util.utcnow()
        self._last_search = now
        profile = self.profile
        min_score = self.min_score
        # Die v6-Suche beachtet veroeffentlichtseit nicht zuverlässig
        cutoff = (dt_util.now() - timedelta(days=days)).date()
        hits = len(found)
        found = {
            refnr: job
            for refnr, job in found.items()
            if (published := published_date(job)) is None or published >= cutoff
        }

        new = [
            job
            for refnr, job in found.items()
            if refnr not in self._seen and refnr not in self._hidden
        ]
        for job in new:
            self._seen[job.refnr] = now.isoformat()
            self._set_distance(job)
            score_job(job, profile)

        promising = sorted(
            (j for j in new if not j.excluded and j.score >= min_score - 20), key=_sort_key
        )[:MAX_DETAILS_PER_RUN]
        if found and not new:
            _LOGGER.debug("%s Treffer, alle schon bekannt", len(found))
        for job in promising:
            if await self.client.load_details(job):
                if job.distance_km is None:
                    self._set_distance(job)
                score_job(job, profile)

        known = {key for job in self._jobs.values() if (key := self._same_posting(job))}
        matched: list[Job] = []
        hits_ok = (j for j in new if not j.excluded and j.score >= min_score)
        for job in sorted(hits_ok, key=_sort_key):
            key = self._same_posting(job)
            if key and key in known:
                continue
            if key:
                known.add(key)
            matched.append(job)
        for job in matched:
            self._jobs[job.refnr] = job
            self._unread.add(job.refnr)
        self._initialized = True
        self._prune(now)
        await self._async_save()

        if first_run:
            await self._async_announce_start(len(matched))
        elif matched:
            await self._async_announce(matched)
            for job in matched:
                self.hass.bus.async_fire(
                    EVENT_NEW_JOB,
                    {"entry_id": self.config_entry.entry_id, **job.as_dict(), "url": job.url},
                )

        best = [
            {"score": j.score, "title": j.title, "excluded": bool(j.excluded)}
            for j in sorted(new, key=_sort_key)[:8]
        ]
        return self._snapshot(
            queries=queries,
            errors=errors,
            new_matches=len(matched),
            found=hits,
            best=best,
        )

    # ---------- Benachrichtigung ----------

    async def _async_send(self, title: str, message: str, job: Job | None = None) -> None:
        service = str(self.conf.get(CONF_NOTIFY) or "").strip()
        domain, _, name = (service or "persistent_notification.create").partition(".")
        payload: dict[str, Any] = {"title": title, "message": message}
        if not service:
            payload["notification_id"] = f"{NOTIFICATION_ID}_{job.refnr if job else 'info'}"
        if job and name.startswith("mobile_app_"):
            payload["data"] = {
                "url": job.url,
                "clickAction": job.url,
                "tag": f"jobradar-{job.refnr}",
                "group": "jobradar",
                "actions": [
                    {"action": "URI", "title": "Öffnen", "uri": job.url},
                    {"action": f"{ACTION_HIDE}{job.refnr}", "title": "Nicht interessant"},
                ],
            }
        try:
            await self.hass.services.async_call(domain, name, payload, blocking=True)
        except Exception as err:  # Benachrichtigung darf die Suche nicht stoppen
            _LOGGER.warning("Benachrichtigung über %s fehlgeschlagen: %s", service, err)

    @staticmethod
    def describe(job: Job) -> str:
        where = "Homeoffice" if job.remote and not job.place else job.place or job.region
        parts = [p for p in (job.employer, where) if p]
        text = ", ".join(parts)
        if job.remote and job.place:
            text += " (Homeoffice möglich)"
        if job.distance_km is not None:
            text += f", {job.distance_km:.0f} km"
        text += f". Passt zu {job.score} %"
        if job.matches:
            text += f": {', '.join(job.matches[:4])}"
        return text + "."

    async def _async_announce(self, matched: list[Job]) -> None:
        for job in matched[:MAX_PUSHES_PER_RUN]:
            await self._async_send(job.title[:100], self.describe(job), job)
        rest = matched[MAX_PUSHES_PER_RUN:]
        if rest:
            await self._async_send(
                f"{len(rest)} weitere passende Stellen",
                "; ".join(f"{j.title} ({j.employer})" for j in rest[:8]),
            )

    async def _async_announce_start(self, count: int) -> None:
        if count:
            message = (
                f"{count} passende Stellen aus den letzten {FIRST_RUN_DAYS} Tagen "
                "stehen im Sensor. "
                "Neue melde ich ab jetzt sofort."
            )
        else:
            message = (
                f"In den letzten {FIRST_RUN_DAYS} Tagen keine passende Stelle. "
                "Neue melde ich sofort."
            )
        await self._async_send("Jobradar ist aktiv", message)

    # ---------- Aktionen ----------

    def has_job(self, refnr: str) -> bool:
        return refnr in self._jobs

    async def async_hide(self, refnr: str) -> None:
        self._hidden.add(refnr)
        self._jobs.pop(refnr, None)
        self._unread.discard(refnr)
        await self._async_save()
        self.async_set_updated_data(self._snapshot())

    async def async_mark_read(self, refnr: str | None = None) -> None:
        if refnr:
            self._unread.discard(refnr)
        else:
            self._unread.clear()
        await self._async_save()
        self.async_set_updated_data(self._snapshot())

    async def async_reset(self) -> None:
        """Vergisst alles – die nächste Suche verhält sich wie die erste."""
        self._initialized = False
        self._seen.clear()
        self._hidden.clear()
        self._unread.clear()
        self._jobs.clear()
        await self._async_save()
        await self.async_refresh()
