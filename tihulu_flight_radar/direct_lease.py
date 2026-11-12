"""Kernel-lifetime advisory exclusion for Flight-owned direct RTL-SDR decoders.

No running daemon, external TIHULU imports, PID files, or stale process
identities. Locks coordinate cooperating Flight instances, not other vendors:
the physical USB open remains authoritative against noncooperating processes.
Global systemd readsb/tar1090 services are NEVER owned by this lease.
"""
from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

from .core import DataError


class DirectDeviceLease:
    """Own one private per-user lock FD for a Flight direct SDR child.

    A permanently named lock file is intentional: unlinking a lock file at
    release creates a split-brain race with another process opening it.
    No PID, boot timestamp or JSON metadata is trusted for ownership.
    """

    def __init__(self, device_key: str = "rtlsdr-index-0"):
        if not device_key or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in device_key):
            raise ValueError("Unsafe SDR device lease key")
        self.device_key = device_key
        self._fd: int | None = None

    @staticmethod
    def _directory() -> Path:
        if os.name == "nt":
            base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
            root = Path(base) / "TIHULU-FlightRadar-SDR-Leases-v1"
        else:
            base = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
            root = Path(base) / f"tihulu-flight-radar-sdr-leases-v1-{os.getuid()}"
        # mkdir itself must not traverse a user-overridable symlink at root.
        try:
            root.mkdir(mode=0o700, exist_ok=True)
            st = root.lstat()
        except OSError as exc:
            raise DataError(f"Cannot create private SDR lease directory: {exc}") from exc
        if not stat.S_ISDIR(st.st_mode) or root.is_symlink():
            raise DataError("SDR lease directory is not a private physical directory")
        if os.name != "nt" and (st.st_uid != os.getuid() or (st.st_mode & 0o077)):
            raise DataError("SDR lease directory ownership or permissions are unsafe")
        return root

    def acquire(self) -> None:
        if self._fd is not None:
            return
        root = self._directory()
        path = root / (self.device_key + ".lock")
        flags = os.O_CREAT | os.O_RDWR | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        fd = None
        try:
            if path.is_symlink():
                raise DataError("SDR lease file must not be a symlink")
            fd = os.open(path, flags, 0o600)
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                raise DataError("SDR lease path is not a regular file")
            if os.name != "nt" and (st.st_uid != os.getuid() or (st.st_mode & 0o077)):
                raise DataError("SDR lease file permissions or ownership are unsafe")
            if os.name == "nt":
                import msvcrt

                if st.st_size < 1:
                    os.write(fd, b"\0")
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._fd = fd
        except (OSError, DataError) as exc:
            if fd is not None:
                os.close(fd)
            raise DataError(
                f"RTL-SDR is busy, or its private Flight lease is unsafe/unavailable: {exc}"
            ) from exc

    def release(self) -> None:
        if self._fd is not None:
            fd = self._fd
            self._fd = None
            # Closing a kernel-held lease after the exact direct child exits
            # releases it even if process metadata or lock file content is stale.
            os.close(fd)
