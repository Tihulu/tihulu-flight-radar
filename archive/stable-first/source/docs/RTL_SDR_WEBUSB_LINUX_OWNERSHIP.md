# RTL-SDR USB ownership — verified browser/WebUSB recovery (6 November 2026)

Applies to **TIHULU Flight Radar**, **Satellite Center**, **Text Center FM/DAB/RTL-433**, **Tihulu Survival Kit Radio Center**, and future RTL2832U modules. English is the default app/help language.

## Confirmed result on Pop!_OS 24.04 / Nooelec NESDR SMArt v5

Real device: **0bda:2838**, RTL2832U. Brave showed:

```text
RadioError.UsbTransferError: Could not connect to the RTL-SDR stick.
Failed to execute 'claimInterface' on 'USBDevice':
Unable to claim interface.
```

`readsb.service` was **inactive**, no competing SDR process was listed by `ps` / `fuser`, but `lsusb -t` showed USB interface 0 attached to **`dvb_usb_rtl28xxu`**. The user explicitly unbound **only that interface** (`1-4:1.0` on this one machine) and confirmed that the Brave browser-only WebUSB flow then **worked**. After unbinding `lsusb -t` displayed `Driver=[none]`.

**Root cause demonstrated:** Linux DVB kernel-driver ownership of USB interface 0, not an absent Python bridge, a bad airplane-feed API, or a missing permission-grant dialog. The same symptom *can* have other causes on other computers; detect before acting.

## Safe diagnostics — no downloads required

Close the native receivers before opening the same SDR in Brave/Chrome/Edge. Stop a system service **only when you explicitly choose to**:

```bash
systemctl is-active readsb.service
# Optional, only when transferring the same SDR from readsb to the browser:
sudo systemctl stop readsb.service
lsusb -d 0bda:2838
lsusb -t
```

If `Driver=dvb_usb_rtl28xxu` is shown on RTL2832U interface 0, the optional repository helper can locate the real sysfs bus/device path **without assuming the example `1-4` applies to every PC**:

```bash
bash scripts/rtl-sdr-usb-interface.sh status
# Only when explicitly choosing to release the matching DVB interface:
bash scripts/rtl-sdr-usb-interface.sh release
# After browser hard-stop, to restore the Linux DVB driver:
bash scripts/rtl-sdr-usb-interface.sh restore
```

The helper is **read-only by default**; it verifies vendor `0bda` and product `2838`, acts on interface 0 only, rejects a different driver and refuses multiple matching devices unless one USB-ID is selected (e.g. `release 1-4`). Privilege is requested for the specific `unbind` / `bind` sysfs write, not for diagnosis. It **never** kills processes, blacklists a module, disables services, changes permissions, or makes WebUSB claims.

Equivalent *manual* write for the validated computer **only**, after verifying `1-4` still belongs to the Nooelec device:

```bash
echo '1-4:1.0' | sudo tee /sys/bus/usb/drivers/dvb_usb_rtl28xxu/unbind
# After finishing and explicitly stopping browser capture:
echo '1-4:1.0' | sudo tee /sys/bus/usb/drivers/dvb_usb_rtl28xxu/bind
```

**Do not unplug/replug after unbinding but before starting the browser:** re-enumeration can load the DVB driver again. An automatic driver bind may also happen after a restart. Recheck instead of permanently blacklisting `dvb_usb_rtl28xxu`; other DVB receivers may need it.

## Browser-only vs desktop ownership

A HTTPS website/PWA cannot run `sudo`, release another process's USB handle, unbind kernel drivers, install WinUSB, or change `udev`. On supported Chromium browsers, direct WebUSB can work **after** OS-level exclusive access is available. No additional application or Python pairing token is needed for supported browser-only WebUSB mode.

- The native app/readsb and Brave/Satellite Center **must not claim the same single dongle simultaneously**. Use the app's Hard Stop / Release USB first. A systemd-managed readsb may need a **separate explicit** service stop.
- Stopping readsb is not the same as unbinding a DVB driver. Verify both individually.
- After selecting the device in WebUSB, permission grant alone does not confirm a successful `claimInterface(0)` or a decoded RF signal. Check a real I/Q transfer and then CRC-verified 1090 MHz messages when using Flight Radar.
- Release this tab's own WebUSB handle on Stop, visibility loss, or close; never forcibly release another app's handle.
- On Linux, a separate `udev` / ACL permission failure is possible even after `Driver=[none]`. Do not use `chmod 777`. Other operating systems have their own USB driver rules.
- Browser diagnostics may inspect permission grants and display these manual steps; they must **never** promise or execute a privileged kernel-driver takeover from GitHub Pages.

## Cross-project acceptance checklist

For Flight Radar, Satellite Center, Text Center and Survival Kit: verify a connected-but-unclaimed USB stick, a DVB-driver-owned stick, two competing receiver apps, reconnect/rebind, successful WebUSB transfer, explicit Stop, and return to native reader. Preserve the app's usual FM/DAB/1090 MHz radio settings and real-source integrity. Treat this recovery procedure as **confirmed hardware feedback**, not proof that each other application has passed its own end-to-end RF reception test.
