"""Platform-aware readsb lifecycle. No shell commands or general root access."""
from __future__ import annotations

import platform
import threading
from functools import wraps
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
# Maximum time Quit waits for a receiver command already in progress.
# An incomplete operation must be reported without losing the child handle.
QUIT_OPERATION_TIMEOUT_SECONDS = 5.0


class MixedOwnershipWarning(DataError):
    """Safe nonfatal Quit warning; external systemd service was untouched."""



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


def linux_readsb_unit_installed() -> bool:
    """Detect whether the configured local systemd decoder unit exists.

    An absent service is not evidence that the RTL-SDR or a direct readsb
    decoder is unavailable. Native UI may instead use Direct readsb.
    """
    if platform.system() != "Linux":
        return False
    try:
        result = subprocess.run(
            [SYSTEMCTL, "show", "-p", "LoadState", "--value", "readsb.service"],
            capture_output=True, text=True, timeout=4, check=False,
        )
        return result.returncode == 0 and result.stdout.strip() == "loaded"
    except (OSError, subprocess.TimeoutExpired):
        return False


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


def _only_while_running(fn):
    """Serialize receiver mutations and reject work once Quit starts."""
    @wraps(fn)
    def guarded(self, *args, **kwargs):
        with self._operation_lock:
            if self._quit_requested.is_set():
                raise DataError("Receiver is shutting down; Start/Restart/configuration refused.")
            return fn(self, *args, **kwargs)
    return guarded


class ReceiverController:
    def __init__(self):
        self.mode = "Linux services" if platform.system() == "Linux" else "Direct readsb"
        self.remote_url = ""
        self.decoder_path = ""
        self.process: subprocess.Popen | None = None
        self._directory: tempfile.TemporaryDirectory | None = None
        self._service_started_by_app = False
        # Shared systemd actions control both units. Only a unit confirmed
        # inactive BEFORE our own successful Start can be attributed to us.
        # Unknown/failed states are never enough proof of ownership.
        self._service_units_started_by_app: set[str] = set()
        self._operation_lock = threading.RLock()
        self._quit_requested = threading.Event()
        self._inside_close = False
        self._closed = False

    def request_quit(self):
        """Stop admitting new starts before any wait for an in-flight worker."""
        self._quit_requested.set()

    @_only_while_running
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

    @_only_while_running
    def start(self) -> str:
        if self.mode == "Remote JSON":
            raise DataError("Remote receiver must be started on its own computer.")
        if self.mode == "Linux services":
            before = {unit: _unit_active(unit) for unit in UNITS}
            outcome = service_action("start")
            for unit, (active, state) in before.items():
                if not active and state == "inactive":
                    self._service_units_started_by_app.add(unit)
            self._service_started_by_app = (
                "readsb.service" in self._service_units_started_by_app
            )
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

    @_only_while_running
    def restart(self) -> str:
        """Stop and start the selected receiver, surfacing start failures."""
        if self.mode == "Remote JSON":
            raise DataError("Remote receiver restart must happen on its own computer.")
        self.stop()
        return self.start()

    def stop(self) -> str:
        with self._operation_lock:
            return self._stop_locked()

    def _stop_locked(self) -> str:
        if self._quit_requested.is_set() and not self._inside_close:
            raise DataError("Receiver is shutting down; explicit Stop refused.")
        if self.mode == "Remote JSON":
            raise DataError("Remote receiver must be stopped on its own computer.")
        if self.mode == "Linux services":
            # An explicit user-invoked Stop remains a separate, intentional
            # command for the paired services, unlike passive application Exit.
            result = service_action("stop")
            self._service_units_started_by_app.clear()
            self._service_started_by_app = False
            return result
        if self.process is not None:
            # Operate on the exact child handle this app created, never a
            # shared process name, external service, or unverified PID.
            try:
                if self.process.poll() is None:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait(timeout=3)
                else:
                    self.process.wait(timeout=3)  # reap already-ended child
            except (OSError, subprocess.TimeoutExpired) as exc:
                # Keep the handle/temporary directory for a safe retry.
                raise DataError("App-owned direct readsb did not exit: " + str(exc)) from exc
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
        """Idempotent bounded Quit, preserving PR #15's paired-service rules."""
        self.request_quit()  # set before blocking on in-flight Start/Restart
        if not self._operation_lock.acquire(timeout=QUIT_OPERATION_TIMEOUT_SECONDS):
            raise DataError(
                "SDR release on exit incomplete: an app-owned receiver operation "
                "is still running; retry Quit after it finishes."
            )
        try:
            if self._closed:
                return
            error = None
            self._inside_close = True
            try:
                if self.process is not None or self._directory is not None:
                    mode = self.mode
                    self.mode = "Direct readsb"
                    try:
                        self._stop_locked()
                    except (DataError, OSError) as exc:
                        error = exc
                    finally:
                        self.mode = mode
                if (platform.system() == "Linux" and release_local_service
                        and self._service_units_started_by_app):
                    if self._service_units_started_by_app == set(UNITS):
                        try:
                            service_action("stop")
                        except DataError as exc:
                            error = exc if error is None else DataError(
                                f"{error}; service release: {exc}"
                            )
                        else:
                            self._service_units_started_by_app.clear()
                            self._service_started_by_app = False
                    else:
                        # Existing sudoers authorizes only a paired stop.
                        # Preserve the external unit and PR #15's warning.
                        mixed = MixedOwnershipWarning(
                            "Automatic release skipped: readsb/tar1090 have mixed "
                            "ownership. The external service was preserved; a "
                            "receiver started here may remain active. Stop it "
                            "explicitly only when no other app is using it."
                        )
                        error = mixed if error is None else DataError(f"{error}; {mixed}")
            finally:
                self._inside_close = False
            if error:
                # Only a pure mixed ownership outcome is a nonfatal warning.
                # A concurrent direct-child failure remains fatal even if its
                # error includes the words "mixed ownership".
                msg = f"SDR release on exit was incomplete: {error}"
                if isinstance(error, MixedOwnershipWarning):
                    raise MixedOwnershipWarning(msg) from error
                raise DataError(msg) from error
            self._closed = True
        finally:
            self._operation_lock.release()
