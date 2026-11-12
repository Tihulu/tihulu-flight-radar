#!/usr/bin/env python3
"""Agent 06 independent PR33 security audit: strictly disposable Linux fixtures.

Some tests intentionally PASS when a remaining security weakness is reproduced.
They must never be interpreted as release approval. No real installation,
pipx, sudoers, settings, receiver, SDR or service operation is used.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import sys
import subprocess
import time
import tempfile
import unittest
from unittest.mock import patch
from tools import flight_transaction_lab as tx

@unittest.skipUnless(sys.platform.startswith("linux"), "Linux renameat2 only")
class IndependentPR33QA(unittest.TestCase):
    def setUp(self):
        if (os.environ.get("CI") != "true"
                or os.environ.get("GITHUB_ACTIONS") != "true"
                or not os.environ.get("RUNNER_TEMP")):
            self.skipTest("GitHub-hosted ephemeral runner required")
        self.old_runner = os.environ["RUNNER_TEMP"]
        self.tmp = tempfile.TemporaryDirectory(prefix="flight-agent06-pr33-", dir=self.old_runner)
        self.top = Path(self.tmp.name)
        self.base = self.top / "runner"
        self.base.mkdir(mode=0o700)
        os.environ["RUNNER_TEMP"] = str(self.base)

    def tearDown(self):
        if hasattr(self, "old_runner"):
            os.environ["RUNNER_TEMP"] = self.old_runner
        if hasattr(self, "tmp"):
            self.tmp.cleanup()

    def lab(self, name="scenario", *, pins=None):
        return tx.TransactionLab(self.base / "flight-transaction-lab" / name,
                                 external_pins=pins)

    def prepared(self, name):
        lab = self.lab(name)
        lab.stage_fixture("old", b"old-version")
        lab.stage_fixture("new", b"new-version")
        lab.switch("old")
        return lab

    @staticmethod
    def evidence_count(root):
        return sum(x.startswith((".tx-", ".pointer-", ".retired-"))
                   for x in os.listdir(root))

    def test_01_foreign_displaced_bytes_survive_exchange(self):
        lab = self.prepared("foreign")
        original = tx._rename
        payload = b"FOREIGN-RACE-CONTENT"
        replaced = []
        def attack(fd, src, dst, flag):
            original(fd, src, dst, flag)
            if not replaced and dst == "current" and flag == tx._EXCHANGE:
                os.rename(src, ".saved-pointer",
                          src_dir_fd=fd, dst_dir_fd=fd)
                tx._write_new(fd, src, payload)
                replaced.append(src)
        with patch.object(tx, "_rename", side_effect=attack):
            with self.assertRaisesRegex(RuntimeError, "Foreign file swapped"):
                lab.switch("new")
        self.assertEqual(len(replaced), 1)
        self.assertTrue(any(p.is_file() and not p.is_symlink()
                            and p.read_bytes() == payload
                            for p in lab.root.iterdir()),
                        "Foreign bytes must survive failed exchange and undo")
        self.assertTrue(lab.pending.exists(), "Suspicious journal must remain")

    def test_02_root_replaced_after_pointer_commit_must_fail_closed(self):
        lab = self.prepared("rootswap")
        saved = lab.root.parent / "displaced-root"
        original = tx._rename
        hit = []
        def attack(fd, src, dst, flag):
            original(fd, src, dst, flag)
            if not hit and dst == "current" and flag == tx._EXCHANGE:
                lab.root.rename(saved)
                lab.root.mkdir(mode=0o700)
                (lab.root / "foreign-marker").write_bytes(b"preserve")
                hit.append(True)
        with patch.object(tx, "_rename", side_effect=attack):
            with self.assertRaisesRegex(RuntimeError, "Fixture root namespace changed"):
                lab.switch("new")
        self.assertTrue(hit)
        self.assertEqual((lab.root / "foreign-marker").read_bytes(), b"preserve")
        self.assertEqual(json.loads((saved / "state.json").read_text())["active"], "new")
        self.assertTrue(any(p.name.startswith(".retired-journal-") for p in saved.iterdir()))

    def test_03_base_replaced_after_commit_must_fail_closed(self):
        lab = self.prepared("baseswap")
        saved = self.top / "displaced-base"
        original = tx._rename
        hit = []
        def attack(fd, src, dst, flag):
            original(fd, src, dst, flag)
            if not hit and dst == "current" and flag == tx._EXCHANGE:
                self.base.rename(saved)
                self.base.mkdir(mode=0o700)
                (self.base / "foreign-marker").write_bytes(b"preserve")
                hit.append(True)
        with patch.object(tx, "_rename", side_effect=attack):
            with self.assertRaisesRegex(RuntimeError,
                                       "Validated runner base namespace changed"):
                lab.switch("new")
        self.assertTrue(hit)
        self.assertEqual((self.base / "foreign-marker").read_bytes(), b"preserve")
        self.assertEqual(json.loads((saved / "flight-transaction-lab" /
                                     "baseswap" / "state.json").read_text())["active"], "new")

    def test_04_final_base_reopen_after_fd_swap_fails_closed(self):
        # A hostile actor renames the base after the FIRST exit walk has
        # reopened it, so the SECOND independent walk must notice drift.
        # Later swaps or namespace ABA remain security HOLD.
        lab = self.prepared("endrace")
        saved = self.top / "detached-validated-base"
        original = tx._open_chain
        checks = []
        def attack(path, *, create=False):
            fd = original(path, create=create)
            if os.fspath(path) == os.fspath(self.base):
                checks.append(len(checks) + 1)
                if len(checks) == 4:
                    self.base.rename(saved)
                    self.base.mkdir(mode=0o700)
                    (self.base / "foreign-marker").write_bytes(b"NEW-PATH")
            return fd
        with patch.object(tx, "_open_chain", side_effect=attack):
            with self.assertRaisesRegex(RuntimeError,
                                        "Validated runner base namespace changed"):
                lab.switch("new")
        self.assertEqual(len(checks), 5, "Second exit-check not reached")
        self.assertEqual((self.base / "foreign-marker").read_bytes(), b"NEW-PATH")
        self.assertFalse((self.base / "flight-transaction-lab" / "endrace").exists())
        self.assertEqual(json.loads((saved / "flight-transaction-lab" /
                                     "endrace" / "state.json").read_text())["active"], "new")
        with self.assertRaisesRegex(RuntimeError, "Validated runner base inode changed"):
            lab.status()

    def test_05_external_pins_reject_recomputed_public_self_hash(self):
        original = b"trusted-in-test"
        approved = hashlib.sha256(original).hexdigest()
        lab = self.lab("pins")
        lab.stage_fixture("v1", original)
        pinned = self.lab("pins", pins={"v1": approved})
        pinned.switch("v1")
        image = lab.releases / "v1" / "image.bin"
        manifest = lab.releases / "v1" / "manifest.json"
        evil = b"FORGED-CONTENT"
        image.write_bytes(evil)
        manifest.write_text(json.dumps({"owner": tx.OWNER, "name": "v1",
                      "sha256": hashlib.sha256(evil).hexdigest(), "size": len(evil)}))
        with self.assertRaisesRegex(RuntimeError, "Externally pinned artifact"):
            pinned.status()
        # Empty pins fail closed even if manifest is otherwise valid.
        missing = self.lab("pins", pins={})
        with self.assertRaisesRegex(RuntimeError, "Externally pinned artifact"):
            missing.status()
        # Unpinned self-hash is reproducibly forgeable. This is NOT a PASS.
        self.assertEqual(lab.status()["active"], "v1")

    def test_06_pin_registry_is_defensively_copied(self):
        genuine = b"registered"
        digest = hashlib.sha256(genuine).hexdigest()
        lab = self.lab("copy")
        lab.stage_fixture("v1", genuine)
        source = {"v1": digest}
        pinned = self.lab("copy", pins=source)
        source["v1"] = "0" * 64
        pinned.switch("v1")
        self.assertEqual(pinned.status()["active"], "v1")

    def test_07_verified_pin_after_finish_mutation_fails_closed(self):
        # The original exact-head QA reproduced false SUCCESS here. The new
        # best-effort exit recheck must reject changed source bytes. A hostile
        # same-UID writer can still mutate after the last check: HOLD.
        good = b"known-identity"
        approved = hashlib.sha256(good).hexdigest()
        lab = self.lab("postpin")
        lab.stage_fixture("v1", good)
        pinned = self.lab("postpin", pins={"v1": approved})
        release = lab.releases / "v1"
        old_finish = tx._View.finish
        hit = []
        def attack(view, expected_state):
            old_finish(view, expected_state)
            changed = b"AFTER-FINISH-MUTATION"
            (release / "image.bin").write_bytes(changed)
            (release / "manifest.json").write_text(json.dumps({
                "owner": tx.OWNER, "name": "v1",
                "sha256": hashlib.sha256(changed).hexdigest(), "size": len(changed)}))
            hit.append(True)
        with patch.object(tx._View, "finish", attack):
            with self.assertRaisesRegex(RuntimeError,
                                        "Externally pinned artifact"):
                pinned.switch("v1")
        self.assertTrue(hit)
        with self.assertRaisesRegex(RuntimeError, "Externally pinned artifact"):
            pinned.status()

    def test_08_quarantine_255_fails_before_journal_and_preserves_state(self):
        lab = self.prepared("cap")
        n = self.evidence_count(lab.root)
        for i in range(255-n):
            (lab.root / (".tx-independent-" + str(i))).write_bytes(b"evidence")
        before = lab.state_path.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "Retained transaction evidence"):
            lab.switch("new")
        self.assertEqual(self.evidence_count(lab.root), 255)
        self.assertEqual(lab.state_path.read_bytes(), before)
        self.assertFalse(lab.pending.exists())
        self.assertEqual(os.readlink(lab.current), "releases/old")

    def test_09_quarantine_252_stays_within_cooperative_bound(self):
        lab = self.prepared("capnear")
        n = self.evidence_count(lab.root)
        for i in range(252-n):
            (lab.root / (".tx-independent-" + str(i))).write_bytes(b"evidence")
        lab.switch("new")
        self.assertLessEqual(self.evidence_count(lab.root), 256)
        self.assertEqual(lab.status()["active"], "new")
        with self.assertRaisesRegex(RuntimeError, "Retained transaction evidence"):
            lab.switch("old")

    def test_10_corrupt_recovery_journal_survives(self):
        lab = self.prepared("journal")
        with self.assertRaisesRegex(RuntimeError, "Injected fault"):
            lab.switch("new", fault="after_journal")
        bad = b'{"owner":"FOREIGN","before":null,"to":"new"}'
        lab.pending.write_bytes(bad)
        with self.assertRaises(RuntimeError):
            lab.recover()
        self.assertEqual(lab.pending.read_bytes(), bad)


    def test_11_replaced_base_cannot_split_cooperative_processes(self):
        # Real child process has a freshly opened "/" FD, not inherited locks.
        # A separately named replacement RUNNER_TEMP cannot create a
        # concurrent critical section while the original root flock exists.
        lab = self.prepared("parallel")
        displaced = self.top / "parallel-original-base"
        child = None
        try:
            with self.assertRaisesRegex(RuntimeError,
                                       "Validated runner base namespace changed"):
                with lab.locked():
                    self.base.rename(displaced)
                    self.base.mkdir(mode=0o700)
                    script = "\n".join([
                        "import sys",
                        "from pathlib import Path",
                        "from tools import flight_transaction_lab as tx",
                        "print('READY', flush=True)",
                        "with tx.TransactionLab(Path(sys.argv[1])).locked():",
                        " print('ENTERED', flush=True)",
                    ])
                    child = subprocess.Popen(
                        [sys.executable, "-c", script,
                         str(self.base / "flight-transaction-lab" / "parallel")],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        env=os.environ.copy(), cwd=os.getcwd(), close_fds=True)
                    self.assertEqual(child.stdout.readline().strip(), b"READY")
                    time.sleep(0.3)
                    self.assertIsNone(child.poll(),
                                      "Second lab entered before first lock released")
            out, err = child.communicate(timeout=8)
            self.assertEqual(child.returncode, 0, err.decode(errors="replace"))
            self.assertIn(b"ENTERED", out)
            self.assertTrue(displaced.is_dir())
        finally:
            if child is not None and child.poll() is None:
                child.kill()
                child.communicate()

    def test_12_verified_byte_snapshot_survives_mutation(self):
        # The verified object handed to a hypothetical installer must not be
        # a user-writable path reopened after verification. This CI-only
        # bytes object demonstrates immutable handoff, NOT signed provenance.
        trusted = b"verified-immutable-source"
        approved = hashlib.sha256(trusted).hexdigest()
        lab = self.lab("snapshot")
        lab.stage_fixture("v1", trusted)
        pinned = self.lab("snapshot", pins={"v1": approved})
        release = lab.releases / "v1"
        with self.assertRaisesRegex(RuntimeError,
                                    "Externally pinned artifact"):
            with pinned.locked() as view:
                view.verify_release("v1")
                snapshot = view.verified_bytes("v1")
                self.assertIs(type(snapshot), bytes)
                self.assertEqual(snapshot, trusted)
                tampered = b"post-verify-path-content"
                (release / "image.bin").write_bytes(tampered)
                (release / "manifest.json").write_text(json.dumps({
                    "owner": tx.OWNER, "name": "v1",
                    "sha256": hashlib.sha256(tampered).hexdigest(),
                    "size": len(tampered)}))
                self.assertEqual(snapshot, trusted,
                                 "Verified bytes must not change with source")
        self.assertEqual(snapshot, trusted)

    def test_13_snapshot_rejects_unverified_release(self):
        lab = self.lab("notverified")
        lab.stage_fixture("v1", b"stored")
        with lab.locked() as view:
            with self.assertRaisesRegex(RuntimeError,
                                        "No validated byte snapshot"):
                view.verified_bytes("v1")
            view.verify_release("v1")
            self.assertEqual(view.verified_bytes("v1"), b"stored")

    def test_14_unpinned_snapshot_detects_in_place_change_at_exit(self):
        # Unpinned dummy fixtures still lack origin authentication but can
        # detect post-validation changes within one cooperative transaction.
        lab = self.lab("unpinexit")
        lab.stage_fixture("v1", b"initial")
        with self.assertRaisesRegex(RuntimeError,
                                    "Verified fixture bytes changed"):
            with lab.locked() as view:
                view.verify_release("v1")
                old = view.verified_bytes("v1")
                changed = b"changed"
                path = lab.releases / "v1"
                (path / "image.bin").write_bytes(changed)
                (path / "manifest.json").write_text(json.dumps({
                    "owner": tx.OWNER, "name": "v1",
                    "sha256": hashlib.sha256(changed).hexdigest(),
                    "size": len(changed)}))
        self.assertEqual(old, b"initial")


if __name__ == "__main__":
    unittest.main(verbosity=2)
