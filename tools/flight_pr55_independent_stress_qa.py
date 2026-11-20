#!/usr/bin/env python3
"""Independent PR55 multi-UID stress QA — disposable GitHub-hosted Linux ONLY.

Real root broker subprocess and genuine exec'd UID65534 hostile clients.
Does NOT modify frozen PR #55/#54/#53 or any predecessor. Adds ONLY this QA
file and its workflow. A green result is scoped CI acceptance of the tested
protocol; it is never production security clearance, human consent, or an
OS-trust-boundary claim.
"""
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
import unittest

from tools import flight_p1_broker_pr52_remediation_ci as v2
from tools import flight_p1_broker_os_boundary_ci as old
from tools import flight_p1_broker_pr52_remediation_tests as tests
from tools import flight_p1_broker_os_boundary_tests as linux

BLOB = linux.BLOB
BROKER_SOURCE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "flight_p1_broker_pr52_remediation_ci.py")

HALF_SEND = r"""
import socket, sys, time
frame = open(sys.argv[2], "rb").read()
s = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
s.connect(sys.argv[1])
s.send(frame[: max(1, len(frame) // 2)])
time.sleep(0.05)
s.close()
print("HALF_SENT", flush=True)
"""

NO_RECV_CLIENT = r"""
import array, fcntl, json, os, socket, sys, time
from pathlib import Path
frame = Path(sys.argv[2]).read_bytes()
data = Path(sys.argv[3]).read_bytes()
fd = os.memfd_create("stress-no-recv", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
try:
    os.write(fd, data)
    fcntl.fcntl(fd, fcntl.F_ADD_SEALS,
                fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL)
    s = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    s.connect(sys.argv[1])
    s.sendmsg([frame], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [fd]))])
    time.sleep(0.4)  # let the broker process+commit; the client then vanishes
    s.close()  # die WITHOUT reading any reply; server-side state is the evidence
    print(json.dumps({"ok": True, "note": "closed before reply"}), flush=True)
finally:
    os.close(fd)
"""


def broker_fd_count(pid):
    return len(os.listdir("/proc/%d/fd" % pid))


@unittest.skipUnless(sys.platform == "linux", "Linux separate-UID acceptance")
class AgentPR55IndependentStressQA(unittest.TestCase):
    """Independent multi-UID stress evidence; helpers reused like the QA #54 file."""

    setUp = tests.PR52RemediationAcceptance.setUp
    start_server = tests.PR52RemediationAcceptance.start_server
    stop_server = tests.PR52RemediationAcceptance.stop_server
    frame_v2 = tests.PR52RemediationAcceptance.frame_v2
    reframe = staticmethod(tests.PR52RemediationAcceptance.reframe)
    parked_client = tests.PR52RemediationAcceptance.parked_client
    grant = tests.PR52RemediationAcceptance.grant
    resume = tests.PR52RemediationAcceptance.resume
    cut_as_approved = tests.PR52RemediationAcceptance.cut_as_approved
    sealed_fd = tests.PR52RemediationAcceptance.sealed_fd
    make_files = tests.PR52RemediationAcceptance.make_files
    request = tests.PR52RemediationAcceptance.request
    unpriv_action = tests.PR52RemediationAcceptance.unpriv_action
    active = tests.PR52RemediationAcceptance.active
    ledger = tests.PR52RemediationAcceptance.ledger

    def protected(self):
        model = v2.BrokerV2(self.root)
        self.addCleanup(model.close)
        return model

    def prep_file(self):
        return self.root/"private"/"prepared"/"prep-00000000000000000050.json"

    def blob_file(self, data=BLOB):
        return self.root/"private"/"release"/(
            "rel-%020d-%s.bin" % (50, v2.dig(data)[:16]))

    def handoff_file(self):
        return self.root/"private"/"handoff"/"transfer-00000000000000000050.json"

    def kill_original(self, p):
        os.kill(p.pid, signal.SIGKILL)
        p.wait(timeout=5)
        self.assertIsNotNone(p.returncode)

    def prepare_with_dead_original(self, cut="after_release"):
        frame, blob, parts = self.frame_v2()
        oldclient = self.parked_client(frame, blob)
        self.grant(oldclient, parts)
        self.stop_server()
        self.cut_as_approved(oldclient, parts, cut=cut)
        self.assertIsNone(self.active())
        self.assertEqual(self.ledger(), [])
        receipt = self.prep_file().read_bytes()
        self.kill_original(oldclient)
        return receipt, blob, parts

    def new_approved(self, **kwargs):
        frame, blob, parts = self.frame_v2(**kwargs)
        replacement = self.parked_client(frame, blob)
        self.grant(replacement, parts)
        return replacement, parts, blob

    def transfer(self, recipient, parts):
        b = self.protected()
        return b.authorize_takeover_from_root_test_authority(
            *parts, recipient.pid, now=old.CI_NOW)

    # 1. Slow/half-send storm: accept loop survives, nothing commits, and a
    #    later root-approved transaction still succeeds on the SAME broker.
    # Catches: accept-loop death or partial-frame processing on malformed/short messages; also that nothing commits without root approval.
    def test_01_half_send_and_slow_client_storm_keeps_broker_alive(self):
        for _ in range(15):
            frame, data, _ = self.frame_v2()
            frame_file, _ = self.make_files(frame, data)
            result = self.unpriv_action(
                r"""
import socket, sys, time
frame = open(sys.argv[2], "rb").read()
s = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
s.connect(sys.argv[1])
s.send(frame[: max(1, len(frame) // 2)])
time.sleep(0.05)
s.close()
print("HALF_SENT", flush=True)
""", self.sock, frame_file)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("HALF_SENT", result.stdout)
            self.assertIsNone(self.worker.poll())
        self.assertEqual(self.ledger(), [])
        frame, blob, parts = self.frame_v2()
        authorized = self.parked_client(frame, blob)
        self.grant(authorized, parts)
        self.assertTrue(self.resume(authorized)["ok"])
        self.assertIsNone(self.worker.poll())
        self.assertEqual(self.active()["seq"], 50)

    # 2. Abandoned FD-passing clients: broker must close received descriptors.
    # Catches: broker descriptor leak when FD-passing clients vanish mid-session (threshold ~12 tolerates constant stdio/accept noise, not per-connection growth).
    def test_02_abandoned_fd_clients_do_not_leak_descriptors(self):
        baseline = broker_fd_count(self.worker.pid)
        frame, data, _ = self.frame_v2()
        for _ in range(25):
            reply = self.request(frame, data)  # one-shot UID65534 + SCM_RIGHTS
            self.assertFalse(reply["ok"])
            self.assertIn("root-side", reply["error"])
        after = broker_fd_count(self.worker.pid)
        self.assertLess(after - baseline, 12,
                        "broker descriptor growth: %d -> %d" % (baseline, after))
        self.assertIsNone(self.worker.poll())
        self.assertEqual(self.ledger(), [])

    # 3. Client dies right after a VALID commit, before reading the reply:
    #    state stays consistent and a stale replay of the same frame is denied.
    # Catches: state divergence when a client dies right after commit (ledger/active are the server-side evidence); stale replay must be denied. Client stdout is deliberately NOT trusted.
    def test_03_client_death_after_commit_keeps_state_consistent(self):
        frame, blob, parts = self.frame_v2()
        victim = self.parked_client(frame, blob, code=NO_RECV_CLIENT)
        self.grant(victim, parts)
        reply = self.resume(victim)
        # The client never reads the broker reply; its stdout is NOT evidence
        # of the broker decision. Server-side durable state is the evidence.
        self.assertEqual(reply.get("note"), "closed before reply")
        self.assertIsNone(self.worker.poll())
        self.assertEqual(len(self.ledger()), 1)
        self.assertEqual(self.active()["seq"], 50)
        self.assertFalse(self.handoff_file().exists())
        again = self.request(frame, blob)
        self.assertFalse(again["ok"])
        self.assertEqual(len(self.ledger()), 1)

    # Catches: broker unavailability or privilege drift after mixed hostile traffic; exactly one commit and unchanged semantics afterward.
    def test_04_signed_acceptance_after_mixed_hostile_storm(self):
        disconnects = r"""
import socket, sys
s = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
s.connect(sys.argv[1]); s.shutdown(socket.SHUT_RDWR); s.close()
print("BYE", flush=True)
"""
        malformed = r"""
import socket, sys
s = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
s.connect(sys.argv[1]); s.send(b"\x00\x01not-a-frame"); s.close()
print("JUNK", flush=True)
"""
        for code in (disconnects, malformed):
            for _ in range(10):
                result = self.unpriv_action(code, self.sock)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIsNone(self.worker.poll())
        for _ in range(5):
            frame, data, _ = self.frame_v2()
            frame_file, _ = self.make_files(frame, data)
            result = self.unpriv_action(HALF_SEND, self.sock, frame_file)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIsNone(self.worker.poll())
        frame, blob, parts = self.frame_v2()
        authorized = self.parked_client(frame, blob)
        self.grant(authorized, parts)
        self.assertTrue(self.resume(authorized)["ok"])
        self.assertIsNone(self.worker.poll())
        self.assertEqual(self.active()["seq"], 50)
        self.assertEqual(len(self.ledger()), 1)

    # 5. A SECOND distinct root-approved recipient stays denied after a
    #    completed handoff, even across a broker restart.
    # Catches: a second root-approved recipient adopting an already-completed transfer, or handoff/prepared bytes mutating after denial (checked across a restart).
    def test_05_second_recipient_after_completed_handoff_denied(self):
        original, blob, _ = self.prepare_with_dead_original()
        authorized, parts, _ = self.new_approved()
        first = self.transfer(authorized, parts)
        firstraw = self.handoff_file().read_bytes()
        self.assertEqual(first["from_nonce"] != first["to_nonce"], True)
        other, partstwo, _ = self.new_approved()
        with self.assertRaisesRegex(old.Denied, "different/foreign transfer"):
            self.transfer(other, partstwo)
        self.assertEqual(self.handoff_file().read_bytes(), firstraw)
        self.assertEqual(self.prep_file().read_bytes(), original)
        self.start_server()
        self.assertFalse(self.resume(other)["ok"])
        self.assertTrue(self.resume(authorized)["ok"])
        self.assertEqual(self.active()["seq"], 50)

    # 6. A takeover may NOT reuse the dead original's PID as the recipient.
    # Catches: takeover authorization reusing the dead original's PID number; the existing handoff bytes must stay identical after the denied attempt.
    def test_06_dead_original_pid_reuse_denied(self):
        # A takeover recipient must be a NEW, independently root-approved,
        # live session. Reusing the dead original's PID number must fail,
        # even with otherwise valid old/new signed parts.
        frame, blob, parts = self.frame_v2()
        oldclient = self.parked_client(frame, blob)
        original_grant = self.grant(oldclient, parts)
        self.stop_server()
        self.cut_as_approved(oldclient, parts, cut="after_release")
        self.assertIsNone(self.active())
        self.assertEqual(self.ledger(), [])
        self.kill_original(oldclient)
        authorized, newparts, _ = self.new_approved()
        first = self.transfer(authorized, newparts)  # legitimate transfer first
        handoff_before = self.handoff_file().read_bytes()
        dead_pid = original_grant["pid"]
        self.assertNotEqual(dead_pid, authorized.pid)
        with self.assertRaises(old.Denied):
            self.transfer_pid(dead_pid, newparts)
        self.assertEqual(self.handoff_file().read_bytes(), handoff_before)

    def transfer_pid(self, replacement_pid, parts):
        b = self.protected()
        return b.authorize_takeover_from_root_test_authority(
            *parts, replacement_pid, now=old.CI_NOW)

    # 7. Broker restart after a commit replays durably and idempotently.
    # Catches: non-durable journal state or replay acceptance after a broker restart (ledger stays 1, same-frame retry denied).
    def test_07_broker_restart_after_commit_replays_idempotently(self):
        frame, blob, parts = self.frame_v2()
        client = self.parked_client(frame, blob)
        self.grant(client, parts)
        self.assertTrue(self.resume(client)["ok"])
        self.stop_server()
        self.start_server()
        self.assertEqual(len(self.ledger()), 1)
        self.assertEqual(self.active()["seq"], 50)
        self.assertFalse(self.handoff_file().exists())
        replay = self.request(frame, blob)
        self.assertFalse(replay["ok"])
        self.assertEqual(len(self.ledger()), 1)
        self.assertIsNone(self.worker.poll())

    # 8. POSITIVE LIMIT witness: no trusted time source exists; freshness and
    #    replay floors are caller-supplied policy, not OS/kernel trust.
    # HOLD witness: documents that the broker trusts no ambient wall clock (CI_NOW is harness policy), not a security clearance.
    def test_08_no_trusted_time_source_is_documented_limit(self):
        source = open(BROKER_SOURCE, "r", encoding="utf-8").read()
        self.assertIn("CI_NOW", source)  # clock is harness-supplied policy
        for banned in ("time.time()", "datetime.now(", "datetime.utcnow(",
                       "clock_gettime("):
            self.assertNotIn(banned, source,
                             "broker must not trust ambient wall clock: " + banned)

    # 9. During a storm, UID65534 still cannot fabricate a protected handoff.
    # Catches: kernel DAC bypass for unprivileged handoff fabrication under load (UID65534 write denied; no forged file).
    def test_09_handoff_write_denied_during_storm(self):
        disconnects = (
            "import socket,sys\n"
            "s=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET)\n"
            "s.connect(sys.argv[1]);s.close();print('BYE',flush=True)\n")
        target = self.root/"private"/"handoff"
        for _ in range(10):
            result = self.unpriv_action(disconnects, self.sock)
            self.assertEqual(result.returncode, 0, result.stderr)
            attack = self.unpriv_action(
                "from pathlib import Path\n"
                "import sys\n"
                "try:\n"
                " Path(sys.argv[1]+'/forged.json').write_bytes(b'ATTACK')\n"
                " print('WROTE')\n"
                "except OSError as error:\n"
                " print('DENIED', type(error).__name__)\n", target)
            self.assertNotIn("WROTE", attack.stdout)
            self.assertIn("DENIED", attack.stdout)
        self.assertFalse((target/"forged.json").exists())
        self.assertIsNone(self.worker.poll())

    # 10. POSITIVE LIMIT witness: no admission/rate control exists; sustained
    #     hostile connection volume is not throttled in this CI prototype.
    # HOLD witness: documents the ABSENCE of admission/rate control (30/30 hostile connections accepted); availability hardening remains open.
    def test_10_availability_rate_limits_absent_positive_limit(self):
        source = open(BROKER_SOURCE, "r", encoding="utf-8").read()
        for marker in ("token_bucket", "rate_limit", "admission_control",
                       "too_many_connections"):
            self.assertNotIn(marker, source)
        accepted = 0
        disconnects = (
            "import socket,sys\n"
            "s=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET)\n"
            "s.connect(sys.argv[1]);s.close();print('BYE',flush=True)\n")
        for _ in range(30):
            result = self.unpriv_action(disconnects, self.sock)
            self.assertEqual(result.returncode, 0, result.stderr)
            accepted += 1
        self.assertEqual(accepted, 30)  # no throttling = documented P2/HOLD
        self.assertIsNone(self.worker.poll())


if __name__ == "__main__":
    unittest.main(verbosity=2)
