#!/usr/bin/env python3
"""Independent Agent 06 PR31 security QA: disposable Linux-only evidence.

These tests deliberately separate corrected controls from still-exploitable
same-UID namespace weaknesses. A green result is NOT release authorization.
All mutating actions are confined to fresh directories below RUNNER_TEMP.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import time
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import flight_transaction_lab as tx


@unittest.skipUnless(sys.platform.startswith("linux"), "renameat2 is Linux-only")
class PR31IndependentSecurityQA(unittest.TestCase):
    def setUp(self):
        if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("CI") != "true":
            self.skipTest("Hosted CI-only independent QA")
        host_runner = os.environ.get("RUNNER_TEMP")
        if not host_runner:
            self.skipTest("Missing hosted CI RUNNER_TEMP")
        self.original_runner = host_runner
        self.disposable = tempfile.TemporaryDirectory(
            prefix="flight-pr31-agent06-", dir=host_runner)
        self.anchor = Path(self.disposable.name)
        self.runner = self.anchor / "runner"
        self.runner.mkdir(mode=0o700)
        os.environ["RUNNER_TEMP"] = str(self.runner)

    def tearDown(self):
        if hasattr(self, "original_runner"):
            os.environ["RUNNER_TEMP"] = self.original_runner
        if hasattr(self, "disposable"):
            self.disposable.cleanup()

    def new_lab(self, name="qa"):
        return tx.TransactionLab(
            self.runner / "flight-transaction-lab" / name)

    def prepared(self, name="qa"):
        lab = self.new_lab(name)
        lab.stage_fixture("old", b"original")
        lab.stage_fixture("new", b"replacement")
        lab.switch("old")
        return lab

    def retained_count(self, lab):
        return sum(name.startswith((".tx-", ".pointer-", ".retired-"))
                   for name in os.listdir(lab.root))

    def test_01_source_has_no_pathname_unlink(self):
        code = Path(tx.__file__).read_text(encoding="utf-8")
        self.assertNotIn("os.unlink(", code)
        self.assertNotIn("os.remove(", code)
        self.assertNotIn("shutil.rmtree(", code)

    def test_02_displaced_pointer_and_state_foreign_bytes_survive(self):
        # Deterministic malicious writer replaces the already-exchanged old
        # entry before the validation of that displaced inode. No deletion is
        # allowed; fail closed, even though the shared path can be poisoned.
        for label, target in (("pointer", "current"), ("state", "state.json")):
            with self.subTest(label=label):
                lab = self.prepared("q" + label)
                original_rename = tx._rename
                proof = b"FOREIGN-POST-EXCHANGE-" + label.encode()
                injected = [False]

                def interfere(fd, src, dst, flag):
                    original_rename(fd, src, dst, flag)
                    if not injected[0] and flag == tx._EXCHANGE and dst == target:
                        injected[0] = True
                        os.rename(src, ".saved-original-" + label,
                                  src_dir_fd=fd, dst_dir_fd=fd)
                        tx._write_new(fd, src, proof)

                with patch.object(tx, "_rename", side_effect=interfere):
                    with self.assertRaisesRegex(RuntimeError,
                                                "Foreign file swapped"):
                        lab.switch("new")
                self.assertTrue(injected[0], "Adversarial schedule was reached")
                self.assertTrue(any(p.is_file() and not p.is_symlink()
                                    and p.read_bytes() == proof
                                    for p in lab.root.iterdir()),
                                "Foreign content was lost")

    def test_03_retired_journal_and_pointer_foreign_bytes_survive(self):
        for label in ("journal", "pointer"):
            with self.subTest(label=label):
                lab = self.prepared("r" + label)
                original_rename = tx._rename
                proof = b"FOREIGN-RETIRED-" + label.encode()
                injected = [False]

                def interfere(fd, src, dst, flag):
                    original_rename(fd, src, dst, flag)
                    matches = (src == "pending.json" and
                               dst.startswith(".retired-journal-")) if label == "journal" else (
                               src == "current" and dst.startswith(".retired-"))
                    if not injected[0] and matches:
                        injected[0] = True
                        os.rename(dst, ".saved-retired-" + label,
                                  src_dir_fd=fd, dst_dir_fd=fd)
                        tx._write_new(fd, dst, proof)

                with patch.object(tx, "_rename", side_effect=interfere):
                    with self.assertRaises(RuntimeError):
                        lab.switch("new") if label == "journal" else lab.switch(None)
                self.assertTrue(injected[0])
                self.assertTrue(any(p.is_file() and not p.is_symlink()
                                    and p.read_bytes() == proof
                                    for p in lab.root.iterdir()),
                                "Foreign retired-path bytes were lost")

    def test_04_root_path_replacement_can_hide_committed_operation(self):
        # Known remaining P1 threat-model gap: the lock and root fd bind the
        # original inode, but no post-operation path-to-inode check exists.
        lab = self.prepared("rootswap")
        original_rename = tx._rename
        injected = [False]
        displaced = lab.root.parent / "qa-displaced"
        def interfere(fd, src, dst, flag):
            original_rename(fd, src, dst, flag)
            if (not injected[0] and src.startswith(".pointer-")
                    and dst == "current" and flag == tx._EXCHANGE):
                injected[0] = True
                lab.root.rename(displaced)
                lab.root.mkdir(mode=0o700)
                (lab.root / "foreign-sentinel").write_bytes(b"do-not-delete")
        with patch.object(tx, "_rename", side_effect=interfere):
            lab.switch("new")  # Returns success on the displaced original fd.
        self.assertTrue(injected[0])
        self.assertEqual((lab.root / "foreign-sentinel").read_bytes(), b"do-not-delete")
        self.assertEqual(json.loads((displaced / "state.json").read_text())["active"],
                         "new", "Commit silently completed in displaced directory")
        with self.assertRaisesRegex(RuntimeError, "Fixture root inode changed"):
            lab.status()
        self.assertFalse((lab.root / "state.json").exists(),
                         "New path must not be mistaken for committed original")

    def test_05_base_directory_replacement_splits_directory_locks(self):
        # Known remaining P1: flock on an inode is not a namespace lock.
        first = self.prepared("baseswap")
        displaced = self.anchor / "runner-original"
        with first.locked() as view_old:
            self.runner.rename(displaced)
            self.runner.mkdir(mode=0o700)
            second = self.new_lab("baseswap")
            # Both contexts acquire exclusive flocks on different base inodes.
            with second.locked() as view_new:
                self.assertNotEqual(os.fstat(view_old.root_fd).st_ino,
                                    os.fstat(view_new.root_fd).st_ino)
                self.assertNotEqual(os.fstat(view_old.root_fd).st_dev,
                                    -1)
        self.assertTrue(displaced.is_dir())

    def test_06_lock_name_replacement_does_not_split_unchanged_base(self):
        # Fresh child with no inherited flock fd: only the pinned runner-dir
        # flock can serialize it after lab.lock inode has been replaced.
        lab = self.prepared("lockswap")
        child = None
        try:
            with self.assertRaisesRegex(RuntimeError,
                                        "Lock entry replaced during transaction"):
                with lab.locked():
                    old = lab.root / ".saved-original-lock"
                    lab.lock_path.rename(old)
                    lab.lock_path.write_bytes(b"FOREIGN-LOCK-PATH")
                    script = (
                        "from pathlib import Path\n"
                        "import sys\n"
                        "from tools import flight_transaction_lab as tx\n"
                        "print('READY',flush=True)\n"
                        "with tx.TransactionLab(Path(sys.argv[1])).locked():\n"
                        " print('ENTERED',flush=True)\n"
                    )
                    child = subprocess.Popen(
                        [sys.executable, "-c", script, str(lab.root)],
                        cwd=os.getcwd(), env=os.environ.copy(),
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        close_fds=True)
                    self.assertEqual(child.stdout.readline().strip(), b"READY")
                    time.sleep(0.25)
                    self.assertIsNone(child.poll(),
                                      "Second critical section bypassed runner flock")
            output, error = child.communicate(timeout=8)
            self.assertEqual(child.returncode, 0, error.decode(errors="replace"))
            self.assertIn(b"ENTERED", output)
            self.assertEqual(lab.lock_path.read_bytes(), b"FOREIGN-LOCK-PATH")
        finally:
            if child is not None and child.poll() is None:
                child.kill()
                child.communicate()

    def test_07_quarantine_can_overshoot_claimed_256_slot_cap(self):
        # Known P2: only pre-transaction count is bounded, not reservations
        # for up to three new entries created by the transaction.
        lab = self.prepared("cap")
        current = self.retained_count(lab)
        self.assertLess(current, 255)
        for index in range(255 - current):
            (lab.root / (".tx-seed-" + str(index))).write_bytes(b"fixture")
        self.assertEqual(self.retained_count(lab), 255)
        lab.switch("new")
        self.assertGreater(self.retained_count(lab), tx.RETAINED_MAX)
        with self.assertRaisesRegex(RuntimeError, "Retained transaction evidence limit"):
            lab.switch("old")

    def test_08_corrupt_pending_journal_stays_intact(self):
        lab = self.prepared("corrupt")
        with self.assertRaisesRegex(RuntimeError, "Injected fault"):
            lab.switch("new", fault="after_journal")
        journal = b'{"owner":"FOREIGN","before":null,"to":"new"}'
        lab.pending.write_bytes(journal)
        with self.assertRaises(RuntimeError):
            lab.recover()
        self.assertEqual(lab.pending.read_bytes(), journal)


if __name__ == "__main__":
    unittest.main(verbosity=2)
