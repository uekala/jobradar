"""Ende-zu-Ende-Prüfung eines Cold-Backups und einer Wiederherstellung in Home Assistant.

Mit ``backup: cold`` stoppt der Supervisor die App (SIGTERM), archiviert
``/data`` und startet die App wieder. Diese Tests starten den echten Dienst mit
genau dem Befehl aus dem Dockerfile und gehen diesen Ablauf durch:

1. Daten über die API schreiben und ein internes Backup anlegen,
2. mit SIGTERM stoppen und ein sauberes Ende innerhalb des Standard-Stopp-
   Timeouts des Supervisors verlangen,
3. prüfen, dass ``/data`` eine vollständige, konsistente Datenbank enthält (kein
   Journal, kein halb geschriebenes Backup, ``PRAGMA integrity_check`` ok),
4. ``/data`` wie ein Home-Assistant-Backup archivieren,
5. auf den ursprünglichen Daten neu starten, dann absichtlich Daten verlieren,
6. das Archiv in ein leeres ``/data`` zurückspielen und jeden Datensatz vergleichen,
7. das interne Backup mit ``python -m app.backup restore-to`` wiederherstellen
   und erneut vergleichen.

Alle Daten hier sind erfundene Testdaten.
"""
from __future__ import annotations

import json
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import tarfile
import threading
import time
from pathlib import Path

import httpx
import pytest

APP_DIR = Path(__file__).resolve().parents[1]
SUPERVISOR_STOP_TIMEOUT = 10  # Sekunden, die der Supervisor bis SIGKILL wartet (Add-on-Standard)

pytestmark = pytest.mark.skipif(
    not hasattr(signal, "SIGTERM") or os.name != "posix",
    reason="needs POSIX signals like the add-on container",
)


def dockerfile_command() -> list[str]:
    for line in (APP_DIR / "Dockerfile").read_text(encoding="utf-8").splitlines():
        if line.startswith("CMD "):
            return json.loads(line[4:])
    raise AssertionError("Dockerfile enthält kein CMD")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Service:
    """Der Add-on-Prozess, gestartet wie im Container."""

    def __init__(self, data_dir: Path, log_file: Path):
        self.data_dir = data_dir
        self.log_file = log_file
        self.port = _free_port()
        self.process: subprocess.Popen | None = None
        self.url = f"http://127.0.0.1:{self.port}"

    def command(self) -> list[str]:
        command = dockerfile_command()
        assert command[0] == "python"
        command[0] = sys.executable
        command[command.index("--host") + 1] = "127.0.0.1"
        command[command.index("--port") + 1] = str(self.port)
        return command

    def start(self) -> Service:
        env = {
            **os.environ,
            "JOBRADAR_DB_PATH": str(self.data_dir / "jobradar.db"),
            "PYTHONUNBUFFERED": "1",
        }
        env.pop("JOBRADAR_BACKUP_DIR", None)
        env.pop("JOBRADAR_BACKUP_CHECK_SECONDS", None)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        log = self.log_file.open("a", encoding="utf-8")
        self.process = subprocess.Popen(
            self.command(), cwd=APP_DIR, env=env, stdout=log, stderr=subprocess.STDOUT
        )
        log.close()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise AssertionError(f"Dienst ist beim Start beendet worden:\n{self.log()}")
            try:
                if httpx.get(f"{self.url}/api/health", timeout=1).status_code == 200:
                    return self
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        self.kill()
        raise AssertionError(f"Dienst antwortet nicht:\n{self.log()}")

    def stop(self) -> tuple[int, float]:
        """Sendet SIGTERM wie der Supervisor und wartet höchstens dessen Stopp-Timeout."""
        assert self.process is not None
        started = time.monotonic()
        self.process.send_signal(signal.SIGTERM)
        try:
            code = self.process.wait(timeout=SUPERVISOR_STOP_TIMEOUT)
        except subprocess.TimeoutExpired as err:
            self.kill()
            raise AssertionError(
                f"Dienst nicht innerhalb von {SUPERVISOR_STOP_TIMEOUT}s beendet:\n{self.log()}"
            ) from err
        return code, time.monotonic() - started

    def kill(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.kill()
            self.process.wait()

    def log(self) -> str:
        return self.log_file.read_text(encoding="utf-8") if self.log_file.exists() else ""

    def get(self, path: str):
        response = httpx.get(f"{self.url}{path}", timeout=5)
        response.raise_for_status()
        return response.json()

    def send(self, method: str, path: str, body: dict):
        response = httpx.request(method, f"{self.url}{path}", json=body, timeout=5)
        response.raise_for_status()
        return response.json()


@pytest.fixture
def services(tmp_path):
    started: list[Service] = []

    def make(name: str) -> Service:
        service = Service(tmp_path / name / "data", tmp_path / f"{name}.log")
        started.append(service)
        return service

    yield make
    for service in started:
        service.kill()


def seed(service: Service) -> None:
    for number in range(1, 6):
        job = service.send(
            "POST",
            "/api/jobs",
            {
                "title": f"Teststelle {number}",
                "company": "Beispiel GmbH",
                "location": "Teststadt",
                "url": f"https://example.invalid/stelle/{number}",
                "source": "test",
                "score": 50 + number,
            },
        )
        if number % 2 == 0:
            service.send(
                "PATCH",
                f"/api/jobs/{job['id']}",
                {"status": "gemerkt", "notes": f"Notiz {number} mit Ümlaut"},
            )
    service.send(
        "PUT",
        "/api/profile",
        {"data": {"location": "Teststadt", "radius_km": 30, "roles": ["Testrolle"]}},
    )
    service.send(
        "PUT",
        "/api/rules/test-regel",
        {"data": {"name": "Testregel", "category": "positive", "terms": ["test"], "weight": 10}},
    )
    service.send(
        "PUT",
        "/api/sources/test-quelle",
        {"name": "Testquelle", "source_type": "manual", "queries": ["Testbegriff"]},
    )


def snapshot(service: Service) -> dict:
    jobs = service.get("/api/jobs")
    items = jobs["items"] if isinstance(jobs, dict) else jobs
    return {
        "jobs": sorted(items, key=lambda job: job["id"]),
        "profile": service.get("/api/profile"),
        "rules": service.get("/api/rules"),
        "sources": service.get("/api/sources"),
    }


def assert_clean_exit(service: Service, code: int) -> None:
    # uvicorn fährt sauber herunter und löst SIGTERM danach erneut aus, deshalb
    # endet der Prozess „durch Signal“ (Docker zeigt Exit-Code 143). Entscheidend
    # ist, dass das Herunterfahren im Lifespan bis zum Ende lief.
    log = service.log()
    assert code in (0, -signal.SIGTERM), log
    assert "Jobradar beendet, Datenbank geschlossen" in log
    assert "Application shutdown complete." in log


def assert_cleanly_closed(data_dir: Path) -> None:
    database = data_dir / "jobradar.db"
    assert database.is_file()
    leftovers = [
        p.name
        for p in data_dir.iterdir()
        if p.name.endswith(("-journal", "-wal", "-shm"))
    ]
    assert leftovers == [], f"Datenbank nicht sauber geschlossen: {leftovers}"
    assert not list((data_dir / "backups").glob("*.partial"))
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        connection.close()


def ha_backup(data_dir: Path, archive: Path) -> None:
    """Archiviert /data so, wie ein Home-Assistant-Backup die Daten eines Add-ons ablegt."""
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(data_dir, arcname="data")


def ha_restore(archive: Path, target_root: Path) -> Path:
    target_root.mkdir(parents=True)
    with tarfile.open(archive) as tar:
        tar.extractall(target_root, filter="data")
    return target_root / "data"


def test_cold_backup_and_restore_keep_every_record(services, tmp_path):
    original = services("original").start()
    seed(original)
    expected = snapshot(original)
    assert len(expected["jobs"]) == 5
    internal = original.send("POST", "/api/backups", {})
    assert internal["rows"]["jobs"] == 5

    # 1. Der Supervisor stoppt die App für das Cold-Backup.
    code, seconds = original.stop()
    assert_clean_exit(original, code)
    assert seconds < SUPERVISOR_STOP_TIMEOUT
    assert_cleanly_closed(original.data_dir)

    # 2. Der Supervisor archiviert /data und startet die App wieder.
    archive = tmp_path / "ha-backup.tar.gz"
    ha_backup(original.data_dir, archive)
    original.start()
    assert snapshot(original) == expected
    original.stop()

    # 3. Nach dem Backup gehen Daten verloren.
    with sqlite3.connect(original.data_dir / "jobradar.db") as db:
        db.execute("DELETE FROM jobs")
    original.start()
    assert snapshot(original)["jobs"] == []
    original.stop()

    # 4. Das Home-Assistant-Backup in ein leeres /data zurückspielen.
    restored_dir = ha_restore(archive, tmp_path / "restored")
    restored = Service(restored_dir, tmp_path / "restored.log")
    restored.start()
    try:
        assert snapshot(restored) == expected
        backups = restored.get("/api/backups")["items"]
        assert internal["file"] in {item["file"] for item in backups}
        assert not any("pre-migration" in item["file"] for item in backups)
    finally:
        restored.stop()

    # 5. Das interne Backup mit der CLI in eine neue Datei wiederherstellen.
    target_dir = tmp_path / "from-internal" / "data"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.backup",
            "restore-to",
            str(restored_dir / "backups" / internal["file"]),
            str(target_dir / "jobradar.db"),
        ],
        cwd=APP_DIR,
        env={**os.environ, "JOBRADAR_DB_PATH": str(restored_dir / "jobradar.db")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["rows"]["jobs"] == 5
    from_internal = Service(target_dir, tmp_path / "from-internal.log")
    from_internal.start()
    try:
        assert snapshot(from_internal) == expected
    finally:
        from_internal.stop()


def test_stop_during_writes_keeps_every_acknowledged_record(services):
    service = services("busy").start()
    acknowledged: list[str] = []
    attempted = 0
    stop_writing = threading.Event()

    def writer() -> None:
        nonlocal attempted
        with httpx.Client(base_url=service.url, timeout=5) as client:
            while not stop_writing.is_set():
                attempted += 1
                try:
                    response = client.post("/api/jobs", json={"title": f"Last {attempted}"})
                except httpx.HTTPError:
                    return
                if response.status_code == 201:
                    acknowledged.append(response.json()["id"])

    thread = threading.Thread(target=writer)
    thread.start()
    deadline = time.monotonic() + 10
    while len(acknowledged) < 25 and time.monotonic() < deadline:
        time.sleep(0.02)
    code, _ = service.stop()
    stop_writing.set()
    thread.join(timeout=10)

    assert_clean_exit(service, code)
    assert len(acknowledged) >= 25
    assert_cleanly_closed(service.data_dir)
    with sqlite3.connect(f"file:{service.data_dir / 'jobradar.db'}?mode=ro", uri=True) as db:
        stored = {row[0] for row in db.execute("SELECT id FROM jobs")}
    assert set(acknowledged) <= stored
    assert len(stored) <= attempted


def test_container_command_stops_within_supervisor_timeout():
    command = dockerfile_command()
    assert command[:4] == ["python", "-m", "uvicorn", "app.main:app"]
    graceful = int(command[command.index("--timeout-graceful-shutdown") + 1])
    assert 0 < graceful < SUPERVISOR_STOP_TIMEOUT
