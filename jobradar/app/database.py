"""SQLite-Speicher für den eigenständigen Jobradar-Dienst."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path


DEFAULT_DB_PATH = "/data/jobradar.db"
SCHEMA_VERSION = 4


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
    """Schemaversion und Spalten von jobs einer vorhandenen Datenbank, None, wenn es keine gibt."""
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
    """Legt das Anfangsschema an. Kann bei jedem Start der Anwendung aufgerufen werden.

    Bevor eine vorhandene Datenbank migriert wird, wird ein geprüftes Backup in
    den Backup-Ordner geschrieben. Scheitert dieses Backup, läuft die Migration nicht.
    """
    path = db_path or database_path()
    existing = _existing_schema(path)
    if existing is not None:
        version, columns = existing
        if version < SCHEMA_VERSION or (columns and "base_score" not in columns):
            from .backup import create_backup  # lokaler Import: backup importiert dieses Modul

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

            CREATE TABLE IF NOT EXISTS imports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                imported_at TEXT NOT NULL,
                source_type TEXT NOT NULL,
                export_created TEXT,
                content_sha256 TEXT NOT NULL,
                report_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS import_archive (
                path TEXT PRIMARY KEY,
                collection TEXT NOT NULL,
                doc_id TEXT NOT NULL,
                version INTEGER,
                updated_at TEXT,
                data_json TEXT NOT NULL,
                import_id INTEGER NOT NULL REFERENCES imports(id),
                imported_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS job_status_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                status TEXT NOT NULL,
                previous TEXT,
                at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_job_status_events_job ON job_status_events(job_id, at);

            INSERT INTO schema_meta(key, value)
            VALUES ('schema_version', '4')
            ON CONFLICT(key) DO UPDATE SET value = excluded.value;
            """
        )
        columns = {row["name"] for row in db.execute("PRAGMA table_info(jobs)")}
        if "base_score" not in columns:
            db.execute("ALTER TABLE jobs ADD COLUMN base_score INTEGER")
            db.execute("UPDATE jobs SET base_score = score WHERE base_score IS NULL")
        _add_missing_columns(db, "jobs", {
            "imported_score": "INTEGER",
            "imported_at": "TEXT",
            "import_source": "TEXT",
            "import_json": "TEXT",
            "status_changed_at": "TEXT",
        })
        _add_missing_columns(db, "runs", {
            "sources": "TEXT",
            "note": "TEXT",
            "imported_at": "TEXT",
            "import_json": "TEXT",
        })
        db.execute(
            "UPDATE schema_meta SET value = ? WHERE key = 'schema_version'", (str(SCHEMA_VERSION),)
        )


def _add_missing_columns(db: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    """Ergänzt Spalten (NULL erlaubt), die ältere Datenbanken noch nicht haben."""
    existing = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
    for name, column_type in columns.items():
        if name not in existing:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {column_type}")


def database_is_ready(db_path: str | None = None) -> bool:
    with connect(db_path) as db:
        row = db.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()
        return row is not None and int(row["value"]) >= 2
