# TIHULU Flight Radar — Ubuntu / Pop!_OS desktop 0.3.2.dev4

**Status:** ✅ Published release (signed) `desktop-0.3.2.dev4-20261122-2327` (GitHub Actions: `desktop-versions-build.yml`) · **Source:** main (after the parity merge)

## One-line install (recommended — pipx, does not touch your existing install)
```
curl -fsSL https://raw.githubusercontent.com/Tihulu/tihulu-flight-radar/main/scripts/install-linux.sh | bash
```
- Debian 12 / Ubuntu 22.04+ / Pop!_OS supported
- Your existing readsb/tar1090 services, receiver settings and recordings stay unchanged
- To pin the version: `TIHULU_REF=<commit-sha> bash -s` (install-linux.sh accepts `TIHULU_REF`)

## Downloadable packages (draft release `desktop-0.3.2.dev4-20261122-2327`)
| Package | File | Download | Note |
|---|---|---|---|
| .deb | `tihulu-flight-radar_0.3.2.dev4_amd64.deb` | [download](https://github.com/Tihulu/tihulu-flight-radar/releases/download/desktop-0.3.2.dev4-20261122-2327/tihulu-flight-radar_0.3.2.dev4_amd64.deb) | Install with `sudo dpkg -i` |
| AppImage | `Tihulu_Flight_Radar-x86_64.AppImage` | [download](https://github.com/Tihulu/tihulu-flight-radar/releases/download/desktop-0.3.2.dev4-20261122-2327/Tihulu_Flight_Radar-x86_64.AppImage) | Runs with `chmod +x`, no install required |

Release page: https://github.com/Tihulu/tihulu-flight-radar/releases/tag/desktop-0.3.2.dev4-20261122-2327 · Hash verification: download `SHA256SUMS`
and compare with `sha256sum -c --ignore-missing SHA256SUMS`.

## Your current installation
Installed version 0.3.2.dev4 · pipx venv · ~/.local/bin/tihulu-flight-radar symlink.
Rollback path: legacy/v0.3.1 @ 67280cd84feb89faec6a80f5fe2a55ce5f7b89e6.
