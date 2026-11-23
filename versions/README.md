# TIHULU Flight Radar — Versions

This directory keeps each version in its own subdirectory with its own README and
installation/access information. The current versions are also listed in the root README.

## Current versions

| Version | Directory | Status | Install / Access |
|---|---|---|---|
| Web 0.3.2.dev4 (live) | [web-0.3.2.dev4/](web-0.3.2.dev4/) | ✅ Live | Open the site in a browser, or serve it locally in one line |
| Ubuntu / Pop!_OS desktop 0.3.2.dev4 | [desktop-ubuntu-popos/](desktop-ubuntu-popos/) | ✅ Published release (verified, signed) | One-line pipx install / .deb / AppImage |
| Windows desktop 0.3.2.dev4 | [desktop-windows/](desktop-windows/) | ✅ Published release (verified, signed) | Download + run |
| macOS desktop 0.3.2.dev4 | [desktop-macos/](desktop-macos/) | ✅ Published release (verified, signed) | Download + run |
| Raspberry Pi 5 (ARM64) 0.3.2.dev4 | [desktop-rpi5-arm/](desktop-rpi5-arm/) | ✅ Published release (CI QEMU, signed) | One-line pipx install (ARM native) |

## Download (draft release `desktop-0.3.2.dev4-20261122-2327`)

Release page: https://github.com/Tihulu/tihulu-flight-radar/releases/tag/desktop-0.3.2.dev4-20261122-2327

| File | Platform | Download |
|---|---|---|
| `tihulu-flight-radar_0.3.2.dev4_amd64.deb` | Ubuntu/Pop!_OS x64 | [.deb](https://github.com/Tihulu/tihulu-flight-radar/releases/download/desktop-0.3.2.dev4-20261122-2327/tihulu-flight-radar_0.3.2.dev4_amd64.deb) |
| `Tihulu_Flight_Radar-x86_64.AppImage` | Ubuntu/Pop!_OS x64 | [AppImage](https://github.com/Tihulu/tihulu-flight-radar/releases/download/desktop-0.3.2.dev4-20261122-2327/Tihulu_Flight_Radar-x86_64.AppImage) |
| `TihuluFlightRadar-win-x64.zip` | Windows x64 | [zip](https://github.com/Tihulu/tihulu-flight-radar/releases/download/desktop-0.3.2.dev4-20261122-2327/TihuluFlightRadar-win-x64.zip) |
| `TihuluFlightRadar-macos-arm64.zip` | macOS Apple Silicon | [zip](https://github.com/Tihulu/tihulu-flight-radar/releases/download/desktop-0.3.2.dev4-20261122-2327/TihuluFlightRadar-macos-arm64.zip) |
| `SHA256SUMS` | all | [SHA256SUMS](https://github.com/Tihulu/tihulu-flight-radar/releases/download/desktop-0.3.2.dev4-20261122-2327/SHA256SUMS) |

The ARM64 (Pi 5) files are in the same release as `..._arm64.deb` and
`...-aarch64.AppImage` (CI QEMU build; verification on physical Pi hardware required).

Verification: `sha256sum -c --ignore-missing SHA256SUMS` compares the downloaded
file's hash against the SHA256SUMS content.

## Rules
1. Every version is added with a DIRECTORY + README + specific source/artifact reference.
2. Version copies in this directory are not modified; a new dated directory is opened for each version.
3. Every README contains: exact source SHA, verification hash, install command and access addresses.
4. Installations never touch your existing readsb/tar1090 services, settings or recordings.
5. Public release is not a version tag/PUBLICATION; this directory is a distribution convenience
   and requires separate approval.
