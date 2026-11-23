# TIHULU Flight Radar — Raspberry Pi 5 (ARM64) 0.3.2.dev4

**Status:** ✅ Published release (signed) `desktop-0.3.2.dev4-20261122-2327` (CI QEMU build) / ARM install path

## Option A — One-line pipx install (recommended, ARM native)
On Raspberry Pi OS 64-bit (Bookworm+):
```
curl -fsSL https://raw.githubusercontent.com/Tihulu/tihulu-flight-radar/main/scripts/install-linux.sh | bash
```
- PySide6 has official ARM64 wheels; no extra compilation needed
- Bookworm prerequisites: `python3-venv pipx git curl` + Qt system libraries
  (install-linux.sh installs these with `apt`)
- You can run readsb/tar1090 separately on your Pi; the app does not touch it

## Option B — ARM64 packages (draft release `desktop-0.3.2.dev4-20261122-2327`)
| Package | File | Download |
|---|---|---|
| .deb (arm64) | `tihulu-flight-radar_0.3.2.dev4_arm64.deb` | [download](https://github.com/Tihulu/tihulu-flight-radar/releases/download/desktop-0.3.2.dev4-20261122-2327/tihulu-flight-radar_0.3.2.dev4_arm64.deb) |
| AppImage (aarch64) | `Tihulu_Flight_Radar-aarch64.AppImage` | [download](https://github.com/Tihulu/tihulu-flight-radar/releases/download/desktop-0.3.2.dev4-20261122-2327/Tihulu_Flight_Radar-aarch64.AppImage) |

Release page: https://github.com/Tihulu/tihulu-flight-radar/releases/tag/desktop-0.3.2.dev4-20261122-2327 · Hash verification: `SHA256SUMS` + `sha256sum -c --ignore-missing`.
(Built with aarch64 QEMU emulation in CI; verification on physical Pi hardware required.)

## Physical Pi verification (owner step)
- A real reception test with Pi 5 + Nooelec/RTL-SDR is required (CI cannot guarantee this)
- If readsb is already running there will be a driver conflict; the single-SDR-owner principle applies
