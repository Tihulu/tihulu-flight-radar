# Flight Radar — two GitHub Pages sites, ONE source

The user explicitly requires every update to publish **both**:
- Standalone: https://tihulu.github.io/tihulu-flight-radar/
- TEXT CENTER: https://tihulu.github.io/TIHULU-TEXT-CENTER/flight_radar/

## Source-of-truth architecture

The canonical implementation and user-facing project is
`Tihulu/tihulu-flight-radar`, path `tihulu_flight_radar/web/`.
TEXT CENTER mirrors its generated browser files, **not** a fork or second
application. Existing native Windows / Pop!_OS / Debian / macOS M-series /
Raspberry Pi software stays in the Flight Radar repo.

**Canonical release branch: `main`.** Topic branches and archived previews remain readable but neither Pages publishing workflow should point at a draft feature branch after release. The immutable legacy path is `legacy/v0.3.1`.

### Standalone publication

`Tihulu/tihulu-flight-radar/.github/workflows/pages.yml` on the
active source branch performs tests, builds a pinned `webrtlsdr` driver,
bundles the GPL-2.0-or-later original tar1090 HTML/JS/CSS/markers via
`scripts/build-web-tar1090.sh`, and writes the output to the standalone
`gh-pages` branch's root. The default-branch
`.github/workflows/standalone-pages.yml` provides hourly recovery/manual
rebuild from that same source. GitHub Actions may also trigger GitHub Pages'
automatic `pages build and deployment` workflow.

GitHub Settings → Pages → Build and deployment → Deploy from a branch →
`gh-pages` → `/(root)` must be configured for the standalone site.
A green workflow **without** a Pages deployment does not prove that the
public URL is working. Pages deployment jobs and both published
`source-revision.json` files must be checked.

### TEXT CENTER publication

`Tihulu/TIHULU-TEXT-CENTER/.github/workflows/sync-flight-radar-pages.yml`
checks out the SAME source branch and builds the SAME WebUSB and upstream
tar1090 assets, producing `gh-pages/flight_radar/`. It is triggered by
workflow file updates, manual dispatch, or 15-minute cron intervals.
This preserves the existing Satellite Center, RF Geolocation, FM/DAB
and other TEXT CENTER published paths.

Each browser package contains `source-revision.json` with:
`repo`, `source_ref`, and a precise `source_sha`. Verify identical
`source_sha` across both live origins. Never hand-patch only one
published site or leave TEXT CENTER pinned to an outdated commit.

### Full tar1090 interface

The browser's **Full tar1090 interface** opens the original upstream
tar1090 code bundled at build time, not a visual approximation. The
same-origin `tar1090-adapter.js` bridges genuine WebUSB/Internet
aircraft to the upstream tar1090 `data/receiver.json`,
`data/aircraft.json` and empty (non-fabricated) history endpoints.
This makes a separate readsb service unnecessary for *this embedded
static browser view*. The original external local tar1090 URL still
requires a separately running readsb backend. Never start readsb
concurrently with browser WebUSB on the same RTL-SDR.

Upstream tar1090 code must retain its exact pinned Git commit and GPL
source/license attribution. Static metadata is not an RF observation.
Aircraft photos, registration, type, operator and route fields may
require external API or database availability and must be marked
unavailable when not grounded. Preserve correct R/I/I-R badges and
altitude colors, independent of data source.

### Cross-site/PWA acceptance

On every user-requested update:
1. Edit and test the canonical source.
2. Trigger its standalone build, and cause TEXT CENTER sync to run in
   the same task; do not rely solely on its next scheduled check.
3. Verify both builds, the bundle, Pages deployment and matching source
   SHAs; if missing or failed, report specific blockers.
4. Verify installed PWA cache updates; each origin maintains separate
   service worker cache and USB permission grants.
5. Confirm genuine RF and Internet source integrity and no fake aircraft.

Do not combine repositories or delete preserved legacy branches. No website can silently stop systemd, unbind
`dvb_usb_rtl28xxu`, or bypass browser WebUSB permissions.

Site install guide: `tihulu_flight_radar/web/install.html` (one-line main installer, links to both web radars and rollback to legacy). The main branch README mirrors those commands.
