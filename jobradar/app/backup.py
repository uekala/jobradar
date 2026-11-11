"""Consistent SQLite backups for the standalone Jobradar.

Rules:
- Backups use SQLite's online backup API, so they are consistent even while
  the service is writing.
- Every backup is checked with ``PRAGMA integrity_check`` before it counts.
- Nothing here ever writes to the live database. A restore always goes into a
  new file; switching to it is a manual step (see docs/architecture.md).
- Only routine backups (daily, manual) are pruned. Backups written before a
  schema migration are kept until someone deletes them on purpose.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .database import database_path

BACKUP_PATTERN = re.compile(r"^jobradar-\d{8}-\d{6}(?:-\d+)?-(?P<reason>[a-z0-9-]+)\.db$")
DEFAULT_KEEP = 14
ROUTINE_REASONS = frozenset({"daily", "manual"})


class BackupError(RuntimeError):
    """A backup could not be created or failed verification."""


def backup_dir(db_path: str | None = None) -> Path:
    configured = os.environ.get("JOBRADAR_BACKUP_DIR")
    if configured:
        return Path(configured)
    return Path(db_path or database_path()).parent / "backups"


def _slug(reason: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", reason.lower()).strip("-")
    return slug or "manual"


def _target_path(directory: Path, reason: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    candidate = directory / f"jobradar-{stamp}-{_slug(reason)}.db"
    counter = 1
    while candidate.exists():
        candidate = directory / f"jobradar-{stamp}-{counter}-{_slug(reason)}.db"
        counter += 1
    return candidate


def verify_backup(path: str | Path) -> dict:
    """Integrity check plus row counts; raises BackupError if the file is damaged."""
    path = Path(path)
    if not path.is_file():
        raise BackupError(f"Backup {path} existiert nicht")
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        result = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise BackupError(f"Backup {path.name} ist beschädigt: {result}")
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        counts = {
            table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in tables
        }
        version = None
        if "schema_meta" in tables:
            row = connection.execute(
                "SELECT value FROM schema_meta WHERE key = 'schema_version'"
            ).fetchone()
            version = row[0] if row else None
    except sqlite3.DatabaseError as err:
        raise BackupError(f"Backup {path.name} ist keine lesbare SQLite-Datei: {err}") from err
    finally:
        connection.close()
    return {
        "file": path.name,
        "size_bytes": path.stat().st_size,
        "schema_version": version,
        "rows": counts,
    }


def create_backup(
    db_path: str | None = None, directory: Path | None = None, reason: str = "manual"
) -> Path:
    """Copy the live database into a new, verified backup file."""
    source_path = Path(db_path or database_path())
    if not source_path.is_file():
        raise BackupError(f"Datenbank {source_path} existiert nicht")
    directory = directory or backup_dir(str(source_path))
    directory.mkdir(parents=True, exist_ok=True)
    target = _target_path(directory, reason)
    partial = target.with_suffix(".db.partial")

    source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True)
    destination = sqlite3.connect(partial)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    os.chmod(partial, 0o600)
    try:
        verify_backup(partial)
    except BackupError:
        partial.unlink(missing_ok=True)
        raise
    partial.rename(target)
    return target


def list_backups(directory: Path | None = None) -> list[Path]:
    directory = directory or backup_dir()
    if not directory.is_dir():
        return []
    files = [p for p in directory.iterdir() if p.is_file() and BACKUP_PATTERN.match(p.name)]
    return sorted(files, key=lambda p: p.name, reverse=True)


def backup_reason(path: Path) -> str | None:
    match = BACKUP_PATTERN.match(path.name)
    return match.group("reason") if match else None


def prune_backups(directory: Path | None = None, keep: int = DEFAULT_KEEP) -> list[Path]:
    """Delete the oldest routine backups beyond ``keep``.

    Only daily and manual backups count and get deleted; pre-migration
    backups and any other file in the folder are left alone.
    """
    if keep < 1:
        raise ValueError("keep muss mindestens 1 sein")
    routine = [p for p in list_backups(directory) if backup_reason(p) in ROUTINE_REASONS]
    removed = []
    for path in routine[keep:]:
        path.unlink()
        removed.append(path)
    return removed


def remove_stale_partials(directory: Path | None = None) -> list[Path]:
    """Delete half-written backup files left behind by an interrupted backup.

    A ``.db.partial`` file never counts as a backup. One can only remain if
    the process was killed while copying, e.g. when Home Assistant stops the
    app for a cold backup and the stop timeout runs out.
    """
    directory = directory or backup_dir()
    if not directory.is_dir():
        return []
    removed = []
    for path in directory.glob("jobradar-*.db.partial"):
        if path.is_file():
            path.unlink()
            removed.append(path)
    return removed


def latest_backup_age(directory: Path | None = None) -> timedelta | None:
    backups = list_backups(directory)
    if not backups:
        return None
    modified = datetime.fromtimestamp(backups[0].stat().st_mtime, tz=timezone.utc)
    return datetime.now(timezone.utc) - modified


def ensure_recent_backup(
    db_path: str | None = None, max_age: timedelta = timedelta(hours=24), keep: int = DEFAULT_KEEP
) -> Path | None:
    """Create a scheduled backup if the newest one is older than ``max_age``."""
    source_path = Path(db_path or database_path())
    if not source_path.is_file():
        return None
    directory = backup_dir(str(source_path))
    age = latest_backup_age(directory)
    if age is not None and age < max_age:
        return None
    created = create_backup(str(source_path), directory, reason="daily")
    prune_backups(directory, keep)
    return created


def restore_to(backup: str | Path, target: str | Path) -> dict:
    """Restore a backup into a NEW file. Refuses to overwrite anything."""
    backup = Path(backup)
    target = Path(target)
    if target.exists():
        raise BackupError(
            f"{target} existiert bereits; eine Wiederherstellung überschreibt nie eine Datei"
        )
    if target.resolve() == Path(database_path()).resolve():
        raise BackupError("Die Live-Datenbank wird nie direkt überschrieben")
    verify_backup(backup)
    target.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(f"file:{backup}?mode=ro", uri=True)
    destination = sqlite3.connect(target)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    os.chmod(target, 0o600)
    return verify_backup(target)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.backup", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create", help="Backup der Live-Datenbank anlegen")
    create.add_argument("--reason", default="manual")
    sub.add_parser("list", help="Vorhandene Backups anzeigen")
    verify = sub.add_parser("verify", help="Backup prüfen")
    verify.add_argument("file")
    restore = sub.add_parser("restore-to", help="Backup in eine NEUE Datei wiederherstellen")
    restore.add_argument("file")
    restore.add_argument("target")
    args = parser.parse_args(argv)

    try:
        if args.command == "create":
            print(create_backup(reason=args.reason))
        elif args.command == "list":
            for path in list_backups():
                print(path.name)
        elif args.command == "verify":
            print(json.dumps(verify_backup(args.file), indent=2, ensure_ascii=False))
        elif args.command == "restore-to":
            print(json.dumps(restore_to(args.file, args.target), indent=2, ensure_ascii=False))
    except BackupError as err:
        print(f"Fehler: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
