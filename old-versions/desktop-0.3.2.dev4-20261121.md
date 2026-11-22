# TIHULU FLIGHT RADAR — DESKTOP 0.3.2.dev4 FROZEN RECORD (installed copy)

Frozen: 2026-11-13 (first session backup) and re-verified 2026-11-20/21.

## Identity
- Version: 0.3.2.dev4 · Python 3.12.3 · PySide6 6.12.0 / PySide6-Addons 6.12.0 /
  PySide6-Essentials 6.12.0 / PySide6-Pdf 6.12.0.140 / PySide6-WebEngine 6.12.0.140
- Installed via pipx at: /home/horseman/.local/share/pipx/venvs/tihulu-flight-radar
- Console scripts: tihulu-flight-radar, tihulu-flight-radar-classic, tihulu-flight-bridge
  (symlinks in ~/.local/bin → pipx venv)
- User data (untouched, verified): ~/.local/share/tihulu-flight-radar
  (rf-history.sqlite3 — PRAGMA integrity_check ok; tar1090 tree)

## Provenance
- Source commit: 950f8278a625ce13a9a3c7e21bf9bf76d4b5888e
- Source branch: fix/native-radar-pairing-install-ui-2026-11-08 (PR #13) — CONFIRMED on remote
  (git ls-remote 2026-11-21: 950f8278a625ce13). Protected copy branch recommended:
  old-versions/desktop-0.3.2.dev4-20261121 @ 950f8278.

## Integrity evidence (this session, live system, read-only)
- 41/41 installed files byte-identical to the private Nov-13 backup manifest
  (owner-only, 700/600, at ~/.local/opt/tihulu-flight-radar-backup-v0.3.2.dev4-20261113/).
- SQLite integrity ok; symlinks intact; no config change since 2026-11-19.

## Reinstall / restore recipe (disposable environment, from this commit)
```
python3 -m venv .venv && .venv/bin/python -m pip install \
  "git+https://github.com/Tihulu/tihulu-flight-radar.git@950f8278a625ce13a9a3c7e21bf9bf76d4b5888e"
```
Then verify: pip show tihulu-flight-radar (0.3.2.dev4) + the three console scripts exist.
The 0.3.1 rollback route stays: legacy/v0.3.1 @ 67280cd84feb89faec6a80f5fe2a55ce5f7b89e6.
