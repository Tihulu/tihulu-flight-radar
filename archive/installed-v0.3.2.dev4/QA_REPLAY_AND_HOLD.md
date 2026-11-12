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
| Exact Python 3.12.3 and 8-version inventory resolution in disposable runner | **PASS**, run 43191456766, no wheel hashes |
| Original Python tests | **PASS**, run 43191456766, disposable runner |
| Original JavaScript regressions (all tracked tests) | **HOLD: 175/179 passed, 4 failed** |
| Guarded classic Qt GUI smoke | **PASS** run 43192017994, Qt offscreen, receiver management disabled |
| Exact hashes of wheels installed on owner's PC | HOLD — never collected |
| Original generated full tar1090 cache / maps / offline assets | HOLD — not archived |
| Real Pop!_OS 24.04 + COSMIC + RTL-SDR and Hauppauge ownership | HOLD — not tested |
| Multiple installations, safe uninstaller, 0.3.1 coexistence | HOLD — no safe 0.3.2 side-by-side installer |
| Release tag, public installer, any production deployment | HOLD — owner approval and QA required |

**No GitHub Release, merge, pipx overwrite, readsb restart, RF device access or workstation change is authorized.**

## Independent CI replay finding (2026-11-12)

At Draft PR #23 head `72b66c8d0c8eb8dd301803961bf6b7b53509df55`, [snapshot replay run 43191456766](https://github.com/Tihulu/tihulu-flight-radar/actions/runs/43191456766) successfully provisioned the owner-observed **Python 3.12.3 and 8 installed distributions**, imported Qt WebEngine and radar module from archived source, and passed frozen Python tests. The subsequent **full original JavaScript test run failed 4 of 179 tests**. These are baseline failures in the original commit; do not rewrite the archived source or exclude failing tests to manufacture a pass.

Failing original tests:
1. `rf_five_layer_portal.test.cjs`: `two independent valid model rings and a weighted center point coexist` — expected 2 rings, actual 0.
2. `rf_model_popup_offline.test.cjs`: `LIVE and BEST cards keep independent measured-unknown metadata` — `window is not defined`.
3. `rf_model_popup_offline.test.cjs`: `model marker respects visibility and right card has details` — expected expression absent from input.
4. `rf_null_region_desktop_regression.test.cjs` — historical test has a JavaScript syntax error near line 106.

The original source CI's curated JS command did **not** exercise these three failing test files. A green generic preview CI does not override the full-archive regression failure. The replay workflow now records JS failure but continues guarded Qt smoke to gather independent GUI evidence, and the explicit final QA gate **fails the job** if any JS or Qt smoke failure persists.

**Functional parity and release remain HOLD.** No physical malfunction on the owner's Pop!_OS desktop was claimed.

## Guarded GUI evidence (12 November 2026)

At [source replay run 43192017994](https://github.com/Tihulu/tihulu-flight-radar/actions/runs/43192017994), the isolated pinned environment and original Python tests passed, **all 179 original JS tests ran (175 PASS, 4 FAIL)**, and the isolated **classic Qt GUI smoke PASS** after forcing all receiver control methods to fail-closed or no-op in the CI process. The final CI job reports **FAIL by design** because the untouched original JavaScript regressions still fail. That is a correct **functional parity HOLD**, not a failure to preserve the Git source.

This smoke does not cover native Qt WebEngine's complete interactive flows, real Pop!_OS COSMIC environment, user-specific configuration, RTL-SDR, readsb/tar1090, or hardware parity. Neither the user's workstation nor a shared receiver was touched.

## Native embedded Qt WebEngine smoke (added for next CI run)

The CI-only `tests/guarded_native_qt_smoke.py` explicitly requires GitHub Actions, Python venv test context, `QT_QPA_PLATFORM=offscreen`, isolated HOME and isolated XDG paths. It installs a fail-closed process-local receiver control patch before importing the frozen original native window, forces auto-start false in temporary QSettings, constructs `NativeRadarWindow`, checks its loopback browser URL and private bridge thread, and closes it. The test is **not** physical SDR, GUI interaction, hardware decoding, external network completeness, private settings compatibility, or an authorized install.

The final source-parity HOLD gate will also fail if native Qt smoke does not pass. JavaScript regressions remain a separate unmodified HOLD irrespective of the native result.
