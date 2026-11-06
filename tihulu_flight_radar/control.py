"""Platform-aware readsb lifecycle. No shell commands or general root access."""
from __future__ import annotations

import platform
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from .core import DataError, detect_sdr_processes, read_local, read_remote

LINUX_JSON = Path("/run/readsb/aircraft.json")
UNITS = ("readsb.service", "tar1090.service")
ACTIONS = ("start", "stop", "enable", "disable")
SYSTEMCTL = "/usr/bin/systemctl"
MODES = ("Linux services", "Direct readsb", "Remote JSON")


def _unit_active(unit: str) -> tuple[bool, str]:
    """Read-only state check. Active process != confirmed RF reception."""
    try:
        result = subprocess.run(
            [SYSTEMCTL, "is-active", unit],
            capture_output=True, text=True, timeout=4, check=False,
        )
        state = (result.stdout or result.stderr).strip()
        return result.returncode == 0 and state == "active", state or "unknown"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"unknown ({exc})"


def linux_service_state() -> tuple[bool, str]:
    if platform.system() != "Linux":
        return False, "Linux service mode is available only on Linux."
    receiver_active, receiver_state = _unit_active("readsb.service")
    _, map_state = _unit_active("tar1090.service")
    return receiver_active, f"readsb: {receiver_state} · tar1090: {map_state}"


def _verify_transition(action: str, timeout_seconds: float = 8.0) -> None:
    """Require a stable decoder state, not just a transient systemd 'active'."""
    expected = action == "start"
    deadline = time.monotonic() + timeout_seconds
    matched_since = None
    last_state = "unknown"
    while True:
        active, last_state = _unit_active("readsb.service")
        now = time.monotonic()
        if active == expected:
            if matched_since is None:
                matched_since = now
            # Catch the common USB-busy problem where readsb crashes just
            # after systemd first reports it as active.
            if not expected or now - matched_since >= 1.5:
                return
        else:
            matched_since = None
        if now >= deadline:
            break
        time.sleep(0.3)
    target = "active" if expected else "stopped"
    raise DataError(
        f"readsb failed to stay {target} after {action}. Current state: {last_state}. "
        "The SDR may still be in use by another application. "
        "Inspect: journalctl -u readsb -n 30 --no-pager"
    )


def service_action(action: str) -> str:
    if action not in ACTIONS:
        raise DataError("Unsupported service action.")
    if platform.system() != "Linux":
        raise DataError("Systemd service management is Linux-only.")
    if action == "start" and not _unit_active("readsb.service")[0]:
        conflicts = detect_sdr_processes()
        if conflicts:
            raise DataError(
                "The RTL-SDR may be in use by: " + ", ".join(conflicts) +
                ". Close the competing application before starting readsb."
            )
    # The exact argument list matches the narrowly scoped sudoers policy.
    # Never pass arbitrary strings or request blanket root permissions.
    cmd = ["/usr/bin/sudo", "-n", SYSTEMCTL, action, *UNITS]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DataError(f"Service operation failed: {exc}") from exc
    if result.returncode:
        details = (result.stderr or result.stdout).strip()[:500]
        raise DataError(details or "Service operation failed. Verify the restricted sudo policy.")
    if action in ("start", "stop"):
        _verify_transition(action)
    if action == "start":
        return "Decoder started. Waiting for ADS-B messages; an active service does not guarantee RF reception."
    if action == "stop":
        return "Decoder stopped. Receiver can be used by another SDR module."
    return f"Receiver boot setting: {action} completed."


class ReceiverController:
    def __init__(self):
        self.mode = "Linux services" if platform.system() == "Linux" else "Direct readsb"
        self.remote_url = ""
        self.decoder_path = ""
        self.process: subprocess.Popen | None = None
        self._directory: tempfile.TemporaryDirectory | None = None
        self._service_started_by_app = False

    def configure(self, mode: str, remote_url: str = "", decoder_path: str = ""):
        if mode not in MODES:
            raise DataError("Unknown receiver mode.")
        if self.process is not None and self.process.poll() is None and mode != self.mode:
            raise DataError("Stop direct readsb before changing source.")
        self.mode = mode
        self.remote_url = remote_url.strip()
        self.decoder_path = decoder_path.strip()

    def status(self) -> tuple[bool, str]:
        if self.mode == "Remote JSON":
            return False, "Remote monitoring (receiver controlled on the other device)."
        if self.mode == "Linux services":
            return linux_service_state()
        if self.process is None:
            return False, "Direct receiver is stopped."
        code = self.process.poll()
        if code is not None:
            detail = ""
            if self._directory is not None:
                try:
                    detail = (Path(self._directory.name) / "readsb.log").read_text(
                        encoding="utf-8", errors="replace")[-500:].strip()
                except OSError:
                    pass
            return False, f"readsb exited with code {code}. {detail}"
        return True, "Direct readsb process is running."

    def start(self) -> str:
        if self.mode == "Remote JSON":
            raise DataError("Remote receiver must be started on its own computer.")
        if self.mode == "Linux services":
            preexisting = _unit_active("readsb.service")[0]
            outcome = service_action("start")
            if not preexisting:
                self._service_started_by_app = True
            return outcome
        if self.process is not None and self.process.poll() is None:
            return "Direct receiver is already running."
        if platform.system() == "Linux" and _unit_active("readsb.service")[0]:
            raise DataError(
                "The readsb system service already owns the SDR. "
                "Stop Linux services before selecting Direct readsb mode."
            )
        binary = self.decoder_path or shutil.which("readsb")
        if not binary and platform.system() == "Darwin":
            for candidate in ("/opt/homebrew/bin/readsb", "/usr/local/bin/readsb"):
                if Path(candidate).is_file():
                    binary = candidate
                    break
        if not binary:
            raise DataError("readsb not found. Install a compatible native decoder first.")
        if self.decoder_path and not Path(binary).is_file():
            raise DataError("Specified readsb executable does not exist.")
        if self._directory is not None:
            self._directory.cleanup()
        self._directory = tempfile.TemporaryDirectory(prefix="tihulu-flight-radar-")
        cmd = [str(binary), "--device-type", "rtlsdr", "--device", "0",
               "--gain", "auto", "--write-json", self._directory.name,
               "--write-json-every", "1", "--quiet"]
        try:
            with (Path(self._directory.name) / "readsb.log").open("wb") as log:
                self.process = subprocess.Popen(cmd, stdin=subprocess.DEVNULL,
                                                stdout=log, stderr=subprocess.STDOUT)
        except OSError as exc:
            self._directory.cleanup()
            self._directory = None
            raise DataError(f"Cannot launch readsb: {exc}") from exc
        return "Starting local readsb. Waiting for real aircraft messages."

    def restart(self) -> str:
        """Stop and start the selected receiver, surfacing start failures."""
        if self.mode == "Remote JSON":
            raise DataError("Remote receiver restart must happen on its own computer.")
        self.stop()
        return self.start()

    def stop(self) -> str:
        if self.mode == "Remote JSON":
            raise DataError("Remote receiver must be stopped on its own computer.")
        if self.mode == "Linux services":
            result = service_action("stop")
            self._service_started_by_app = False
            return result
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        self.process = None
        if self._directory is not None:
            self._directory.cleanup()
            self._directory = None
        return "Direct receiver stopped; SDR released."

    def snapshot(self) -> dict:
        if self.mode == "Remote JSON":
            return read_remote(self.remote_url)
        if self.mode == "Linux services":
            return read_local(LINUX_JSON)
        if self._directory is None:
            raise DataError("Start the direct receiver first.")
        return read_local(Path(self._directory.name) / "aircraft.json")

    def close(self, release_local_service: bool = False):
        """Release a direct child and, if requested, local readsb on exit.

        Background systemd services are shared. The desktop "Release SDR on
        exit" policy is explicitly ON by default, but remote JSON mode never
        manages services on another device. Service permissions remain narrow;
        a failed stop must be reported to the caller, not hidden.
        """
        error = None
        if self.process is not None:
            mode = self.mode
            self.mode = "Direct readsb"
            try:
                self.stop()
            except (DataError, OSError) as exc:
                error = exc
            finally:
                self.mode = mode
        if (platform.system() == "Linux"
                and self.mode == "Linux services"
                and (release_local_service or self._service_started_by_app)
                and _unit_active("readsb.service")[0]):
            try:
                service_action("stop")
                self._service_started_by_app = False
            except DataError as exc:
                error = exc
        if error:
            raise DataError(f"SDR release on exit was incomplete: {error}") from error
