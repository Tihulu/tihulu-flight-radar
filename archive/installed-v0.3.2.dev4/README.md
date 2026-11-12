# Installed Flight Radar v0.3.2.dev4 — versioned source snapshot

> **Preserved Git source, not a public stable release and not a byte-for-byte backup of an installed pipx environment.** Installation/release stays HOLD until separate QA and owner authorization.

## Exact provenance

On 12 November 2026 the owner read the existing Pop!_OS pipx installation metadata. The installed distribution was `tihulu-flight-radar 0.3.2.dev4` (Python 3.12.3) with `direct_url.json` pointing to Git revision `950f8278a625ce13a9a3c7e21bf9bf76d4b5888e` on `fix/native-radar-pairing-install-ui-2026-11-08`.

GitHub independently resolves the requested revision to the same commit; its exact Git tree is `0aa376600310576bb1de3c0c557e774c3233b6c5`. Its `pyproject.toml` declares `version = "0.3.2.dev4"`.

- Frozen checkout branch (points **directly** at the installed-source commit): [`snapshot/installed-v0.3.2.dev4-950f8278`](https://github.com/Tihulu/tihulu-flight-radar/tree/snapshot/installed-v0.3.2.dev4-950f8278)
- `source/` — **complete copy of all 120 Git-tracked source blobs**, including map assets, Python application, Qt UI, tests, scripts and docs, with original path structure and Git executable modes, and an **identical Git tree object**.
- `manifest/provenance.json` — path, byte size, Git blob SHA-1, Git mode for each of 120 files. Both the commit and tree are pinned, not dynamically copied from `main`.
- `tests/verify_snapshot.py` — read-only verification of the exact Git subtree, source blob hashes and file inventory.

The owner subsequently provided the **entire observed output** of `pip list --format=freeze` from that pipx environment on 12 November 2026: **8 Python distributions**, including `pip`, `PySide6`, `PySide6_Addons`, `PySide6_Essentials`, `PySide6_Pdf`, `PySide6_WebEngine`, `shiboken6`, and `tihulu-flight-radar`. Preserve it as read-only evidence under [`manifest/observed-pip-freeze.txt`](manifest/observed-pip-freeze.txt) and [`manifest/observed-python-environment.json`](manifest/observed-python-environment.json); the verification script cross-checks both files. This is **not an installable lockfile or hash-verified reproduction**: the exact local wheel/archive hashes, platform-native shared-library versions, globally installed packages, separate tar1090 cache, private user data and installed venv contents were not collected or independently inspected. Do not run `pip install -r` against this observation.

## Version distinction

| Preserved object | Version | Exact Git source |
| --- | --- | --- |
| Legacy Stable First Draft PR #22 | 0.3.1 | `67280cd84feb89faec6a80f5fe2a55ce5f7b89e6` |
| **This installed-source snapshot** | **0.3.2.dev4** | **`950f8278a625ce13a9a3c7e21bf9bf76d4b5888e`** |
| General preview branch | 0.3.2.dev4 | **not assumed identical** |

Version strings are not sufficient identifiers. The user's currently installed `0.3.2.dev4` differs from other branches carrying the same package version.

## Verify without installing or launching

```sh
python3 archive/installed-v0.3.2.dev4/tests/verify_snapshot.py
```

This checks archive bytes without invoking readsb, sudo, systemctl, pipx, Qt or any SDR device.

## Safe source-only retrieval (NOT an installation)

The source can also be inspected directly at the exact original commit:

```sh
git clone --no-checkout https://github.com/Tihulu/tihulu-flight-radar.git flight-source-review
git -C flight-source-review checkout --detach 950f8278a625ce13a9a3c7e21bf9bf76d4b5888e
git -C flight-source-review rev-parse HEAD
```

Do **not** run original `scripts/install-linux.sh` or `scripts/popos-version-switch.sh` to restore this version: both are preserved as historical source and may replace the existing pipx application, change packages or sudoers rules.

## Safety and release gate

- No machine access or machine installation occurred to create this GitHub snapshot.
- No process, `readsb`, `tar1090`, SDR or other TIHULU app was touched.
- The Qt app and receiver control features are **historically preserved, not certified safe for simultaneous execution**.
- Real side-by-side installation, rollback, Pop!_OS COSMIC GUI, hardware receiver ownership, external provider licensing and full tar1090 runtime resources need independent testing.
- `main`, `gh-pages`, `legacy/v0.3.1`, PR #22 and PRs #15–#21 remain untouched.
- Do not merge, tag a public release, deploy, overwrite pipx, or publish a one-line installer without explicit owner approval.

**Source archive: preservation GO. Installation, side-by-side hardware control and public release: HOLD.**
