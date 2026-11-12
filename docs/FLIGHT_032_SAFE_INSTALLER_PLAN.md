# TIHULU Flight Radar 0.3.2.dev4 — isolated installation plan

**State: READ-ONLY PREFLIGHT ONLY, installation and release HOLD.**

The original working Pop!_OS app is `tihulu-flight-radar 0.3.2.dev4` from `950f8278a625ce13a9a3c7e21bf9bf76d4b5888e`, pinned at `snapshot/installed-v0.3.2.dev4-950f8278` and preserved in Draft PR #23. Legacy v0.3.1 is separately preserved under Draft PR #22. Both are immutable preservation baselines, not targets for modifications.

This design uses the **security-patched** `f923d8c1fc3333052ca3865fe68e2e9d39a73791` source from Draft PR #25 as a **separate preview candidate**. It is not byte-identical to the owner's installed original and must never be relabeled as such.

## Phase A: non-mutating preflight (implemented)

```sh
python3 tools/flight_safe_preflight.py
python3 tools/flight_safe_preflight.py --json
```

These commands inspect metadata of fixed path names only. They do not read QSettings, pipx venv contents, privileged sudoers file contents, private recordings or receiver data. They never write, install, update, chmod, delete, stop services, access USB or elevate privileges.

A future safe-preview target must be **different** from every installed application:
- Data/release root: `~/.local/share/tihulu-flight-032-safe` (no existing app data paths).
- Launcher: `~/.local/bin/tihulu-flight-032-safe`.
- Desktop shortcut: `~/.local/share/applications/tihulu-flight-032-safe.desktop`.
- Isolated QSettings/config: `~/.config/tihulu-flight-032-safe`.
- Isolated Qt/browser cache: `~/.cache/tihulu-flight-032-safe`.
- Isolated XDG data: `~/.local/share/tihulu-flight-032-safe/user-data`.
- No access to `~/.local/share/pipx/venvs/tihulu-flight-radar`, `~/.local/bin/tihulu-flight-radar`, old Stable First `0.3.1` release, or shared `readsb/tar1090` services.

Owner-reported real-machine evidence on 12 November 2026 confirms `/etc/sudoers.d/tihulu-flight-radar` exists and grants NOPASSWD systemctl start/stop/enable/disable. **Preflight deliberately marks that as HOLD.** It never changes, removes, chmods or reads this sudoers file. A rollback-capable policy-revocation action would be a separate explicitly approved procedure.

## Phase B: transactional installer (NOT YET IMPLEMENTED)

Before any installation, implement and separately QA: exact Git SHA and SHA-256 file manifest verification, source/package lock and artifact hash audit, isolated Python 3.12.3 venv, deterministic owned paths, staged offline-safe verification, collision refusal, owned inventory, install/rollback/uninstall transactions, no shared hardware controls (passive by default), atomic launcher switching, safe cleanup of only installer-owned files, and explicit user approval before use.

Never use historical `scripts/install-linux.sh` or `scripts/popos-version-switch.sh`: they contain overwriting `pipx install --force` behavior, sudo apt modifications and potential legacy package removal, and are not safe side-by-side installation methods.

## Phase C: operational sign-off (NOT DONE)

Validate offline map assets, Qt on Pop!_OS 24.04 COSMIC/NVIDIA, original installed-wheel parity, persistent QSettings isolation, tar1090 availability, SDR access arbitration across Media Center/Flight Radar/Satellite Center, rollback, reinstall, uninstall and last-resort recovery on a **disposable account/device first**. No simulation or CI can substitute for real hardware QA.

**No PR merge, release, installer execution or live receiver service operation is authorized.**

**Non-searchable sudoers directories:** A normal user may not be permitted to stat `/etc/sudoers.d/tihulu-flight-radar`. Preflight reports `sudoers_policy_present: null` and a HOLD blocker, **not** an assumed absence. The GitHub CI runner exercises this fail-closed outcome, validates JSON and checks the working tree remains untouched.
