"""Release metadata of the add-on must agree, and cold backups stay on from 0.3.0."""
from __future__ import annotations

import re
from pathlib import Path

from app.main import app

APP_DIR = Path(__file__).resolve().parents[1]


def _config_value(key: str) -> str | None:
    text = (APP_DIR / "config.yaml").read_text(encoding="utf-8")
    match = re.search(rf'^{key}:\s*"?([^"\n#]+?)"?\s*(?:#.*)?$', text, re.MULTILINE)
    return match.group(1).strip() if match else None


def _version_tuple(version: str) -> tuple[int, ...]:
    assert re.fullmatch(r"\d+\.\d+\.\d+", version), version
    return tuple(int(part) for part in version.split("."))


def test_versions_agree():
    config_version = _config_value("version")
    changelog = (APP_DIR / "CHANGELOG.md").read_text(encoding="utf-8")
    headings = re.findall(r"^##\s+(\d+\.\d+\.\d+)\b", changelog, re.MULTILINE)

    assert config_version is not None
    assert app.version == config_version, "app/main.py und config.yaml nennen andere Versionen"
    assert headings, "jobradar/CHANGELOG.md hat keinen Versionseintrag"
    assert headings[0] == config_version, "Neuester CHANGELOG-Eintrag passt nicht zu config.yaml"


def test_cold_backup_from_0_3_0():
    version = _version_tuple(_config_value("version") or "")
    if version >= (0, 3, 0):
        assert _config_value("backup") == "cold"


def test_database_lives_in_backed_up_data_folder():
    dockerfile = (APP_DIR / "Dockerfile").read_text(encoding="utf-8")
    assert "ENV JOBRADAR_DB_PATH=/data/jobradar.db" in dockerfile
