#!/usr/bin/env python3
"""AGENT 06 independent PR #29 race evidence — synthetic CI-only fixtures.

Agent 07 continuation: turn independent reproductions into negative security
acceptance checks. A PASS still does NOT prove resistance to hostile same-UID
processes or production release safety.
Runs exclusively in a newly created disposable RUNNER_TEMP sandbox on Linux.
No production installation, pipx, QSettings, systemctl, sudo, SDR or network.
"""
from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
from pathlib import Path
import subprocess
import sys
import time
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

    def assert_retains_without_unlink(self, prefix, switch_to):
        """Enforce: no pathname-based deletion in shared transaction namespace.

        The audit's previous deterministic inject-on-unlink tests established
        that any validation before os.unlink is still racy. Their secure
        successors reject the dangerous operation itself; displaced entries
        must be retained as evidence. This is NOT a same-UID trust guarantee.
        """
        real_unlink = os.unlink
        attempted = []
        def forbid(name, *args, **kwargs):
            if kwargs.get("dir_fd") is not None:
                attempted.append(name)
                raise AssertionError("Unsafe path-unlink attempted: " + str(name))
            return real_unlink(name, *args, **kwargs)
        with patch.object(tx.os, "unlink", side_effect=forbid):
            self.lab.switch(switch_to)
        self.assertEqual(attempted, [], "No transaction path may be unlinked")
        matches = list(self.lab.root.glob(prefix + "*"))
        self.assertTrue(matches, "Old transaction evidence must be retained")
        return matches

    def test_accept_pointer_displaced_entry_kept_instead_of_unlink(self):
        self.prepare()
        entries = self.assert_retains_without_unlink(".pointer-", "new")
        self.assertTrue(any(x.is_symlink() and os.readlink(x) == "releases/old"
                            for x in entries))
        self.assertEqual(self.lab.status()["active"], "new")

    def test_accept_state_displaced_entry_kept_instead_of_unlink(self):
        self.prepare()
        entries = self.assert_retains_without_unlink(".tx-", "new")
        self.assertTrue(any(b'"active":"old"' in x.read_bytes()
                            for x in entries if x.is_file()))
        self.assertEqual(self.lab.status()["active"], "new")

    def test_accept_verified_pending_retirement_kept_instead_of_unlink(self):
        self.prepare()
        entries = self.assert_retains_without_unlink(".retired-journal-", "new")
        self.assertTrue(any(b'"owner"' in x.read_bytes()
                            for x in entries if x.is_file()))
        self.assertFalse(self.lab.pending.exists())
        self.assertEqual(self.lab.status()["active"], "new")

    def test_accept_deactivation_retired_pointer_kept_instead_of_unlink(self):
        self.prepare()
        entries = self.assert_retains_without_unlink(".retired-", None)
        self.assertTrue(any(x.is_symlink() and os.readlink(x) == "releases/old"
                            for x in entries))
        self.assertIsNone(self.lab.status()["active"])

    def test_accept_env_root_drift_is_rejected_without_write(self):
        self.lab.stage_fixture("one", b"old-base")
        second = Path(tempfile.mkdtemp(prefix="flight-pr29-other-", dir=self.base))
        os.environ["RUNNER_TEMP"] = str(second)
        with self.assertRaisesRegex(RuntimeError, "RUNNER_TEMP changed"):
            self.lab.stage_fixture("two", b"must-not-write")
        unexpected = second / "flight-transaction-lab" / "qa" / "releases" / "two"
        self.assertFalse(unexpected.exists(), "No silent redirected writes")
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
        self.assertTrue(self.lab.pending.exists(),
                        "Corrupt journal must remain available for diagnosis")

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

    def test_control_two_concurrent_rollbacks_are_serializable(self):
        self.prepare()
        self.lab.switch("new")
        ctx = multiprocessing.get_context("fork")
        start = ctx.Event()
        results = ctx.Queue()
        root = self.lab.root
        def worker():
            try:
                if not start.wait(timeout=5):
                    raise RuntimeError("start barrier timed out")
                tx.TransactionLab(root).rollback()
                results.put("PASS")
            except BaseException as exc:
                results.put("FAIL:" + repr(exc))
        processes = [ctx.Process(target=worker) for _ in range(2)]
        for process in processes:
            process.start()
        start.set()
        for process in processes:
            process.join(timeout=10)
            if process.is_alive():
                process.terminate()
                process.join()
                self.fail("Concurrent rollback deadlocked")
            self.assertEqual(process.exitcode, 0)
        self.assertEqual([results.get(timeout=3) for _ in processes],
                         ["PASS", "PASS"])
        # Two serialized rollback transactions toggle new -> old -> new.
        self.assertEqual(self.lab.status()["active"], "new")
        self.assertEqual(self.lab.status()["previous"], "old")

    def test_control_corrupt_state_refuses_recovery_without_deleting_journal(self):
        self.prepare()
        with self.assertRaisesRegex(RuntimeError, "Injected fault"):
            self.lab.switch("new", fault="after_pointer")
        self.lab.state_path.write_text(json.dumps({
            "owner": "FOREIGN", "active": "old", "previous": None}))
        journal_before = self.lab.pending.read_bytes()
        state_before = self.lab.state_path.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "Foreign or corrupt"):
            self.lab.recover()
        self.assertEqual(self.lab.pending.read_bytes(), journal_before)
        self.assertEqual(self.lab.state_path.read_bytes(), state_before)
        self.assertEqual(os.readlink(self.lab.current), "releases/new")

    def test_accept_replaced_lock_cannot_overlap_critical_sections(self):
        self.prepare()
        child = None
        try:
            with self.assertRaisesRegex(RuntimeError,
                                        "Lock entry replaced during transaction"):
                with self.lab.locked():
                    old_inode = self.lab.lock_path.stat().st_ino
                    self.lab.lock_path.unlink()
                    self.lab.lock_path.write_bytes(b"FOREIGN_LOCK_PATH")
                    self.assertNotEqual(self.lab.lock_path.stat().st_ino, old_inode)
                    # Fresh subprocess prevents inherited parent flock FDs
                    # under fork from extending the original held lock.
                    script = (
                        "import os,sys\n"
                        "from pathlib import Path\n"
                        "from tools import flight_transaction_lab as tx\n"
                        "print('READY',flush=True)\n"
                        "with tx.TransactionLab(Path(sys.argv[1])).locked():\n"
                        " print('ENTERED',flush=True)\n"
                    )
                    child = subprocess.Popen(
                        [sys.executable, "-c", script, str(self.lab.root)],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        cwd=os.getcwd(), env=os.environ.copy(), close_fds=True)
                    self.assertEqual(child.stdout.readline().strip(), b"READY")
                    # Before parent release, child MUST remain blocked even
                    # though lab.lock was replaced by a same-UID process.
                    time.sleep(0.35)
                    self.assertIsNone(child.poll(),
                        "Replacing lock inode entered a second critical section")
            stdout, stderr = child.communicate(timeout=8)
            self.assertEqual(child.returncode, 0, stderr.decode(errors="replace"))
            self.assertIn(b"ENTERED", stdout)
        finally:
            if child is not None and child.poll() is None:
                child.kill()
                child.communicate()


if __name__ == "__main__":
    unittest.main(verbosity=2)
