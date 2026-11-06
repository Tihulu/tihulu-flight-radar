# Full tar1090 for web and Pop!_OS without an ADS-B antenna

Status: **0.3.2.dev1 development preview**, 6 November 2026.
Existing **0.3.1** is preserved at `legacy/v0.3.1` and is not modified.

## One original tar1090 GUI, three operating modes

The full upstream tar1090 GUI (pinned tar1090 commit
`5d59b1ba2c5e30eb23f1161940367b7767f10ad5`) is embedded as an
iframe of the **same full map with its aircraft table, photos, filters,
type/registration metadata, and OSM**. This is not a simplified map imitation.

- **Internet only** — works without a connected RTL-SDR, a running readsb
  decoder or any locally hosted tar1090 service. Real aircraft come from
  the configured Internet sources in the parent radar.
- **Antenna only** — works with actual WebUSB/readsb reception and real
  local Mode S/ADS-B observations even if Internet providers are unavailable.
- **Hybrid** — merge by valid ICAO24, one marker; show I/R only when the
  plane was genuinely received both via RF and Internet. Preserve separate
  raw metadata and avoid inventing RF messages.

Click **Full tar1090 · Internet or Radio** on both GitHub Pages deployments or
inside the native app. Source visibility controls inside the full GUI offer
`Internet (I)`, `Local radio (R)`, and `Both (I/R)`. They filter
*display only* and never start/stop an antenna.

## How Pop!_OS works without readsb

The one-line Linux installer now caches the original tar1090 browser files,
from the public `gh-pages` branch, in:

```
~/.local/share/tihulu-flight-radar/tar1090/
```

The authenticated loopback radar server serves **static** `/tar1090/*`
files from this cache. The tar1090 iframe gets fresh, actual aircraft
snapshots only through a restricted `postMessage` interface, not by
pretending to own the user's RTL-SDR or installing a fake readsb decoder.
The same-origin static paths are traversal/symlink guarded. Pairing is still
required for receiver/API access; the full frontend assets contain no token.

If the optional static cache could not be downloaded during installation,
the native GUI can fall back to the public, pinned HTTPS Pages tar1090
frontend. The fallback uses restricted messaging from the explicitly
allowed localhost parent. **The fallback needs Internet, and is not a claim
that offline tar1090 is available without cached assets.** The top-level
radio controller remains unaffected.

On GitHub Pages, tar1090 is already bundled in the site. The parent can
receive browser WebUSB RF, selected public Internet sources, or both; the
embedded tar1090 consumes only those observations. The Pages site cannot
access local readsb without an explicitly paired compatible bridge.

## Safety / freshness

- The full map never automatically claims a USB device or calls systemd.
  Receiver start/stop remain explicit and separate.
- Cached snapshot observations age in real time and expire after 60 seconds.
  The page does not reset stale timestamps to zero or turn Internet aircraft
  into local RF message counts.
- Only `https://tihulu.github.io` and the controlled localhost parent
  can communicate with the tar1090 iframe; origin and window identity
  must match, and the child never receives the bridge secret.
- Browser Internet requests are subject to provider terms, service CORS
  policies, public relay availability, and rate limits. Offline caches are
  only static tar1090 files, not fake live flight data.
- Upstream GPL-2.0-or-later licence and tar1090-db credits are retained.
  Aircraft imagery and live maps still require network access.

## Regressions to verify

Run `node --test tests/tar_full_browser.test.cjs tests/internet_sources.test.cjs`
and `pytest -q tests/test_tar_static_internet_only.py tests/test_bridge.py`.
Native physical SDR/Qt UI checks are separate and should not be declared
passed merely from unit/CI. Check the exact deployed GitHub Pages URLs and
provider availability after deploy.

Desktop rollback remains available using the exact-commit pinned
`scripts/popos-version-switch.sh legacy` path; see
[Pop!_OS version switching](POP_OS_VERSION_SWITCH_AND_LEGACY.md).
