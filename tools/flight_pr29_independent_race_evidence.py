#!/usr/bin/env python3
"""AGENT 06 independent PR #29 race evidence — synthetic CI-only fixtures.

IMPORTANT: These tests intentionally assert the CURRENT unsafe behavior to
document reproducible release blockers. A green test run is NOT a security GO.
Runs exclusively in a newly created disposable RUNNER_TEMP sandbox on Linux.
No production installation, pipx, QSettings, systemctl, sudo, SDR or network.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import flight_transaction_lab as tx


@unittest.skipUnless(sys.platform == "linux", "Linux renameat2 only")
class IndependentPR29Evidence(unittest.TestCase):
    def setUp(self):
        if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("CI") != "true":
            self.skipTest("GitHub-hosted disposable CI required")
        runner = os.environ.get("RUNNER_TEMP")
        if not runner:
            self.skipTest("RUNNER_TEMP required")
        self.original_env = {key: os.environ.get(key) for key in (
            "GITHUB_ACTIONS", "CI", "RUNNER_TEMP")}
        self.disposable = tempfile.TemporaryDirectory(
            prefix="flight-pr29-independent-", dir=runner)
        self.base = Path(self.disposable.name)
        os.environ["RUNNER_TEMP"] = str(self.base)
        self.lab = tx.TransactionLab(
            self.base / "flight-transaction-lab" / "qa")

    def tearDown(self):
        for key, previous in getattr(self, "original_env", {}).items():
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous
        if hasattr(self, "disposable"):
            self.disposable.cleanup()

    def prepare(self):
        self.lab.stage_fixture("old", b"old")
        self.lab.stage_fixture("new", b"new")
        self.lab.switch("old")

    def race_delete(self, prefix, switch_to):
        """Inject a foreign file at the instant the trusted caller unlinks.

        Real adversarial schedule: after validated moved-entry inode/content,
        another same-UID process swaps the entry before unlink(). The
        injected file's bytes are unrelated to this transaction and must be
        preserved. Existing code calls unconditional unlink and deletes it.
        """
        real_unlink = os.unlink
        observed = []
        original_payload = b"FOREIGN_INDEPENDENT_DATA_PR29"
        def interleave(name, *args, **kwargs):
            fd = kwargs.get("dir_fd")
            if (fd is not None and isinstance(name, str)
                    and name.startswith(prefix) and not observed):
                real_unlink(name, dir_fd=fd)
                handle = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                                 0o600, dir_fd=fd)
                try:
                    os.write(handle, original_payload)
                    os.fsync(handle)
                finally:
                    os.close(handle)
                observed.append(name)
            return real_unlink(name, *args, **kwargs)
        with patch.object(tx.os, "unlink", side_effect=interleave):
            self.lab.switch(switch_to)
        self.assertEqual(len(observed), 1, "Injected race was not reached")
        self.assertFalse((self.lab.root / observed[0]).exists(),
                         "Reproduction: foreign bytes were removed by final unlink")
        self.assertFalse((self.lab.root / observed[0]).is_symlink())
        return observed[0]

    def test_repro_pointer_displaced_entry_replaced_before_unlink(self):
        self.prepare()
        name = self.race_delete(".pointer-", "new")
        self.assertTrue(name.startswith(".pointer-"))
        self.assertEqual(self.lab.status()["active"], "new")

    def test_repro_state_displaced_entry_replaced_before_unlink(self):
        self.prepare()
        name = self.race_delete(".tx-", "new")
        self.assertTrue(name.startswith(".tx-"))
        self.assertEqual(self.lab.status()["active"], "new")

    def test_repro_verified_pending_retirement_replaced_before_unlink(self):
        self.prepare()
        name = self.race_delete(".retired-journal-", "new")
        self.assertTrue(name.startswith(".retired-journal-"))
        self.assertFalse(self.lab.pending.exists())
        self.assertEqual(self.lab.status()["active"], "new")

    def test_repro_verified_deactivation_retired_pointer_replaced_before_unlink(self):
        self.prepare()
        name = self.race_delete(".retired-", None)
        self.assertTrue(name.startswith(".retired-"))
        self.assertIsNone(self.lab.status()["active"])

    def test_repro_env_runner_temp_changed_after_constructor_changes_write_root(self):
        # The root was validated at initial construction; locked() uses live
        # environment rather than a bound root path/descriptor.
        self.lab.stage_fixture("one", b"old-base")
        second = Path(tempfile.mkdtemp(prefix="flight-pr29-other-", dir=self.base))
        os.environ["RUNNER_TEMP"] = str(second)
        self.lab.stage_fixture("two", b"unexpected-other-base")
        unexpected = second / "flight-transaction-lab" / "qa" / "releases" / "two" / "image.bin"
        self.assertEqual(unexpected.read_bytes(), b"unexpected-other-base")
        self.assertFalse((self.lab.releases / "two").exists())

    def test_control_strict_invalid_journal_is_preserved(self):
        self.prepare()
        with self.assertRaisesRegex(RuntimeError, "Injected fault"):
            self.lab.switch("new", fault="after_journal")
        source = json.loads(self.lab.pending.read_text())
        source["before"]["owner"] = "FOREIGN"
        self.lab.pending.write_text(json.dumps(source))
        data = self.lab.pending.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "Foreign or corrupt"):
            self.lab.recover()
        self.assertEqual(self.lab.pending.read_bytes(), data)
        self.assertEqual(self.lab.status if self.lab.pending.exists() else None,
                         self.lab.status)

    def test_control_interrupted_pointer_recovery_and_one_lock_rollback(self):
        self.prepare()
        with self.assertRaisesRegex(RuntimeError, "Injected fault"):
            self.lab.switch("new", fault="after_pointer")
        self.lab.recover()
        self.assertEqual(self.lab.status()["active"], "old")
        self.lab.switch("new")
        self.lab.rollback()
        self.assertEqual(self.lab.status()["active"], "old")

    def test_control_manifest_self_hash_is_not_authentication(self):
        self.lab.stage_fixture("one", b"original")
        path = self.lab.releases / "one"
        raw = b"forged-by-same-uid"
        (path / "image.bin").write_bytes(raw)
        (path / "manifest.json").write_text(json.dumps({
            "owner": tx.OWNER, "name": "one",
            "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}))
        self.lab.switch("one")
        self.assertEqual(self.lab.status()["active"], "one")


if __name__ == "__main__":
    unittest.main(verbosity=2)
