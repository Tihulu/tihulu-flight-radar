#!/usr/bin/env python3
"""CI-only parity check for a disposable reproduction of the owner-reported pipx versions.

Does not read the owner's machine, manage a service, or claim file-level wheel parity.
Call from a newly created, disposable Python 3.12.3 virtual environment.
"""
from __future__ import annotations

import json
import re
import sys
from importlib import metadata
from pathlib import Path

ARCHIVE = Path(__file__).resolve().parents[1]
OWNER_EVIDENCE = ARCHIVE / "manifest" / "observed-python-environment.json"
SOURCE_COMMIT = "950f8278a625ce13a9a3c7e21bf9bf76d4b5888e"
SOURCE_TREE = "0aa376600310576bb1de3c0c557e774c3233b6c5"


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def main() -> None:
    evidence = json.loads(OWNER_EVIDENCE.read_text(encoding="utf-8"))
    if (evidence["git_revision"] != SOURCE_COMMIT
            or evidence["source_archive_tree_sha"] != SOURCE_TREE):
        raise RuntimeError("Frozen source provenance does not match user inventory")
    if sys.version_info[:3] != (3, 12, 3):
        raise RuntimeError("Replay Python must equal owner's observed 3.12.3")
    if sys.prefix == sys.base_prefix:
        raise RuntimeError("Refusing to validate the system Python environment")

    expected = {canonical(p["name"]): p["version"] for p in evidence["observed_packages"]}
    actual = {}
    for d in metadata.distributions():
        name = d.metadata.get("Name")
        if not name:
            continue
        key = canonical(name)
        if key in actual and actual[key] != d.version:
            raise RuntimeError("Conflicting installed versions: " + name)
        actual[key] = d.version

    if actual != expected:
        missing = {k: v for k, v in expected.items() if actual.get(k) != v}
        extra = {k: v for k, v in actual.items() if k not in expected}
        raise RuntimeError(f"Pinned inventory mismatch: missing/mismatched={missing}, extra={extra}")
    app = metadata.distribution("tihulu-flight-radar")
    if app.version != "0.3.2.dev4":
        raise RuntimeError("Installed app package version differs")
    # Real module imports verify the Qt wheel artifacts exist and link on CI Linux.
    import PySide6  # noqa: F401
    from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
    import tihulu_flight_radar  # noqa: F401
    print("PASS: disposable CI Python 3.12.3 environment matches all 8 owner-reported "
          "distribution versions; Qt WebEngine and installed radar module import.")
    print("LIMIT: wheel bytes, original pipx environment, COSMIC graphics and RF hardware unverified.")


if __name__ == "__main__":
    main()
