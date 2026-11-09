import os
import sqlite3
import stat
from datetime import timedelta

import pytest
from app import backup
from app.database import connect, initialize_database
from fastapi.testclient import TestClient


def _db_with_jobs(tmp_path, count=3):
    db_file = tmp_path / "jobradar.db"
    initialize_database(str(db_file))
    with connect(str(db_file)) as db:
        for i in range(count):
            db.execute(
                "INSERT INTO jobs (id, title, first_seen_at, last_seen_at, created_at, updated_at) "
                "VALUES (?, ?, 'x', 'x', 'x', 'x')",
                (f"job-{i}", f"Stelle {i}"),
            )
    return db_file


@pytest.fixture(autouse=True)
def _isolated_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("JOBRADAR_DB_PATH", str(tmp_path / "jobradar.db"))
    monkeypatch.delenv("JOBRADAR_BACKUP_DIR", raising=False)


def test_backup_is_consistent_verified_and_private(tmp_path):
    db_file = _db_with_jobs(tmp_path)
    path = backup.create_backup(str(db_file), reason="manual")

    assert path.parent == tmp_path / "backups"
    assert backup.BACKUP_PATTERN.match(path.name)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    info = backup.verify_backup(path)
    assert info["rows"]["jobs"] == 3
    assert info["schema_version"] == "3"
    assert not list(path.parent.glob("*.partial"))


def test_backup_of_missing_database_fails(tmp_path):
    with pytest.raises(backup.BackupError):
        backup.create_backup(str(tmp_path / "fehlt.db"))


def test_damaged_file_fails_verification(tmp_path):
    broken = tmp_path / "jobradar-20260101-000000-manual.db"
    broken.write_bytes(b"keine sqlite-datei" * 100)
    with pytest.raises(backup.BackupError):
        backup.verify_backup(broken)


def test_restore_goes_into_new_file_and_matches(tmp_path):
    db_file = _db_with_jobs(tmp_path, count=5)
    path = backup.create_backup(str(db_file))
    with connect(str(db_file)) as db:
        db.execute("DELETE FROM jobs")

    restored = tmp_path / "restore" / "jobradar-restored.db"
    info = backup.restore_to(path, restored)

    assert info["rows"]["jobs"] == 5
    with sqlite3.connect(restored) as db:
        titles = [row[0] for row in db.execute("SELECT title FROM jobs ORDER BY id")]
    assert titles == [f"Stelle {i}" for i in range(5)]
    # The live database was not touched by the restore.
    with sqlite3.connect(db_file) as db:
        assert db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0


def test_restore_never_overwrites(tmp_path):
    db_file = _db_with_jobs(tmp_path)
    path = backup.create_backup(str(db_file))
    existing = tmp_path / "vorhanden.db"
    existing.write_bytes(b"x")
    with pytest.raises(backup.BackupError):
        backup.restore_to(path, existing)
    assert existing.read_bytes() == b"x"


def test_restore_refuses_live_database_path(tmp_path, monkeypatch):
    db_file = _db_with_jobs(tmp_path)
    path = backup.create_backup(str(db_file))
    live = tmp_path / "neu-live.db"
    monkeypatch.setenv("JOBRADAR_DB_PATH", str(live))
    with pytest.raises(backup.BackupError):
        backup.restore_to(path, live)
    assert not live.exists()


def test_prune_keeps_newest_and_only_touches_backups(tmp_path):
    directory = tmp_path / "backups"
    directory.mkdir()
    names = [f"jobradar-202601{day:02d}-000000-daily.db" for day in range(1, 8)]
    for name in names:
        (directory / name).write_bytes(b"")
    (directory / "notizen.txt").write_text("bleibt")
    db_file = _db_with_jobs(tmp_path)

    removed = backup.prune_backups(directory, keep=3)

    assert sorted(p.name for p in removed) == names[:4]
    assert sorted(p.name for p in backup.list_backups(directory)) == names[4:]
    assert (directory / "notizen.txt").exists()
    assert db_file.exists()


def test_ensure_recent_backup_creates_once_per_day(tmp_path):
    db_file = _db_with_jobs(tmp_path)
    first = backup.ensure_recent_backup(str(db_file))
    assert first is not None
    assert backup.ensure_recent_backup(str(db_file)) is None
    assert backup.ensure_recent_backup(str(db_file), max_age=timedelta(0)) is not None


def test_migration_from_v2_writes_backup_first(tmp_path):
    db_file = tmp_path / "jobradar.db"
    with sqlite3.connect(db_file) as db:
        db.executescript(
            """
            CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO schema_meta VALUES ('schema_version', '2');
            CREATE TABLE jobs (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, company TEXT, location TEXT,
                url TEXT, source TEXT, description TEXT, salary_min REAL, salary_max REAL,
                remote_type TEXT, score INTEGER, status TEXT NOT NULL DEFAULT 'neu',
                notes TEXT NOT NULL DEFAULT '', published_at TEXT,
                first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, raw_json TEXT
            );
            INSERT INTO jobs (id, title, score, first_seen_at, last_seen_at, created_at, updated_at)
            VALUES ('alt', 'Bestehende Stelle', 77, 'x', 'x', 'x', 'x');
            """
        )

    initialize_database(str(db_file))

    backups = backup.list_backups(tmp_path / "backups")
    assert len(backups) == 1
    assert "pre-migration-v2-to-v3" in backups[0].name
    info = backup.verify_backup(backups[0])
    assert info["schema_version"] == "2"
    assert info["rows"]["jobs"] == 1
    with connect(str(db_file)) as db:
        row = db.execute("SELECT title, base_score FROM jobs WHERE id = 'alt'").fetchone()
    assert (row["title"], row["base_score"]) == ("Bestehende Stelle", 77)


def test_no_backup_for_new_or_current_database(tmp_path):
    db_file = tmp_path / "jobradar.db"
    initialize_database(str(db_file))
    initialize_database(str(db_file))
    assert backup.list_backups(tmp_path / "backups") == []


def test_migration_stops_when_backup_fails(tmp_path, monkeypatch):
    db_file = tmp_path / "jobradar.db"
    with sqlite3.connect(db_file) as db:
        db.executescript(
            "CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
            "INSERT INTO schema_meta VALUES ('schema_version', '2');"
        )

    def fail(*args, **kwargs):
        raise backup.BackupError("Datenträger voll")

    monkeypatch.setattr(backup, "create_backup", fail)
    with pytest.raises(backup.BackupError):
        initialize_database(str(db_file))
    with sqlite3.connect(db_file) as db:
        version = db.execute("SELECT value FROM schema_meta").fetchone()[0]
    assert version == "2"


def test_backup_api(tmp_path):
    with TestClient(__import__("app.main", fromlist=["app"]).app) as client:
        startup = client.get("/api/backups").json()["items"]
        assert len(startup) == 1  # daily backup on first start
        created = client.post("/api/backups")
        assert created.status_code == 201
        assert created.json()["rows"]["jobs"] == 0
        assert len(client.get("/api/backups").json()["items"]) == 2


def test_backup_dir_can_be_configured(tmp_path, monkeypatch):
    target = tmp_path / "anderswo"
    monkeypatch.setenv("JOBRADAR_BACKUP_DIR", str(target))
    db_file = _db_with_jobs(tmp_path)
    path = backup.create_backup(str(db_file))
    assert path.parent == target


def test_command_line(tmp_path, capsys):
    db_file = _db_with_jobs(tmp_path, count=2)
    assert backup.main(["create", "--reason", "vor Update"]) == 0
    created = capsys.readouterr().out.strip()
    assert created.endswith("-vor-update.db")
    assert backup.main(["list"]) == 0
    assert created.rsplit("/", 1)[-1] in capsys.readouterr().out
    assert backup.main(["verify", created]) == 0
    assert '"jobs": 2' in capsys.readouterr().out
    target = tmp_path / "wiederhergestellt.db"
    assert backup.main(["restore-to", created, str(target)]) == 0
    assert target.exists()
    assert backup.main(["restore-to", created, str(db_file)]) == 1
    assert "überschreibt nie" in capsys.readouterr().err
