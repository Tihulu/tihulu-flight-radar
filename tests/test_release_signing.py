"""Release signing, ledger decisions and anti-rollback - openssl Ed25519."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[1] / "tools" / "release_signing.py"
SHA1 = "a" * 40
SHA2 = "b" * 40


@pytest.fixture(scope="module")
def key(tmp_path_factory):
    out = tmp_path_factory.mktemp("rootkey")
    info = subprocess.run([sys.executable, str(TOOL), "keygen",
                           "--out-dir", str(out)], capture_output=True, text=True)
    assert info.returncode == 0, info.stderr
    private = out / "root-private.pem"
    public = out / "root-public.pem"
    assert (os.stat(private).st_mode & 0o777) == 0o600
    assert "fingerprint" in info.stdout
    return private, public


def _append(tool, key, tmp_path, **kwargs):
    cmd = [sys.executable, str(tool), "ledger", "append",
           "--key", str(key), "--version", "0.3.2.dev4",
           "--tag", "desktop-test", "--source-sha", SHA1]
    for name, value in kwargs.items():
        cmd += ["--" + name.replace("_", "-"), value]
    return subprocess.run(cmd, cwd=tmp_path, capture_output=True, text=True)


def test_keygen_and_fingerprint(key):
    private, public = key
    out = subprocess.run([sys.executable, str(TOOL), "fingerprint",
                          "--pub", str(public)], capture_output=True, text=True)
    assert out.returncode == 0 and len(out.stdout.strip()) == 32


def test_sign_verify_roundtrip(key, tmp_path):
    private, public = key
    manifest = tmp_path / "SHA256SUMS"
    manifest.write_text("deadbeef  some-file\n", encoding="utf-8")
    signed = subprocess.run([sys.executable, str(TOOL), "sign",
                             "--key", str(private), "--file", str(manifest)],
                            capture_output=True, text=True)
    assert signed.returncode == 0, signed.stderr
    assert manifest.with_suffix(manifest.suffix + ".sig").exists()
    ok = subprocess.run([sys.executable, str(TOOL), "verify", "--pub",
                         str(public), "--file", str(manifest),
                         "--sig", str(manifest.with_suffix(manifest.suffix + ".sig"))],
                        capture_output=True, text=True)
    assert ok.returncode == 0 and "VALID" in ok.stdout
    manifest.write_text("evil  some-file\n", encoding="utf-8")
    bad = subprocess.run([sys.executable, str(TOOL), "verify", "--pub",
                          str(public), "--file", str(manifest),
                          "--sig", str(manifest.with_suffix(manifest.suffix + ".sig"))],
                         capture_output=True, text=True)
    assert bad.returncode == 1 and "INVALID" in bad.stdout


def test_ledger_append_chain_and_duplicate_refusal(key, tmp_path):
    private, public = key
    first = _append(TOOL, private, tmp_path, note="initial")
    assert first.returncode == 0, first.stderr
    assert "seq 1" in first.stdout
    ledger = json.loads((tmp_path / "versions/releases/ledger.json").read_text())
    assert ledger["entries"][0]["seq"] == 1
    assert ledger["entries"][0]["prev_seq"] == 0
    again = _append(TOOL, private, tmp_path, source_sha=SHA1)
    assert again.returncode != 0  # duplicate source_sha refused
    bad_sha = subprocess.run([sys.executable, str(TOOL), "ledger", "append",
                              "--key", str(private), "--version", "0.3.2.dev4",
                              "--tag", "t", "--source-sha", "notasha"],
                             cwd=tmp_path, capture_output=True, text=True)
    assert bad_sha.returncode != 0


def test_ledger_check_allow_unknown_rollback_and_tombstone(key, tmp_path):
    private, public = key
    _append(TOOL, private, tmp_path)
    # approved
    ok = subprocess.run([sys.executable, str(TOOL), "ledger", "check", "--pub",
                         str(public), "--source-sha", SHA1], cwd=tmp_path,
                        capture_output=True, text=True)
    assert ok.returncode == 0 and "LEDGER seq=1" in ok.stdout
    # unknown source refused (exit 2)
    unknown = subprocess.run([sys.executable, str(TOOL), "ledger", "check", "--pub",
                              str(public), "--source-sha", SHA2], cwd=tmp_path,
                             capture_output=True, text=True)
    assert unknown.returncode == 2 and "not-in-ledger" in unknown.stdout
    # rollback refusal: installed seq 2, requesting seq 1 must be refused.
    second = subprocess.run([sys.executable, str(TOOL), "ledger", "append",
                              "--key", str(private), "--version", "0.3.2.dev4",
                              "--tag", "t2", "--source-sha", SHA2], cwd=tmp_path,
                             capture_output=True, text=True)
    assert second.returncode == 0
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"seq": 2}), encoding="utf-8")
    roll = subprocess.run([sys.executable, str(TOOL), "ledger", "check", "--pub",
                           str(public), "--source-sha", SHA1,
                           "--state-file", str(state)], cwd=tmp_path,
                          capture_output=True, text=True)
    assert roll.returncode == 2 and "rollback" in roll.stdout
    allowed = subprocess.run([sys.executable, str(TOOL), "ledger", "check", "--pub",
                              str(public), "--source-sha", SHA1,
                              "--state-file", str(state), "--allow-rollback"],
                             cwd=tmp_path, capture_output=True, text=True)
    assert allowed.returncode == 0 and "rollback" in allowed.stdout
    # tombstone: revoke SHA2, then it is refused even explicitly
    rev = subprocess.run([sys.executable, str(TOOL), "ledger", "append", "--key",
                          str(private), "--version", "0.3.2.dev4", "--tag", "t2",
                          "--source-sha", SHA2, "--revoke"], cwd=tmp_path,
                         capture_output=True, text=True)
    assert rev.returncode == 0
    dead = subprocess.run([sys.executable, str(TOOL), "ledger", "check", "--pub",
                           str(public), "--source-sha", SHA2,
                           "--allow-rollback"], cwd=tmp_path,
                          capture_output=True, text=True)
    assert dead.returncode == 2 and "revoked" in dead.stdout


def test_tampered_ledger_refuses_everything(key, tmp_path):
    private, public = key
    _append(TOOL, private, tmp_path)
    ledger = tmp_path / "versions/releases/ledger.json"
    data = json.loads(ledger.read_text())
    data["entries"][0]["version"] = "0.0.0-evil"
    ledger.write_text(json.dumps(data, indent=2), encoding="utf-8")
    check = subprocess.run([sys.executable, str(TOOL), "ledger", "check", "--pub",
                            str(public), "--source-sha", SHA1], cwd=tmp_path,
                           capture_output=True, text=True)
    assert check.returncode == 1
    assert "INVALID" in check.stderr
