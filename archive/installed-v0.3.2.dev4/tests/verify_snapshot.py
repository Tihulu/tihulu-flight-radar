#!/usr/bin/env python3
"""Read-only frozen Git source and per-blob manifest verification. No imports from app."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ARCHIVE = Path(__file__).resolve().parents[1]
REPO = ARCHIVE.parents[1]
SOURCE = ARCHIVE / "source"
MANIFEST = ARCHIVE / "manifest" / "provenance.json"
EXPECTED_COMMIT = "950f8278a625ce13a9a3c7e21bf9bf76d4b5888e"
EXPECTED_TREE = "0aa376600310576bb1de3c0c557e774c3233b6c5"
EXPECTED_COUNT = 120


def verify():
    if MANIFEST.is_symlink() or not MANIFEST.is_file():
        raise ValueError("Manifest must be a regular file")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if (manifest.get("pinned_source_commit") != EXPECTED_COMMIT
            or manifest.get("pinned_source_tree_sha") != EXPECTED_TREE
            or manifest.get("version") != "0.3.2.dev4"
            or manifest.get("source_file_count") != EXPECTED_COUNT):
        raise ValueError("Wrong frozen installed-source provenance")
    entries = manifest.get("files")
    if not isinstance(entries, list) or len(entries) != EXPECTED_COUNT:
        raise ValueError("Incomplete source manifest")

    paths = set()
    total_size = 0
    for f in entries:
        name = f["path"]
        rel = Path(name)
        if (rel.is_absolute() or name != rel.as_posix()
                or any(part in (".", "..") for part in rel.parts)
                or name in paths):
            raise ValueError("Unsafe or repeated archive path: " + name)
        paths.add(name)
        target = SOURCE / rel
        if target.is_symlink() or not target.is_file():
            raise ValueError("Missing or symlink source: " + name)
        for ancestor in target.parents:
            if ancestor == SOURCE.parent:
                break
            if ancestor.is_symlink():
                raise ValueError("Symlink ancestor: " + name)
        raw = target.read_bytes()
        if len(raw) != f["size"]:
            raise ValueError("Size mismatch: " + name)
        git_sha1 = hashlib.sha1(
            b"blob " + str(len(raw)).encode("ascii") + b"\x00" + raw
        ).hexdigest()
        if git_sha1 != f["git_blob_sha1"]:
            raise ValueError("Git blob SHA-1 mismatch: " + name)
        if f["mode"] not in ("100644", "100755"):
            raise ValueError("Unexpected source mode: " + name)
        total_size += len(raw)
    actual_paths = {
        p.relative_to(SOURCE).as_posix()
        for p in SOURCE.rglob("*") if p.is_file() or p.is_symlink()
    }
    if actual_paths != paths:
        raise ValueError("Missing/foreign archived file(s)")
    if total_size != manifest["source_bytes"]:
        raise ValueError("Source byte-count mismatch")
    git_tree = subprocess.check_output(
        ["git", "rev-parse", "HEAD:archive/installed-v0.3.2.dev4/source"],
        cwd=REPO, text=True
    ).strip()
    if git_tree != EXPECTED_TREE:
        raise ValueError("Archived subtree differs from observed installed-source Git tree")
    print(
        "PASS: 120 exact tracked source blobs, file metadata, "
        "original Git tree " + EXPECTED_TREE
    )




def verify_owner_reported_python_environment():
    """Verify saved owner-reported inventory against an independent typed manifest.

    This verifies consistency of archive evidence; it does not validate the
    real workstation's environment or reconstruct a wheel-locked installation.
    """
    observed = ARCHIVE / "manifest" / "observed-pip-freeze.txt"
    typed = ARCHIVE / "manifest" / "observed-python-environment.json"
    if observed.is_symlink() or typed.is_symlink():
        raise ValueError("Observed environment evidence cannot be symlinks")
    data = json.loads(typed.read_text(encoding="utf-8"))
    if (data.get("git_revision") != EXPECTED_COMMIT
            or data.get("source_archive_tree_sha") != EXPECTED_TREE
            or data.get("kind") != "owner-reported-python-distribution-inventory"
            or data.get("observed_python") != "3.12.3"):
        raise ValueError("Owner-reported Python environment provenance mismatch")
    actual = [line.strip() for line in observed.read_text(encoding="utf-8").splitlines()
              if line.strip() and not line.startswith("#")]
    expected = [f'{p["name"]}=={p["version"]}' for p in data["observed_packages"]]
    pinned = (
        "pip==26.3",
        "PySide6==6.12.0",
        "PySide6_Addons==6.12.0",
        "PySide6_Essentials==6.12.0",
        "PySide6_Pdf==6.12.0.140",
        "PySide6_WebEngine==6.12.0.140",
        "shiboken6==6.12.0",
        "tihulu-flight-radar==0.3.2.dev4",
    )
    if actual != expected or tuple(expected) != pinned:
        raise ValueError("User-observed package list changed")
    print(f"PASS: {len(expected)} observed Python distribution versions (not wheel hashes)")

if __name__ == "__main__":
    try:
        verify()
        verify_owner_reported_python_environment()
    except (OSError, KeyError, ValueError, subprocess.CalledProcessError) as exc:
        print("HOLD: " + str(exc), file=sys.stderr)
        raise SystemExit(2)
