"""Bewertet Stellen nach Suchprofil – ohne Home-Assistant-Abhängigkeiten."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date

from .pay import grade_from_text, pay_label, pay_matches

# Allgemeine Rollenwörter: zusammen mit einer Fähigkeit im Titel zählt das als passende Rolle
ROLE_WORDS = (
    "administrator",
    "admin",
    "engineer",
    "ingenieur",
    "architekt",
    "architect",
    "spezialist",
    "specialist",
    "consultant",
    "berater",
    "techniker",
    "betreuer",
)

POINTS_ROLE = 50
POINTS_SKILL_TITLE = 10
POINTS_SKILL_TEXT = 5
MAX_SKILL_POINTS = 40
POINTS_UNWANTED = -25
POINTS_REMOTE = 5
POINTS_NEARBY = 5
NEARBY_KM = 25
POINTS_PAY_OK = 5
POINTS_PAY_LOW = -30
POINTS_MUTED = -20  # Arbeitgeber, dessen Stellen du mehrmals ausgeblendet hast

# "(m/w/d)", "(w/m/d)", "(m/f/d)", "(all genders)", "(gn)" …
_GENDER = re.compile(
    r"\(\s*(?:[mwfdxi]\s*[/|,]\s*){1,3}[mwfdxi]\s*\)"
    r"|\(\s*(?:all genders?|alle geschlechter|gn\*?|div)\s*\)",
    re.I,
)


def normalize(text: str) -> str:
    """Kleinbuchstaben ohne Leer- und Bindestriche.

    Damit sind "IT-Administrator" und "IT Administrator" gleich.
    """
    text = text.lower().replace("ß", "ss")
    return re.sub(r"[\s\-_/.,:;()|]+", "", text)


def clean_title(title: str, place: str = "") -> str:
    """Titel ohne Geschlechtsangabe und ohne angehängten Ort, für den Vergleich.

    "Systemadministrator (m/w/d) - Duisburg" und "Systemadministrator (w/m/d)"
    gelten so als dieselbe Stelle.
    """
    text = _GENDER.sub(" ", title)
    if place:
        for sep in (" - ", " – ", " | ", " in ", ", "):
            head, found, tail = text.rpartition(sep)
            if found and normalize(tail) == normalize(place):
                text = head
                break
    return normalize(text)


def parse_list(value: str | list[str] | None) -> list[str]:
    """Liste aus Text mit Kommas oder Zeilenumbrüchen."""
    if value is None:
        return []
    items = value if isinstance(value, list) else re.split(r"[,\n;]", value)
    seen: list[str] = []
    for item in items:
        item = item.strip()
        if item and item.lower() not in (s.lower() for s in seen):
            seen.append(item)
    return seen


@dataclass(frozen=True)
class Profile:
    """Wonach gesucht und wie bewertet wird."""

    search_terms: tuple[str, ...]
    skills: tuple[str, ...] = ()
    unwanted: tuple[str, ...] = ()
    excluded_words: tuple[str, ...] = ()
    excluded_employers: tuple[str, ...] = ()
    salary_expectation: int = 0  # Jahresbrutto in Euro, 0 = nicht vergleichen
    min_pay_grade: int = 0  # Entgeltgruppe TVöD/TV-L, 0 = nicht vergleichen
    muted_employers: tuple[str, ...] = ()  # aus "Nicht interessant" gelernt


@dataclass
class Job:
    """Eine Stelle, wie die Jobbörse sie liefert, ergänzt um Bewertung."""

    refnr: str
    title: str
    occupation: str = ""
    employer: str = ""
    place: str = ""
    postcode: str = ""
    region: str = ""
    lat: float | None = None
    lon: float | None = None
    published: str = ""
    start: str = ""
    external_url: str = ""
    remote: bool = False
    description: str = ""
    salary: str = ""
    pay_low: int | None = None
    pay_high: int | None = None
    pay_grade: int | None = None
    pay_scale: str = ""
    pay_ok: bool | None = None
    working_time: list[str] = field(default_factory=list)
    limited: str = ""
    source: str = ""  # leer = Jobbörse der Bundesagentur
    link: str = ""  # eigene Adresse der Anzeige bei anderen Quellen
    deadline: str = ""  # Bewerbungsfrist, ISO-Datum
    details_loaded: bool = False
    distance_km: float | None = None
    score: int = 0
    matches: list[str] = field(default_factory=list)
    excluded: str | None = None

    @property
    def pay(self) -> str:
        """Gehalt oder Entgeltgruppe, kurz."""
        return pay_label(self.pay_low, self.pay_high, self.pay_grade, self.pay_scale)

    @property
    def url(self) -> str:
        if self.link:
            return self.link
        return f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{self.refnr}"

    @property
    def from_jobboerse(self) -> bool:
        return not self.source

    def as_dict(self) -> dict:
        return {
            "refnr": self.refnr,
            "titel": self.title,
            "beruf": self.occupation,
            "arbeitgeber": self.employer,
            "ort": self.place,
            "plz": self.postcode,
            "region": self.region,
            "lat": self.lat,
            "lon": self.lon,
            "veroeffentlicht": self.published,
            "eintritt": self.start,
            "externe_url": self.external_url,
            "remote": self.remote,
            "beschreibung": self.description,
            "verguetung": self.salary,
            "gehalt_von": self.pay_low,
            "gehalt_bis": self.pay_high,
            "entgeltgruppe": self.pay_grade,
            "tarif": self.pay_scale,
            "gehalt_passt": self.pay_ok,
            "arbeitszeit": self.working_time,
            "befristung": self.limited,
            "quelle": self.source,
            "link": self.link,
            "bewerbungsfrist": self.deadline,
            "details": self.details_loaded,
            "entfernung_km": self.distance_km,
            "punkte": self.score,
            "treffer": self.matches,
            "ausgeschlossen": self.excluded,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Job:
        return cls(
            refnr=data["refnr"],
            title=data.get("titel", ""),
            occupation=data.get("beruf", ""),
            employer=data.get("arbeitgeber", ""),
            place=data.get("ort", ""),
            postcode=data.get("plz", ""),
            region=data.get("region", ""),
            lat=data.get("lat"),
            lon=data.get("lon"),
            published=data.get("veroeffentlicht", ""),
            start=data.get("eintritt", ""),
            external_url=data.get("externe_url", ""),
            remote=bool(data.get("remote")),
            description=data.get("beschreibung", ""),
            salary=data.get("verguetung", ""),
            pay_low=data.get("gehalt_von"),
            pay_high=data.get("gehalt_bis"),
            pay_grade=data.get("entgeltgruppe"),
            pay_scale=data.get("tarif", ""),
            pay_ok=data.get("gehalt_passt"),
            working_time=list(data.get("arbeitszeit") or []),
            limited=data.get("befristung", ""),
            source=data.get("quelle", ""),
            link=data.get("link", ""),
            deadline=data.get("bewerbungsfrist", ""),
            details_loaded=bool(data.get("details")),
            distance_km=data.get("entfernung_km"),
            score=int(data.get("punkte", 0)),
            matches=list(data.get("treffer") or []),
            excluded=data.get("ausgeschlossen"),
        )


def _contains(haystack: str, needle: str) -> bool:
    return bool(needle) and normalize(needle) in haystack


def score_job(job: Job, profile: Profile) -> Job:
    """Setzt Punkte (0–100), Treffer und gegebenenfalls einen Ausschlussgrund."""
    title = normalize(f"{job.title} {job.occupation}")
    text = normalize(job.description)
    employer = normalize(job.employer)

    job.excluded = None
    for name in profile.excluded_employers:
        if _contains(employer, name):
            job.excluded = f"Arbeitgeber ausgeschlossen ({name})"
    for word in profile.excluded_words:
        if _contains(title, word):
            job.excluded = f"Ausschlusswort im Titel ({word})"

    matches: list[str] = []
    points = 0
    role = any(_contains(title, term) for term in profile.search_terms)
    skills_in_title = [s for s in profile.skills if _contains(title, s)]
    if not role and skills_in_title and any(w in title for w in ROLE_WORDS):
        role = True
    if role:
        points += POINTS_ROLE

    skill_points = 0
    for skill in profile.skills:
        if skill in skills_in_title:
            skill_points += POINTS_SKILL_TITLE
            matches.append(skill)
        elif text and _contains(text, skill):
            skill_points += POINTS_SKILL_TEXT
            matches.append(skill)
    points += min(skill_points, MAX_SKILL_POINTS)

    for word in profile.unwanted:
        if _contains(title, word):
            points += POINTS_UNWANTED
    if employer and any(_contains(employer, name) for name in profile.muted_employers):
        points += POINTS_MUTED

    if job.remote:
        points += POINTS_REMOTE
    if job.distance_km is not None and job.distance_km <= NEARBY_KM:
        points += POINTS_NEARBY

    # Gehalt: Betrag aus der Jobbörse, sonst Entgeltgruppe aus Titel oder Text
    if not (job.pay_low or job.pay_high) and job.pay_grade is None:
        job.pay_grade, job.pay_scale = grade_from_text(f"{job.title}\n{job.description}")
    job.pay_ok = pay_matches(
        job.pay_low,
        job.pay_high,
        job.pay_grade,
        profile.salary_expectation,
        profile.min_pay_grade,
    )
    if job.pay_ok is True:
        points += POINTS_PAY_OK
    elif job.pay_ok is False:
        points += POINTS_PAY_LOW

    job.score = max(0, min(100, points))
    job.matches = matches
    return job


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Luftlinie nach Haversine."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def published_date(job: Job) -> date | None:
    try:
        return date.fromisoformat(job.published[:10])
    except ValueError:
        return None
