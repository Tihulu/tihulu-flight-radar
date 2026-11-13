#!/usr/bin/env python3
"""Agent 06 independent PR35 exact-head red-team evidence, disposable Linux CI.

This suite deliberately PASSes when a still-exploitable late race is proven.
Those positive reproductions are SECURITY HOLD, not remediation success.
Only newly generated RUNNER_TEMP paths are mutated. No actual installer,
owner workstation, pipx, sudoers, QSettings, SDR or services are accessed.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from tools import flight_transaction_lab as tx


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux-only fixture")
class Agent06PR35IndependentQA(unittest.TestCase):
    def setUp(self):
        if os.environ.get("CI") != "true" or os.environ.get("GITHUB_ACTIONS") != "true":
            self.skipTest("Only dedicated GitHub disposable CI is allowed")
        home = os.environ.get("RUNNER_TEMP")
        if not home:
            self.skipTest("RUNNER_TEMP missing")
        self.runner_before = home
        self.tmp = tempfile.TemporaryDirectory(prefix="agent06-pr35-", dir=home)
        self.top = Path(self.tmp.name)
        self.base = self.top / "runner"
        self.base.mkdir(mode=0o700)
        os.environ["RUNNER_TEMP"] = str(self.base)

    def tearDown(self):
        if hasattr(self, "runner_before"):
            os.environ["RUNNER_TEMP"] = self.runner_before
        if hasattr(self, "tmp"):
            self.tmp.cleanup()

    def make_lab(self, name, pins=None):
        return tx.TransactionLab(self.base / "flight-transaction-lab" / name,
                                 external_pins=pins)

    def prepared(self, name):
        lab = self.make_lab(name)
        lab.stage_fixture("old", b"old-image")
        lab.stage_fixture("new", b"new-image")
        lab.switch("old")
        return lab

    def record_change(self, release, name, raw):
        (release / "image.bin").write_bytes(raw)
        (release / "manifest.json").write_text(json.dumps({
            "owner": tx.OWNER, "name": name,
            "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)
        }), encoding="utf-8")

    def count_evidence(self, lab):
        return sum(n.startswith((".tx-", ".pointer-", ".retired-"))
                   for n in os.listdir(lab.root))

    def test_01_no_destructive_pathname_unlink_in_lab(self):
        source = Path(tx.__file__).read_text(encoding="utf-8")
        self.assertNotIn("os.unlink(", source)
        self.assertNotIn("os.remove(", source)
        self.assertNotIn("shutil.rmtree(", source)

    def test_02_foreign_displaced_pointer_bytes_survive(self):
        lab = self.prepared("foreign")
        original = tx._rename
        marker = b"FOREIGN_AGENT06_PR35_INJECTION"
        fired = []
        def injection(fd, src, dst, flags):
            original(fd, src, dst, flags)
            if not fired and dst == "current" and flags == tx._EXCHANGE:
                fired.append(src)
                os.rename(src, ".saved-own-pointer",
                          src_dir_fd=fd, dst_dir_fd=fd)
                tx._write_new(fd, src, marker)
        with patch.object(tx, "_rename", side_effect=injection):
            with self.assertRaisesRegex(RuntimeError, "Foreign file swapped"):
                lab.switch("new")
        self.assertEqual(len(fired), 1)
        self.assertTrue(any(p.is_file() and not p.is_symlink()
                            and p.read_bytes() == marker
                            for p in lab.root.iterdir()))
        self.assertTrue(lab.pending.exists(), "Suspicious pending journal must survive")

    def test_03_second_exit_walk_catches_first_walk_swap(self):
        lab = self.prepared("firstwalk")
        old_base = self.top / "firstwalk-moved"
        real_open = tx._open_chain
        count = []
        def interleave(path, *, create=False):
            fd = real_open(path, create=create)
            if os.fspath(path) == os.fspath(self.base):
                count.append(True)
                if len(count) == 4:
                    self.base.rename(old_base)
                    self.base.mkdir(mode=0o700)
                    (self.base / "sentinel").write_bytes(b"NOT-OWNED")
            return fd
        with patch.object(tx, "_open_chain", side_effect=interleave):
            with self.assertRaisesRegex(RuntimeError, "Validated runner base namespace changed"):
                lab.switch("new")
        self.assertEqual(len(count), 5)
        self.assertEqual((self.base / "sentinel").read_bytes(), b"NOT-OWNED")
        self.assertEqual(json.loads((old_base / "flight-transaction-lab" /
                          "firstwalk" / "state.json").read_text())["active"], "new")

    def test_04_last_exit_walk_still_reports_false_success(self):
        # P1 POSITIVE VULNERABILITY REPRODUCTION. Swap after second walk
        # acquired a valid FD, before validation can finish.
        lab = self.prepared("lastwalk")
        detached = self.top / "lastwalk-detached"
        real_open = tx._open_chain
        seen = []
        def interleave(path, *, create=False):
            fd = real_open(path, create=create)
            if os.fspath(path) == os.fspath(self.base):
                seen.append(True)
                if len(seen) == 5:
                    self.base.rename(detached)
                    self.base.mkdir(mode=0o700)
                    (self.base / "foreign-contents").write_bytes(b"FOREIGN")
            return fd
        with patch.object(tx, "_open_chain", side_effect=interleave):
            lab.switch("new")  # BUG: returns success for hidden detached root
        self.assertEqual(len(seen), 5)
        self.assertEqual((self.base / "foreign-contents").read_bytes(), b"FOREIGN")
        self.assertFalse((self.base / "flight-transaction-lab" / "lastwalk").exists())
        self.assertEqual(json.loads((detached / "flight-transaction-lab" /
                          "lastwalk" / "state.json").read_text())["active"], "new")
        with self.assertRaisesRegex(RuntimeError, "Validated runner base inode changed"):
            lab.status()

    def test_05_finish_time_mutation_is_detected_on_exit(self):
        genuine = b"trusted-before"
        lab = self.make_lab("finish")
        lab.stage_fixture("one", genuine)
        pinned = self.make_lab("finish", pins={"one":hashlib.sha256(genuine).hexdigest()})
        real_finish = tx._View.finish
        raced = []
        def after_finish(view, new_state):
            real_finish(view, new_state)
            self.record_change(lab.releases / "one", "one", b"foreign-after-finish")
            raced.append(True)
        with patch.object(tx._View, "finish", new=after_finish):
            with self.assertRaisesRegex(RuntimeError, "Externally pinned artifact"):
                pinned.switch("one")
        self.assertTrue(raced)

    def test_06_after_final_byte_check_mutation_reports_false_success(self):
        # P1 POSITIVE VULNERABILITY REPRODUCTION. A mutable artifact can
        # change just after the final comparison but before transaction return.
        genuine = b"approved-by-fixture"
        lab = self.make_lab("lastbyte")
        lab.stage_fixture("one", genuine)
        pinned = self.make_lab("lastbyte", pins={"one":hashlib.sha256(genuine).hexdigest()})
        real_check = tx._View.check_verified_snapshots
        fired = []
        def interleave(view):
            real_check(view)
            self.record_change(lab.releases / "one", "one", b"foreign-after-last-check")
            fired.append(True)
        with patch.object(tx._View, "check_verified_snapshots", new=interleave):
            pinned.switch("one")   # returns success despite modified public source
        self.assertTrue(fired)
        self.assertEqual((lab.releases / "one" / "image.bin").read_bytes(),
                         b"foreign-after-last-check")
        with self.assertRaisesRegex(RuntimeError, "Externally pinned artifact"):
            pinned.status()

    def test_07_verified_bytes_snapshot_is_immutable_but_only_in_memory(self):
        genuine = b"source-read-one-time"
        lab = self.make_lab("snapshot")
        lab.stage_fixture("one", genuine)
        pinned = self.make_lab("snapshot", pins={"one":hashlib.sha256(genuine).hexdigest()})
        with self.assertRaisesRegex(RuntimeError, "Externally pinned artifact"):
            with pinned.locked() as view:
                with self.assertRaisesRegex(RuntimeError, "No validated byte snapshot"):
                    view.verified_bytes("one")
                view.verify_release("one")
                held = view.verified_bytes("one")
                self.assertEqual(held, genuine)
                self.record_change(lab.releases / "one", "one", b"changed-disk-image")
                self.assertEqual(held, genuine)
        self.assertEqual(held, genuine)

    def test_08_unpinned_manifest_is_still_forgeable_not_origin_auth(self):
        lab = self.make_lab("forge")
        lab.stage_fixture("one", b"legitimate")
        trusted = hashlib.sha256(b"legitimate").hexdigest()
        self.record_change(lab.releases / "one", "one", b"malicious-but-self-hashed")
        pinned = self.make_lab("forge", pins={"one":trusted})
        with self.assertRaisesRegex(RuntimeError, "Externally pinned artifact"):
            pinned.switch("one")
        # Unpinned path still treats an untrusted manifest as self-consistent.
        lab.switch("one")
        self.assertEqual(lab.status()["active"], "one")

    def test_09_255_quarantine_slots_fail_without_new_journal(self):
        lab = self.prepared("quota")
        have = self.count_evidence(lab)
        self.assertLessEqual(have, 252)
        for i in range(255-have):
            (lab.root / (".tx-seed-" + str(i))).write_bytes(b"test")
        before = lab.state_path.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "Retained transaction evidence"):
            lab.switch("new")
        self.assertEqual(self.count_evidence(lab), 255)
        self.assertEqual(lab.state_path.read_bytes(), before)
        self.assertFalse(lab.pending.exists())

    def test_10_corrupt_journal_survives_recovery(self):
        lab = self.prepared("corrupt")
        with self.assertRaisesRegex(RuntimeError, "Injected fault"):
            lab.switch("new", fault="after_journal")
        corrupt = b'{"owner":"FOREIGN","before":null,"to":"new"}'
        lab.pending.write_bytes(corrupt)
        with self.assertRaises(RuntimeError):
            lab.recover()
        self.assertEqual(lab.pending.read_bytes(), corrupt)

    def test_11_outer_cooperative_flock_blocks_distinct_base_inode(self):
        lab = self.prepared("flock")
        displaced = self.top / "flock-old-runner"
        child = None
        try:
            with self.assertRaisesRegex(RuntimeError, "Validated runner base namespace changed"):
                with lab.locked():
                    self.base.rename(displaced)
                    self.base.mkdir(mode=0o700)
                    code = "\n".join([
                        "import sys",
                        "from pathlib import Path",
                        "from tools import flight_transaction_lab as tx",
                        "print('READY',flush=True)",
                        "with tx.TransactionLab(Path(sys.argv[1])).locked():",
                        " print('ENTERED',flush=True)",
                    ])
                    child = subprocess.Popen(
                        [sys.executable, "-c", code,
                         str(self.base / "flight-transaction-lab" / "flock")],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        cwd=os.getcwd(), env=os.environ.copy(), close_fds=True)
                    self.assertEqual(child.stdout.readline().strip(), b"READY")
                    time.sleep(0.25)
                    self.assertIsNone(child.poll(), "Critical sections overlapped")
            out, err = child.communicate(timeout=8)
            self.assertEqual(child.returncode, 0, err.decode(errors="replace"))
            self.assertIn(b"ENTERED", out)
        finally:
            if child is not None and child.poll() is None:
                child.kill()
                child.communicate()

if __name__ == "__main__":
    unittest.main(verbosity=2)
