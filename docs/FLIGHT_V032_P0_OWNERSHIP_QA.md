# Flight Radar 0.3.2.dev4 experimental receiver safety and JS QA

**Draft development only; no merge, install, public release, or workstation changes.**

Baseline: exact machine-observed source 950f8278a625ce13a9a3c7e21bf9bf76d4b5888e, Python 3.12.3. New isolated fix branch differs from frozen version and must not be confused with it.
Frozen refs snapshot/installed-v0.3.2.dev4-950f8278 and legacy/v0.3.1, archives in PRs #22 and #23, and main are not modified.

## P0 shared systemd service

Original close(release_local_service=True) automatically stopped systemd readsb/tar1090 when active, even when another TIHULU app depended on it.
Development fix never stops shared systemd units on GUI exit, even if it started them; direct app-owned child processes still release.
Preexisting active shared unit is read-only; manual stop/restart through this controller requires that this controller started the unit. Changing receiver mode forfeits claimed ownership. Module-level stop requires explicit ownership assertion.
Native/classic GUIs replace the unsafe auto-release setting with a non-interactive safety explanation. Historical saved preference is left untouched.

**Residual HOLD:** in-process _service_started_by_app is not cross-process ownership proof. A manual stop could still affect other consumers after this app started shared readsb. Independent QA must validate concurrent access, systemd invocation identity or a stronger shared-service stop ban before hardware GO.

## Four historical JS test failures

Fixes in the development branch are corrections to outdated test harnesses, not fabrication of RF observations:
- Actually invoke paintRfComparisons() before asserting ring drawings.
- Provide a mocked browser window.TihuluRFV2.display() for isolated LIVE/BEST card function tests.
- Replace broken old regex with literal guard checks for independent LIVE/BEST pins.
- Repair invalid newline and simulate the current portaled Circles menu and pointerdown/Escape/Done.
Generic workflow now runs all tests/*.test.cjs, not the old curated subset that excluded 3 files.

## Gate

CI can verify Python, JS and Qt in a disposable environment. No claims about real Pop!_OS COSMIC, installed wheel hashes, hardware SDR, readsb/tar1090 coexistence, installer rollback or release. They remain HOLD.
