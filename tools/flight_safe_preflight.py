#!/usr/bin/env python3
"""Flight Radar 0.3.2 safe-preview preflight: read-only, no installer actions.

This probe never imports the application, starts/stops readsb, writes settings,
changes files, invokes sudo/pipx/systemctl, or creates output files.
It is a prerequisite for *future* isolated installation work, not an installer.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path

SOURCE_VERSION = "0.3.2.dev4"
ORIGINAL_INSTALLED_COMMIT = "950f8278a625ce13a9a3c7e21bf9bf76d4b5888e"
REVIEWED_SECURITY_COMMIT = "f923d8c1fc3333052ca3865fe68e2e9d39a73791"
SAFE_NAME = "tihulu-flight-032-safe"
OLD_SUDOERS = Path("/etc/sudoers.d/tihulu-flight-radar")


def _exists(path: Path) -> bool:
    # lexists semantics: a broken symlink still counts as occupied.
    return path.is_symlink() or path.exists()


def _kind(path: Path) -> str:
    if path.is_symlink():
        return "symlink"
    if path.is_dir():
        return "directory"
    if path.is_file():
        return "file"
    if _exists(path):
        return "other"
    return "absent"


def _chain_under_home(home: Path, target: Path) -> list[Path]:
    if target != home and home not in target.parents:
        raise ValueError(f"Path outside home: {target}")
    chain = [target]
    while chain[0] != home:
        chain.insert(0, chain[0].parent)
    return chain


def check(home: Path, old_sudoers: Path = OLD_SUDOERS) -> dict:
    """Inspect only metadata of fixed names. Never read private configuration."""
    if not home.is_absolute():
        raise ValueError("Home must be an absolute path")
    local = home / ".local"
    base = local / "share" / SAFE_NAME
    target = local / "bin" / SAFE_NAME
    desktop = local / "share" / "applications" / (SAFE_NAME + ".desktop")
    xdg = {
        "config": home / ".config" / SAFE_NAME,
        "cache": home / ".cache" / SAFE_NAME,
        "data": base / "user-data",
    }
    managed = {"base": base, "launcher": target, "desktop": desktop}
    protected = {
        "installed_pipx": local / "share" / "pipx" / "venvs" / "tihulu-flight-radar",
        "installed_launcher": local / "bin" / "tihulu-flight-radar",
        "installed_classic": local / "bin" / "tihulu-flight-radar-classic",
        "installed_bridge": local / "bin" / "tihulu-flight-bridge",
        "old_stable_first": local / "share" / "tihulu-flight-stable-first",
    }
    blockers: list[str] = []
    warnings: list[str] = []
    managed_view = {key: {"path": str(path), "type": _kind(path)}
                    for key, path in managed.items()}
    protected_view = {key: {"present": _exists(path), "type": _kind(path)}
                      for key, path in protected.items()}

    for key, path in managed.items():
        if _exists(path):
            blockers.append(f"Managed {key} name already occupied; never overwrite: {path}")
    # Any prospective parent path must be a regular, trusted directory.
    parents = set()
    for path in [*managed.values(), *xdg.values()]:
        parents.update(_chain_under_home(home, path)[:-1])
    for path in sorted(parents, key=lambda p: (len(p.parts), str(p))):
        if path.is_symlink():
            blockers.append(f"Symlink ancestor: {path}")
            continue
        if not _exists(path):
            continue
        if not path.is_dir():
            blockers.append(f"Non-directory ancestor: {path}")
            continue
        if os.name == "posix":
            s = path.stat()
            if s.st_uid != os.getuid():
                blockers.append(f"Foreign-owned ancestor: {path}")
            if stat.S_IMODE(s.st_mode) & 0o022:
                blockers.append(f"Group/other-writable ancestor: {path}")

    if _exists(old_sudoers):
        # Metadata only; intentionally do not read privileged file contents.
        blockers.append(
            "Historical sudoers policy exists; review and revoke only with "
            "separate explicit approval, never automatically."
        )
    if os.name != "posix":
        warnings.append("Installation targets Linux only; other OS results are advisory.")
    warnings.append(
        "This is read-only preflight, not a byte-identical installed wheel "
        "backup or a working side-by-side install."
    )
    warnings.append(
        "Direct RTL-SDR USB ownership and concurrent readsb/tar1090 service "
        "safety require physical-device testing; release remains HOLD."
    )

    return {
        "schema": 1,
        "candidate": SAFE_NAME,
        "original_installed_source_commit": ORIGINAL_INSTALLED_COMMIT,
        "security_candidate_commit": REVIEWED_SECURITY_COMMIT,
        "package_version": SOURCE_VERSION,
        "check_mode": "read-only-no-side-effects",
        "ready_for_installer_qa": not blockers,
        "ready_for_installation": False,
        "managed_names": managed_view,
        "existing_protected_names": protected_view,
        "isolated_xdg_targets": {key: str(path) for key, path in xdg.items()},
        "sudoers_policy_present": _exists(old_sudoers),
        "blockers": blockers,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print machine-readable read-only assessment")
    args = parser.parse_args(argv)
    result = check(Path.home())
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"Flight Radar {SOURCE_VERSION} — READ-ONLY side-by-side preflight")
        print(f"Original source: {ORIGINAL_INSTALLED_COMMIT}")
        print(f"Safe candidate:  {REVIEWED_SECURITY_COMMIT}")
        print(f"Proposed name:   {SAFE_NAME}")
        print(f"Current pipx protected: {result['existing_protected_names']['installed_pipx']['present']}")
        print(f"Historic sudoers present: {result['sudoers_policy_present']}")
        print(f"Blockers: {len(result['blockers'])}")
        for reason in result["blockers"]:
            print("HOLD: " + reason)
        print("Real installation and hardware authorization: HOLD (always)")
    return 2 if result["blockers"] else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"HOLD: preflight could not complete safely: {exc}", file=sys.stderr)
        raise SystemExit(2)
