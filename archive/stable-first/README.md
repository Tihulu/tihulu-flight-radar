# TIHULU Flight Radar — Stable First (archived source; HOLD)

**Not a certified release. Do not install on the owner's working machine.**
This is a review-only preservation of the *user-confirmed* historical v0.3.1
source. It is **not** proof that the owner's presently installed binary has
the exact same build or runtime dependencies.

## Immutable provenance

- Repository: `Tihulu/tihulu-flight-radar`
- Legacy branch: `legacy/v0.3.1` (verified head)
- Source commit: `67280cd84feb89faec6a80f5fe2a55ce5f7b89e6`
- Exact Git tree: `a916732793c405e73f5de996b528ac96437222cd`
- The `source/` directory contains all 64 Git-tracked blobs from that tree
  with their original executable bits and hierarchy. No changes to the blobs.
- `manifest/provenance.json` records every path, mode, byte size, Git blob
  SHA-1 and independent SHA-256. Generated artifacts, untracked dependencies,
  local settings, recordings, secrets, and SDR services are **not** archived.
- The source's own `scripts/install-linux.sh` and Debian sudoers package are
  preserved for historical fidelity **but must never be executed** by this
  installation process.

The original source still includes the Qt native radar, classic dashboard,
browser map, local bridge, radio/Internet/Hybrid source distinction, receiver
controller, aircraft details, mapping, package resources, tests, docs and
historical tar1090 integration. No features from v0.3.2.dev4 or draft PRs
#15–#21 are represented as legacy features. Generated tar1090 bundles,
OS readsb, SDR drivers and external Internet providers are separate runtime
dependencies and are **not** made available by storing this tree.

## Safety model / known legacy limitation

Original v0.3.1 starts its receiver automatically by default and its original
`native.py` can stop global `readsb` and `tar1090` services on Quit.
The original service control does not provide a defensible cross-version
exclusive owner lease. Simply launching that unchanged source against the
owner's running installation is **unsafe**.

For that reason the new `tihulu-flight-stable-first` launcher runs
`installer/safe_entry.py` with a fail-closed passive runtime shim:
**Start/Stop/Restart, sudo/systemctl service mutations and Direct readsb
acquisition are disabled**; passive reading of real pre-existing readsb
aircraft.json data and Internet/Remote JSON/map display remain available.
The unmodified historical feature implementations remain in `source/`.
The launch shim is not a tested proof of hardware parity. A future **separate,
approved safety patch and physical acceptance** is required before restoring
active receiver control.

Default: On-Demand / no background task. The launcher does not start
readsb/tar1090 or acquire the RTL-SDR. Passive Quit cannot stop them.
No pipx version switch, automatic migration, sudo, apt, systemctl mutation,
device access or third-party service installation occurs in the installer.

Qt settings are kept separate using isolated
`XDG_CONFIG_HOME`, `XDG_CACHE_HOME`, and `XDG_DATA_HOME`. The Qt source's
hardcoded organization/application string is unchanged, so this setting
isolation and the distinct desktop entry must still be tested on a real
Pop!_OS COSMIC/Qt installation.

## Reviewing and checking from the isolated archive checkout

Requires Python >=3.11. These checks **do not install or launch** anything:

```sh
python3 archive/stable-first/installer/stable_first.py --check
python3 archive/stable-first/installer/stable_first.py --dry-run
python3 -m unittest discover -s archive/stable-first/tests -v
```

**For disposable CI only, after independent review:**

```sh
python3 archive/stable-first/installer/stable_first.py --install
~/.local/bin/tihulu-flight-stable-first
python3 archive/stable-first/installer/stable_first.py --rollback
python3 archive/stable-first/installer/stable_first.py --uninstall
```

The installer creates a new venv in a versioned directory under
`~/.local/share/tihulu-flight-stable-first/releases/`, installs the pinned
Qt 6.8.3 Python distributions, and installs the exact local source into that
venv. It places **only** a distinct executable in
`~/.local/bin/tihulu-flight-stable-first` and an independent
`tihulu-flight-stable-first.desktop`. No existing
`tihulu-flight-radar` pipx package, app shortcut or Python environment is
read, updated or removed. Python transitive wheel versions and OS native
libraries are not cryptographically locked and remain a reproducibility
**blocker**; an independent lock+hash verification is required before GO.

The installer supports opt-in `--install`, `--dry-run`, `--check`,
`--rollback` (only when an earlier Stable First slot exists) and
`--uninstall`. Repeating the same pinned installation is a no-op. Install,
rollback, check, and uninstall do not invoke any receiver service commands.
Uninstall checks the recorded complete release inventory before deleting
only verified installer-owned files and refuses to delete modified/foreign
files or symlinks. It deliberately keeps private app configuration, caches,
recordings and model/data directories. A release modified by Python runtime
caches will cause deletion to **HOLD** for manual inspection, never a
force-delete. Rollback cannot invent a previous version on the first install.

## Future one-line command — NOT YET AUTHORIZED TO EXECUTE

After independent QA, replace `REVIEWED_ARCHIVE_COMMIT_SHA` with the exact
approved PR head and audit its SHA and contents. Never use `main`,
`legacy/v0.3.1` or a moving branch as the installer source.

```sh
bash -c 'set -euo pipefail; sha=REVIEWED_ARCHIVE_COMMIT_SHA; d=$(mktemp -d); trap '\''rm -rf -- "$d"'\'' EXIT; git clone --quiet https://github.com/Tihulu/tihulu-flight-radar.git "$d/repo"; git -C "$d/repo" checkout --quiet --detach "$sha"; test "$(git -C "$d/repo" rev-parse HEAD)" = "$sha"; python3 "$d/repo/archive/stable-first/installer/stable_first.py" --check; python3 "$d/repo/archive/stable-first/installer/stable_first.py" --install'
```

This is a *documentation-only proposal*, not a published approved installer.
It must **not** be run on the current owner's machine. The future pinned
command still requires independent review of transitive dependencies, file
ownership races, clean installed Qt behavior, Debian and Pop!_OS parity.

## Acceptance matrix

| Gate | Status | Evidence / blocker |
| --- | --- | --- |
| Exact historical Git source | GO (source only) | Git tree and 64 SHA-256 entries |
| Private settings preserved by source archiving | GO (source only) | Tracked files only; no migration |
| Standalone CI installation | HOLD | Await disposable clean install + rollback evidence |
| Native Qt GUI and all original behaviors | HOLD | Snapshot fidelity alone does not prove runtime parity |
| Side-by-side config/launcher identity | HOLD | Code-level isolation; independent runtime test needed |
| Real SDR ownership and receiver Start/Stop/Restart | HOLD | Legacy global-service ownership unsafe; disabled by safe shim |
| OS support beyond tested Linux | HOLD | Windows, macOS, Pi not accepted by this installer |
| Production/general release | HOLD | Independent QA and explicit owner approval required |

No changes to `main`, `gh-pages`, `legacy/v0.3.1`, PRs #15–#21,
current installed software, SDR hardware, or services. This Draft PR is a
review artifact only.
