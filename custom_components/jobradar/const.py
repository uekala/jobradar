"""Konstanten für Jobradar."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "jobradar"

CONF_LOCATION = "location"
CONF_RADIUS = "radius"
CONF_REMOTE = "include_remote"
CONF_SEARCH_TERMS = "search_terms"
CONF_SKILLS = "skills"
CONF_UNWANTED = "unwanted"
CONF_EXCLUDED_WORDS = "excluded_words"
CONF_EXCLUDED_EMPLOYERS = "excluded_employers"
CONF_MIN_SCORE = "min_score"
CONF_NOTIFY = "notify_service"
CONF_INTERVAL = "interval_minutes"
CONF_NO_TEMP_AGENCIES = "exclude_temp_agencies"
CONF_SALARY = "salary_expectation"
CONF_MIN_GRADE = "min_pay_grade"

DEFAULT_RADIUS = 50
DEFAULT_MIN_SCORE = 50
DEFAULT_INTERVAL = 30
MIN_INTERVAL = 15

DEFAULT_SEARCH_TERMS = (
    "Systemadministrator, Systemingenieur, IT-Administrator, Linux-Administrator, "
    "Windows-Administrator, VMware, Virtualisierung, Cloud Engineer, Platform Engineer, "
    "IT-Infrastruktur"
)
DEFAULT_SKILLS = (
    "VMware, vSphere, ESXi, Proxmox, Virtualisierung, Ansible, Linux, Windows Server, "
    "Kubernetes, OpenShift, Docker, Checkmk, PowerShell, Python, Storage, Backup, Rechenzentrum"
)
DEFAULT_UNWANTED = "Junior, Helpdesk, Service Desk, 1st Level, First Level, Vertrieb, Sales"
DEFAULT_EXCLUDED_WORDS = (
    "Ausbildung, Auszubildende, Azubi, Praktikum, Praktikant, Werkstudent, Trainee, Minijob, "
    "Aushilfe, Duales Studium, Abschlussarbeit, Thesis"
)

FIRST_RUN_DAYS = 14
RUN_DAYS = 2
KEEP_DAYS = 30
SEEN_DAYS = 90
MAX_DETAILS_PER_RUN = 15
MAX_PUSHES_PER_RUN = 5
MAX_LISTED = 30

EVENT_NEW_JOB = "jobradar_new_job"
ACTION_HIDE = "JOBRADAR_HIDE::"
NOTIFICATION_ID = "jobradar"

STORAGE_VERSION = 1
UPDATE_TIMEOUT = timedelta(minutes=5)
