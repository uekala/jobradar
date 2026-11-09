"""SQLite persistence for the standalone Jobradar service."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path


DEFAULT_DB_PATH = "/data/jobradar.db"
SCHEMA_VERSION = 3


def database_path() -> str:
    return os.environ.get("JOBRADAR_DB_PATH", DEFAULT_DB_PATH)


def connect(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or database_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _existing_schema(path: str) -> tuple[int, set[str]] | None:
    """Schema version and jobs columns of an existing database, None if there is none."""
    file = Path(path)
    if not file.is_file() or file.stat().st_size == 0:
        return None
    connection = sqlite3.connect(f"file:{file}?mode=ro", uri=True)
    try:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        tables = {row[0] for row in rows}
        if not tables:
            return None
        version = 0
        if "schema_meta" in tables:
            row = connection.execute(
                "SELECT value FROM schema_meta WHERE key = 'schema_version'"
            ).fetchone()
            version = int(row[0]) if row else 0
        columns = set()
        if "jobs" in tables:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)")}
        return version, columns
    finally:
        connection.close()


def initialize_database(db_path: str | None = None) -> None:
    """Create the initial schema. Safe to call on every application start.

    Before an existing database is migrated, a verified backup is written to
    the backups folder. If that backup fails, the migration does not run.
    """
    path = db_path or database_path()
    existing = _existing_schema(path)
    if existing is not None:
        version, columns = existing
        if version < SCHEMA_VERSION or (columns and "base_score" not in columns):
            from .backup import create_backup  # local import: backup imports this module

            create_backup(path, reason=f"pre-migration-v{version}-to-v{SCHEMA_VERSION}")
    with connect(path) as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                company TEXT,
                location TEXT,
                url TEXT,
                source TEXT,
                description TEXT,
                salary_min REAL,
                salary_max REAL,
                remote_type TEXT,
                score INTEGER,
                base_score INTEGER,
                status TEXT NOT NULL DEFAULT 'neu',
                notes TEXT NOT NULL DEFAULT '',
                published_at TEXT,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                raw_json TEXT
            );

            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL,
                jobs_found INTEGER NOT NULL DEFAULT 0,
                jobs_new INTEGER NOT NULL DEFAULT 0,
                error_summary TEXT
            );

            CREATE TABLE IF NOT EXISTS profile (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                data_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS search_rules (
                id TEXT PRIMARY KEY,
                data_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS job_sources (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                source_type TEXT NOT NULL DEFAULT 'web',
                base_url TEXT,
                enabled INTEGER NOT NULL DEFAULT 1,
                query_json TEXT NOT NULL DEFAULT '[]',
                config_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_job_sources_enabled ON job_sources(enabled);

            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
            CREATE INDEX IF NOT EXISTS idx_jobs_score ON jobs(score);
            CREATE INDEX IF NOT EXISTS idx_jobs_first_seen ON jobs(first_seen_at);

            INSERT INTO schema_meta(key, value)
            VALUES ('schema_version', '3')
            ON CONFLICT(key) DO UPDATE SET value = excluded.value;
            """
        )
        columns = {row["name"] for row in db.execute("PRAGMA table_info(jobs)")}
        if "base_score" not in columns:
            db.execute("ALTER TABLE jobs ADD COLUMN base_score INTEGER")
            db.execute("UPDATE jobs SET base_score = score WHERE base_score IS NULL")
        db.execute("UPDATE schema_meta SET value = '3' WHERE key = 'schema_version'")


def database_is_ready(db_path: str | None = None) -> bool:
    with connect(db_path) as db:
        row = db.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()
        return row is not None and int(row["value"]) >= 2
