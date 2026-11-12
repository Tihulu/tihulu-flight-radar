# Flight Radar 0.3.2.dev4 — Phase B transaction laboratory (CI only)

**NOT A USER INSTALLER. No production install CLI is provided.** The only CLI command is `python3 tools/flight_transaction_lab.py --plan`, which writes nothing and requires no privileges.

## Purpose

Provide testable, versioned building blocks for a future **distinct-name** side-by-side installation of the security candidate, while preserving the original user's pipx 0.3.2.dev4 installation, v0.3.1 archive, settings, old sudoers and readsb/tar1090 services.

`TransactionLab` is gated to GitHub Actions with `CI=true` and an exact `RUNNER_TEMP/flight-transaction-lab/<fixture>` root. It only works on arbitrary small test bytes and **never invokes pip, Python package installers, sudo, systemctl, Qt or SDR processes**. The laboratory is not a model of a byte-exact installed wheel.

Phase-B safeguards tested:
- Non-overwrite versioned fixture staging, hash/ownership/size validation, collision refusal.
- Atomic `current` link replacement using same-directory symlink + rename.
- Write-ahead journal and explicit recovery after injected failure at journal, pointer and state transitions.
- Two preserved release payloads through switching, rollback and deactivation; no release deletion.
- Refusal of symlinked roots, corrupted fixture, wrong owner and a non-disposable path.
- Verify fake installed pipx owner file remains untouched.

**Remaining HOLD:** independent concurrency and symlink-race review, actual application package/venv/wheel-hash locking, reliable installer rollback/uninstall when deletion fails, service lifetime policy and USB exclusive ownership, real Pop!_OS COSMIC QA, licensing, binary artifact signing, package-native launch behavior. Old `/etc/sudoers.d/tihulu-flight-radar` rule confirmed by owner remains untouched and requires separate authorized review.

The history of original sources is unchanged: PR #22 0.3.1, PR #23 original 0.3.2.dev4 and PR #25 security candidate. This stacked PR must stay Draft. No merge or release without separate independent validation and the owner's explicit approval.
