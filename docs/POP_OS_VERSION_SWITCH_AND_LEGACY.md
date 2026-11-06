# Pop!_OS version switching — preview and preserved legacy (6 Nov 2026)

## Archived source revisions

| Version | GitHub ref | Pinned source SHA | Role |
| --- | --- | --- | --- |
| **0.3.1** | [`legacy/v0.3.1`](https://github.com/Tihulu/tihulu-flight-radar/tree/legacy/v0.3.1) | `67280cd84feb89faec6a80f5fe2a55ce5f7b89e6` | Last archived 0.3.1 code snapshot **before** multi-provider enhancement |
| **0.3.2.dev0** | [`preview/v0.3.2-dev0`](https://github.com/Tihulu/tihulu-flight-radar/tree/preview/v0.3.2-dev0) | `c1e9c2c849cab681c863d4f63d538c1a940397f9` | Opt-in multi-Internet-provider preview |

The user physically verified a `0.3.1` installation on Pop!_OS with RF (R),
Internet (I) and ICAO24-matched I/R. **A package version alone does not prove the
exact local Git commit used**. The legacy ref pins the repository's last known
pre-multi-provider 0.3.1 source. To determine whether the old installed
checkout is byte-identical to this archive, inspect the pipx origin **before
replacing it** with:

```bash
cat ~/.local/share/pipx/venvs/tihulu-flight-radar/pipx_metadata.json | grep -E 'git\+|tihulu-flight-radar'
cat ~/.local/share/pipx/venvs/tihulu-flight-radar/lib/python*/site-packages/tihulu_flight_radar-*.dist-info/direct_url.json
```

The user should **close all Flight Radar windows** before switching. The
version switcher replaces the *same* pipx virtual environment and desktop
shortcuts, without keeping two separate installed apps. It does **not** remove
`readsb`, `tar1090`, SDR drivers, stored configurations or recordings, and
does not auto-start an SDR device. The original installer only removes
specifically named superseded application Debian packages via
`apt-get remove`, never `purge` or a receiver service. It requires a normal
non-root Linux user and may request `sudo` for system dependencies and narrow
service-control permissions.

## Download the reusable switching script from GitHub once

```bash
curl -fLsS https://raw.githubusercontent.com/Tihulu/tihulu-flight-radar/preview/v0.3.2-dev0/scripts/popos-version-switch.sh -o "$HOME/tihulu-flight-switch.sh"
```

Review the [switching script](../scripts/popos-version-switch.sh)
and the [installer](../scripts/install-linux.sh) before running shell code
downloaded from GitHub.

### Replace 0.3.1 with the new 0.3.2.dev0 preview

```bash
bash "$HOME/tihulu-flight-switch.sh" preview
```

### Roll back to the preserved 0.3.1 on demand

```bash
bash "$HOME/tihulu-flight-switch.sh" legacy
```

Both commands are **pinned to exact commit SHAs**, not a moving `main`,
`feature`, `preview` or `legacy` branch head. The switching wrapper
downloads the old repository's already-verified `scripts/install-linux.sh`
at that SHA, runs it with `TIHULU_REF` pointing at the same SHA, invokes
`pipx install --force` to replace the existing application, refreshes
launchers, then asserts that Python imports the expected version.

The same procedure works in reverse, so a user can install the preview again
after restoring legacy. Do not claim native multi-network support exists in
0.3.1 or that a new preview passed physical tests until actually verified.

### Verify after installation

```bash
~/.local/share/pipx/venvs/tihulu-flight-radar/bin/python -c "import tihulu_flight_radar; print(tihulu_flight_radar.__version__)"
pipx list
```

Expected output is `0.3.2.dev0` after preview or `0.3.1` after legacy.
GitHub source links provide a stable rollback path even if a later version
has different dependencies or network APIs.

**Avoid** `sudo pipx`, `pipx uninstall` before a successful replacement,
`apt purge readsb`, `apt purge tar1090`, blanket process-killing commands,
or removing other SDR configuration.
