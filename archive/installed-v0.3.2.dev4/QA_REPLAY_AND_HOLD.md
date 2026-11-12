# Installed v0.3.2.dev4 — source replay and device-ownership QA

**Snapshot ref:** `950f8278a625ce13a9a3c7e21bf9bf76d4b5888e` (Git tree `0aa376600310576bb1de3c0c557e774c3233b6c5`).
**Scope:** source replay in disposable CI, not proof of a byte-identical installed wheel or Pop!_OS physical hardware.

## Current source & owner-reported Python environment

- Archived original Git source: 120/120 files, all original bytes, no patches to `source/`.
- Owner-reported 2026-11-12 Pop!_OS 24.04 / Python 3.12.3 / 8 pinned Python distribution versions, recorded in `manifest/observed-python-environment.json` and `manifest/observed-pip-freeze.txt`.
- The new CI replay starts with a **fresh isolated venv**, uses Python **3.12.3**, installs the owner-observed exact package versions (from ordinary package indexes, without artifact hashes), installs the **archived** 0.3.2.dev4 package with `--no-deps`, then checks all eight package versions before adding `pytest`.
- After pin checking, CI runs upstream Python unit tests, JavaScript tests and optional **guarded** offscreen classic Qt smoke. All run in an ephemeral GitHub runner with `HOME`, `XDG_CONFIG_HOME`, `XDG_CACHE_HOME` and `XDG_DATA_HOME` separated. No original installer or version switcher is invoked.
- `tests/verify_rebuilt_environment.py` is **CI-only** and asserts it runs within a virtual environment, on Python 3.12.3 and against the recorded inventory.
- `tests/guarded_classic_qt_smoke.py` requires explicit GitHub CI, offscreen Qt and ephemeral HOME; blocks receiver `start`, `stop`, `restart`, `service_action` before loading original GUI script.
- CI success only means version-pinned packages can be **retrieved and exercised** against frozen source on test Linux. It **does not** mean wheel builds or binary hashes are identical to the owner's actual installation.

## Device ownership / coexistence — confirmed HOLD

**Finding:** In frozen source `tihulu_flight_radar/control.py`, receiver close with `release_local_service=True` can stop a shared `readsb` service; the original `tests/test_control.py::test_shared_service_stops_when_exit_release_enabled` explicitly expects a `stop` call even without proving the application owns that service. The native UI in `tihulu_flight_radar/native.py` defaults `release_sdr_on_exit=True`. No app-exit ownership fix has been made to this historical snapshot; such a change must be **outside** the frozen source and independently reviewed.

**Also:** original `scripts/install-linux.sh` and `scripts/popos-version-switch.sh` can replace the shared `pipx` application (`pipx install --force`); they are preserved as inert evidence and must not be executed during source replay.

**Also:** original native app reads and writes `QSettings("Tihulu", "FlightRadar")`, so running a naive side-by-side copy can share private preferences unless launch environment is isolated.

## Independent review gates

| Question | Status |
| --- | --- |
| Correct original Git commit and source tree | GO |
| Preserve all tracked files and unchanged byte content | GO |
| Owner-reported 8-version Python package inventory | GO (observed, not independently fetched) |
| Exact Python version and wheel resolution in disposable runner | WAIT FOR CI |
| Original source unit/JS tests, guarded GUI smoke | WAIT FOR CI |
| Exact hashes of wheels installed on owner's PC | HOLD — never collected |
| Original generated full tar1090 cache / maps / offline assets | HOLD — not archived |
| Real Pop!_OS 24.04 + COSMIC + RTL-SDR and Hauppauge ownership | HOLD — not tested |
| Multiple installations, safe uninstaller, 0.3.1 coexistence | HOLD — no safe 0.3.2 side-by-side installer |
| Release tag, public installer, any production deployment | HOLD — owner approval and QA required |

**No GitHub Release, merge, pipx overwrite, readsb restart, RF device access or workstation change is authorized.**
