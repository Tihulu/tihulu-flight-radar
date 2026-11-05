"""Platform-aware readsb lifecycle. No shell commands or general root access."""
from __future__ import annotations

import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

from .core import DataError, read_local, read_remote

LINUX_JSON = Path("/run/readsb/aircraft.json")
UNITS = ("readsb.service", "tar1090.service")
ACTIONS = ("start", "stop", "enable", "disable")
SYSTEMCTL = "/usr/bin/systemctl"
MODES = ("Linux services", "Direct readsb", "Remote JSON")


def linux_service_state() -> tuple[bool, str]:
    if platform.system() != "Linux":
        return False, "Linux service mode is available only on Linux."
    try:
        r = subprocess.run([SYSTEMCTL, "is-active", "readsb.service"],
                           capture_output=True, text=True, timeout=3, check=False)
        return r.returncode == 0 and r.stdout.strip() == "active", r.stdout.strip() or r.stderr.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)


def service_action(action: str) -> str:
    if action not in ACTIONS:
        raise DataError("Unsupported service action.")
    if platform.system() != "Linux":
        raise DataError("Systemd service management is Linux-only.")
    # Compatible with the v0.2 Debian package's narrowly scoped sudoers policy.
    cmd = ["/usr/bin/sudo", "-n", SYSTEMCTL, action, *UNITS]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DataError(f"Service operation failed: {exc}") from exc
    if r.returncode:
        detail = (r.stderr or r.stdout).strip()[:500]
        raise DataError(detail or "Service action failed. Configure restricted sudo access.")
    return f"Receiver services: {action} completed."


class ReceiverController:
    def __init__(self):
        self.mode = "Linux services" if platform.system() == "Linux" else "Direct readsb"
        self.remote_url = ""
        self.decoder_path = ""
        self.process: subprocess.Popen | None = None
        self._directory: tempfile.TemporaryDirectory | None = None

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
            return service_action("start")
        if self.process is not None and self.process.poll() is None:
            return "Direct receiver is already running."
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

    def stop(self) -> str:
        if self.mode == "Remote JSON":
            raise DataError("Remote receiver must be stopped on its own computer.")
        if self.mode == "Linux services":
            return service_action("stop")
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

    def close(self):
        # App owns only direct child processes, never existing systemd services.
        if self.process is not None:
            mode = self.mode
            self.mode = "Direct readsb"
            try:
                self.stop()
            finally:
                self.mode = mode
