# Flight Radar v0.3.2.dev4 — independent shared systemd security review

**Baseline:** Draft PR #24 HEAD `c9a9c32868c7c9606fbd233153d31c19c9014c81`, itself stacked on user's exact installed Git source `950f8278a625ce13a9a3c7e21bf9bf76d4b5888e`.

**Scope:** additional review PR stacked on #24. This is not the frozen source, not a production release, not a user-device installation, and not an audit of the user's private system.

## Findings

**SEC-FLIGHT-P0-01 — cross-app shared readsb can still be stopped.**
PR #24 disabled GUI-exit stopping but allowed `service_action("stop", ownership_confirmed=True)` using a caller-controlled boolean, and `ReceiverController.stop/restart` trusted `_service_started_by_app`. A receiver started by one app may have acquired consumers since startup. A process-local flag is not proof of exclusive ownership. *Severity: P0 for coexistence; confirmed by code inspection.*

**SEC-FLIGHT-P0-02 — shared systemd lifecycle privilege granted by installer.**
`scripts/install-linux.sh` still wrote a NOPASSWD sudoers rule permitting `systemctl start/stop/enable/disable readsb.service tar1090.service`. This is contrary to the desired read-only shared-service contract. *Severity: P0 for new installs; confirmed by source.* The script also force-installs over existing pipx and can remove historic application packages; it is **not approved for use on the owner's computer**.

**SEC-FLIGHT-P1-03 — cross-app direct SDR start race.**
Direct readsb checks systemd active state before launch, but there is no shared hardware lock or test proving another SDR module cannot claim the USB device between check and process launch. **HOLD** pending a real multi-app exclusive lease and hardware QA.

## Safeguards in this stacked review branch

1. `service_action` always rejects start, stop, enable and disable for shared systemd units before invoking sudo or subprocess, even with a forged `ownership_confirmed=True`.
2. `ReceiverController.start()` in Linux-services mode remains read-only: reports an active preexisting service, and refuses to start an inactive one. `stop()/restart()` always refuse for shared systemd, regardless of a spoofed `_service_started_by_app`.
3. Direct readsb mode continues to own only its own `Popen` subprocess; its stop/restart/close methods are not removed. Remote JSON remains read-only.
4. Classic GUI disables start/stop/restart and boot toggles in shared Linux-service mode; native Qt disables the auto-start toggle in shared mode. Bridge advertises control only in Direct readsb mode. All control entrypoints fail closed server-side regardless of UI state.
5. The installer no longer writes a sudoers rule or invokes `visudo` for service privilege. **It does not delete or chmod any preexisting `/etc/sudoers.d/tihulu-flight-radar` file**, and does not inspect the owner's computer. A preexisting historic rule could still be present and requires separate explicit owner-authorized review.
6. Negative tests attempt to bypass read-only protections with forged ownership, all four service actions, running/inactive states, legacy release flags and bridge controls. CI runs full Python and all JavaScript regressions on disposable runners.

## Open release blockers

- **HOLD:** no evidence that existing privileged policy on user's Pop!_OS PC has been inspected or safely removed; do not modify automatically.
- **HOLD:** no full installed-wheel byte hash attestation, full pipx/Qt native-library reproducibility, or original tar1090 cache completeness.
- **HOLD:** no shared hardware lock, cross-process start race elimination or real NooElec SDR / readsb / Media Center / Pop!_OS COSMIC coexistence tests.
- **HOLD:** historical installer still performs `pipx install --force`, privileged apt changes and legacy package removals; must not be used for side-by-side archive install without independent installer hardening.
- **HOLD:** 0.3.1 and 0.3.2.dev4 archives and existing PRs #22/#23 are never updated or repointed.
- **HOLD:** no merge, public release, installer publication, workstation install or service operation without owner approval.

**Scoped code-level shared-systemd safety can be GO only after exact-HEAD CI and independent tests are verified. Full operational security and release remain HOLD.**
