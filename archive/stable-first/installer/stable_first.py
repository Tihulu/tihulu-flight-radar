#!/usr/bin/env python3
"""Isolated, opt-in Stable First installer. No sudo, systemctl or SDR actions."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from shlex import quote

OWNER = "tihulu-flight-stable-first/v1"
SOURCE_SHA = "67280cd84feb89faec6a80f5fe2a55ce5f7b89e6"
ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "source"
MANIFEST = ROOT / "manifest" / "provenance.json"
HOME = Path.home()
BASE = HOME / ".local" / "share" / "tihulu-flight-stable-first"
RELEASES = BASE / "releases"
CURRENT = BASE / "current"
STATE = BASE / "state.json"
LAUNCHER = HOME / ".local" / "bin" / "tihulu-flight-stable-first"
DESKTOP = HOME / ".local" / "share" / "applications" / "tihulu-flight-stable-first.desktop"
VERSION = "0.3.1"
PINNED_QT = ("PySide6==6.12.0", "PySide6-WebEngine==6.12.0.140")


def fail(message):
    raise RuntimeError(message)


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def no_link(path):
    if path.is_symlink():
        fail(f"Refusing symlink: {path}")


def owner_file(path):
    no_link(path)
    if not path.is_file() or path.stat().st_uid != os.getuid():
        fail(f"Refusing unowned/non-file path: {path}")


def secure_dir(path):
    path = Path(path)
    if path != HOME and HOME not in path.parents:
        fail(f"Refusing path outside home: {path}")
    chain = list(reversed(path.parents))
    for part in [p for p in chain if p == HOME or HOME in p.parents] + [path]:
        no_link(part)
        if part.exists():
            if not part.is_dir() or part.stat().st_uid != os.getuid():
                fail(f"Refusing foreign directory: {part}")
        else:
            part.mkdir(mode=0o700)


def safe_rel(name):
    path = Path(name)
    if path.is_absolute() or not path.parts or any(
        part in ("", ".", "..") for part in path.parts
    ):
        fail(f"Invalid manifest path: {name}")
    return path


def verify_source():
    owner_file(MANIFEST)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("source_commit") != SOURCE_SHA or manifest.get("files_count") != 64:
        fail("Wrong legacy source SHA or incomplete manifest")
    if manifest.get("source_tree_sha") != "a916732793c405e73f5de996b528ac96437222cd":
        fail("Wrong frozen legacy tree SHA")
    entries = manifest.get("files", [])
    if len(entries) != 64 or len({e["path"] for e in entries}) != len(entries):
        fail("Duplicate or missing manifest paths")
    for entry in entries:
        rel = safe_rel(entry["path"])
        file_path = SOURCE / rel
        for parent in file_path.parents:
            if parent == SOURCE.parent:
                break
            no_link(parent)
        owner_file(file_path)
        if file_path.stat().st_size != entry["size"]:
            fail(f"Source size mismatch: {rel}")
        if digest(file_path) != entry["sha256"]:
            fail(f"SHA-256 mismatch: {rel}")
        mode = stat.S_IMODE(file_path.stat().st_mode)
        if mode != int(entry["mode"], 8) & 0o777:
            fail(f"Source permissions mismatch: {rel}")
    return manifest


def read_state():
    if not STATE.exists() and not STATE.is_symlink():
        return None
    owner_file(STATE)
    value = json.loads(STATE.read_text(encoding="utf-8"))
    if value.get("owner") != OWNER:
        fail("Unknown ownership marker; refusing operation")
    return value


def expected_shortcuts():
    py = quote(str(CURRENT / "venv" / "bin" / "python"))
    entry = quote(str(CURRENT / "safe_entry.py"))
    config = quote(str(HOME / ".config" / "tihulu-flight-stable-first"))
    cache = quote(str(HOME / ".cache" / "tihulu-flight-stable-first"))
    data = quote(str(BASE / "user-data"))
    launch = (
        "#!/bin/sh\n# TIHULU_STABLE_FIRST_OWNED_v1\nset -eu\n"
        f"export XDG_CONFIG_HOME={config}\n"
        f"export XDG_CACHE_HOME={cache}\n"
        f"export XDG_DATA_HOME={data}\n"
        "export TIHULU_STABLE_FIRST_PASSIVE=1\n"
        f"exec {py} {entry} \"$@\"\n"
    )
    executable = str(LAUNCHER).replace("\\", "\\\\").replace('"', '\\"')
    desktop = (
        "[Desktop Entry]\nType=Application\nName=TIHULU Flight Radar (Stable First)\n"
        "Comment=Archived legacy v0.3.1 — passive, isolated receiver access\n"
        f"Exec=\"{executable}\"\nTerminal=false\n"
        "Categories=Network;Utility;\n"
        "StartupNotify=true\n"
        "X-Tihulu-Stable-First-Owner=v1\n"
    )
    return launch.encode(), desktop.encode()


def check_state(state, full_inventory=False):
    if state is None:
        if CURRENT.exists() or CURRENT.is_symlink() or LAUNCHER.exists() or LAUNCHER.is_symlink() or DESKTOP.exists() or DESKTOP.is_symlink():
            fail("Foreign/orphan installation artifacts found; refusing takeover")
        return
    if not CURRENT.is_symlink():
        fail("Missing or foreign active-install link")
    active = state["active"]
    versions = state["releases"]
    if active not in versions:
        fail("Current release is not recorded as owned")
    if os.readlink(CURRENT) != "releases/" + active:
        fail("Active release link does not match state")
    for target, key in ((LAUNCHER, "launcher_sha256"), (DESKTOP, "desktop_sha256")):
        owner_file(target)
        if digest(target) != state[key]:
            fail(f"Foreign-modified installation entry: {target}")
    for name, record in versions.items():
        if not re.fullmatch(r"0\.3\.1-67280cd8-[a-f0-9]{12}", name):
            fail("Unexpected release identifier")
        release = RELEASES / name
        no_link(release)
        marker = release / "installed.json"
        owner_file(marker)
        meta = json.loads(marker.read_text())
        if meta != {"owner": OWNER, "source_sha": SOURCE_SHA, "release": name}:
            fail("Release ownership marker mismatch")
        if full_inventory:
            verify_inventory(release, record["inventory_sha256"])


def inventory(release):
    result = {}
    for p in sorted(release.rglob("*")):
        name = p.relative_to(release).as_posix()
        if name == "inventory.json":
            continue
        if p.is_symlink():
            result[name] = ["symlink", os.readlink(p)]
        elif p.is_file():
            result[name] = ["file", digest(p), stat.S_IMODE(p.stat().st_mode)]
        elif p.is_dir():
            result[name] = ["dir"]
        else:
            fail(f"Unrecognized installation artifact: {p}")
    return result


def verify_inventory(release, saved_hash):
    path = release / "inventory.json"
    owner_file(path)
    if digest(path) != saved_hash:
        fail(f"Installation inventory modified: {release}")
    expected = json.loads(path.read_text())
    if inventory(release) != expected:
        fail(f"Foreign changes inside release; refusing deletion: {release}")


def atomic_write(path, data, mode=0o600):
    secure_dir(path.parent)
    no_link(path)
    fd, temp = tempfile.mkstemp(prefix=".stable-first-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(temp, mode)
        os.replace(temp, path)
    finally:
        if os.path.lexists(temp):
            os.unlink(temp)


def replace_active(name):
    temp = BASE / (".current-" + uuid.uuid4().hex)
    os.symlink("releases/" + name, temp)
    try:
        os.replace(temp, CURRENT)
    finally:
        if temp.is_symlink():
            temp.unlink()


def install():
    manifest = verify_source()
    existing = read_state()
    check_state(existing)
    launch, desktop = expected_shortcuts()
    if existing and existing["source_sha"] == SOURCE_SHA:
        print("Already installed; no files or services changed")
        return
    if BASE.exists() and not existing:
        no_link(BASE)
        if any(BASE.iterdir()):
            fail("Existing foreign data in install base; refusing takeover")
    secure_dir(RELEASES)
    stage = RELEASES / (".stage-" + uuid.uuid4().hex)
    name = f"{VERSION}-{SOURCE_SHA[:8]}-{uuid.uuid4().hex[:12]}"
    stage.mkdir(mode=0o700)
    try:
        tree = stage / "source"
        tree.mkdir()
        for entry in manifest["files"]:
            rel = safe_rel(entry["path"])
            target = tree / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SOURCE / rel, target, follow_symlinks=False)
        # Distinct venv: pipx app, service units and system Python untouched.
        subprocess.run([sys.executable, "-m", "venv", str(stage / "venv")], check=True)
        pip = stage / "venv" / "bin" / "python"
        subprocess.run([str(pip), "-m", "pip", "--isolated", "install",
                        "--disable-pip-version-check", "--no-input", "--only-binary=:all:",
                        *PINNED_QT], check=True)
        subprocess.run([str(pip), "-m", "pip", "--isolated", "install",
                        "--disable-pip-version-check", "--no-input", "--no-deps",
                        str(tree)], check=True)
        subprocess.run([str(pip), "-m", "pip", "freeze"],
                       check=True, stdout=(stage / "dependencies.txt").open("w"))
        shutil.copy2(Path(__file__).with_name("safe_entry.py"), stage / "safe_entry.py")
        meta = {"owner": OWNER, "source_sha": SOURCE_SHA, "release": name}
        (stage / "installed.json").write_text(json.dumps(meta, sort_keys=True))
        snapshot = inventory(stage)
        (stage / "inventory.json").write_text(json.dumps(snapshot, sort_keys=True))
        inv_hash = digest(stage / "inventory.json")
        final = RELEASES / name
        if final.exists() or final.is_symlink():
            fail("Refusing to replace existing release")
        stage.rename(final)
    except BaseException:
        if stage.is_dir() and not stage.is_symlink():
            shutil.rmtree(stage)
        raise
    versions = dict(existing["releases"]) if existing else {}
    versions[name] = {"inventory_sha256": inv_hash}
    prior = existing["active"] if existing else None
    newstate = {"owner": OWNER, "source_sha": SOURCE_SHA,
                "active": name, "previous": prior, "releases": versions,
                "launcher_sha256": hashlib.sha256(launch).hexdigest(),
                "desktop_sha256": hashlib.sha256(desktop).hexdigest()}
    # Fail closed on conflicts before touching any existing entry point.
    if not existing and any(p.exists() or p.is_symlink() for p in (LAUNCHER, DESKTOP, CURRENT, STATE)):
        fail("Existing shortcut or release link; installation left isolated for review")
    atomic_write(LAUNCHER, launch, 0o700)
    atomic_write(DESKTOP, desktop, 0o600)
    replace_active(name)
    atomic_write(STATE, (json.dumps(newstate, indent=2) + "\n").encode())
    print(f"Installed only {LAUNCHER}; receiver controls remain disabled")


def rollback():
    state = read_state()
    if state is None:
        fail("No Stable First installation to roll back")
    check_state(state)
    prev = state.get("previous")
    if not prev or prev not in state["releases"]:
        fail("No previous Stable First release available")
    old = state["active"]
    state["active"], state["previous"] = prev, old
    replace_active(prev)
    atomic_write(STATE, (json.dumps(state, indent=2) + "\n").encode())
    print("Rolled back Stable First alias only; no services touched")


def uninstall():
    state = read_state()
    if state is None:
        check_state(None)
        print("Stable First is not installed")
        return
    check_state(state, full_inventory=True)
    for item in (LAUNCHER, DESKTOP, CURRENT):
        if item.is_symlink() and item != CURRENT:
            fail(f"Foreign shortcut symlink: {item}")
    for item in (LAUNCHER, DESKTOP, CURRENT):
        item.unlink()
    for name in state["releases"]:
        shutil.rmtree(RELEASES / name)
    STATE.unlink()
    # Preserve all user configuration, cache, recordings and data directories.
    print("Removed verified installer-owned artifacts only; user data preserved")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    for flag in ("dry-run", "check", "install", "rollback", "uninstall"):
        group.add_argument("--" + flag, action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        verify_source()
        check_state(read_state())
        print(f"DRY RUN: would install {SOURCE_SHA} into {BASE}; no actions taken")
    elif args.check:
        manifest = verify_source()
        state = read_state()
        check_state(state)
        print(f"CHECK OK: {manifest['files_count']} frozen files; installed={state is not None}")
    elif args.install:
        install()
    elif args.rollback:
        rollback()
    else:
        uninstall()


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, KeyError, subprocess.CalledProcessError) as exc:
        print(f"Stable First HOLD: {exc}", file=sys.stderr)
        raise SystemExit(2)
