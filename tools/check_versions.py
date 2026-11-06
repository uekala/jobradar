#!/usr/bin/env python3
"""Validate the legacy Home Assistant integration version metadata."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
integration_dir = ROOT / "custom_components" / "jobradar"
manifest = json.loads((integration_dir / "manifest.json").read_text(encoding="utf-8"))

if manifest.get("domain") != "jobradar":
    raise SystemExit("manifest domain must be 'jobradar'")

version = manifest.get("version")
if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
    raise SystemExit(f"Invalid Home Assistant manifest version: {version!r}")

# The repository root CHANGELOG.md belongs to the standalone service. Keep the
# integration's release history and version check scoped to its own directory.
changelog_path = integration_dir / "CHANGELOG.md"
if changelog_path.exists():
    headings = re.findall(
        r"^##\s+(\d+\.\d+\.\d+)(?:\s|$)",
        changelog_path.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if not headings or headings[0] != version:
        actual = headings[0] if headings else "no version heading"
        raise SystemExit(
            f"custom_components/jobradar/CHANGELOG.md starts at {actual}, "
            f"manifest version is {version}"
        )

print(f"Jobradar manifest version {version} is valid.")
