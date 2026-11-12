"""Independent QA evidence for PR #27. All mutations are disposable CI fixtures.

These evidence tests intentionally assert CURRENT vulnerable behavior. They are not
security acceptance tests and MUST NOT be interpreted as production PASS.
No real installation paths, system services, receiver devices, or user data.
"""
import hashlib
import json
import os
import stat
from pathlib import Path

import pytest

import tools.flight_transaction_lab as tx


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    return tx.TransactionLab(tmp_path / "flight-transaction-lab" / "qa")


def test_evidence_recover_corrupt_before_can_destroy_only_journal(lab):
    lab.stage_fixture("old", b"old")
    lab.stage_fixture("new", b"new")
    lab.switch("old")
    with pytest.raises(RuntimeError, match="Injected fault"):
        lab.switch("new", fault="after_journal")
    journal = json.loads(lab.pending.read_text())
    journal["before"]["owner"] = "FOREIGN"
    lab.pending.write_text(json.dumps(journal))
    with pytest.raises(RuntimeError, match="Foreign or corrupt transaction state"):
        lab.recover()
    assert not lab.pending.exists(), "Recover removed the only journal before validation"
    with pytest.raises(RuntimeError, match="Foreign or corrupt transaction state"):
        lab.status()


def test_evidence_foreign_current_entry_overwritten_in_race(lab, monkeypatch):
    lab.stage_fixture("old", b"old")
    lab.stage_fixture("new", b"new")
    lab.switch("old")
    real_replace = tx.os.replace
    injected = []
    def race_replace(source, destination):
        if Path(destination) == lab.current:
            lab.current.unlink()
            lab.current.write_bytes(b"FOREIGN_CURRENT_DATA")
            injected.append(True)
        return real_replace(source, destination)
    monkeypatch.setattr(tx.os, "replace", race_replace)
    lab.switch("new")
    assert injected, "Expected synthetic race point not reached"
    assert lab.current.is_symlink()
    assert lab.status()["active"] == "new"


def test_evidence_foreign_state_entry_overwritten_in_race(lab, monkeypatch):
    lab.stage_fixture("new", b"new")
    real_atomic = tx._write_atomic
    injected = []
    def race_atomic(path, content):
        if Path(path) == lab.state_path:
            lab.state_path.write_bytes(b"FOREIGN_STATE_DATA")
            injected.append(True)
        return real_atomic(path, content)
    monkeypatch.setattr(tx, "_write_atomic", race_atomic)
    lab.switch("new")
    assert injected
    assert b"FOREIGN_STATE_DATA" not in lab.state_path.read_bytes()
    assert lab.status()["active"] == "new"


def test_evidence_rollback_nonserializable_interleaving(lab, monkeypatch):
    for name in ("old", "new", "third"):
        lab.stage_fixture(name, name.encode())
    lab.switch("old")
    lab.switch("new")
    real_switch = lab.switch
    interleaved = []
    def race_switch(name, **kwargs):
        if name == "old" and not interleaved:
            interleaved.append(True)
            real_switch("third")
        return real_switch(name, **kwargs)
    monkeypatch.setattr(lab, "switch", race_switch)
    lab.rollback()
    assert interleaved
    state = lab.status()
    assert (state["active"], state["previous"]) == ("old", "third")
    # A serial rollback before the third switch would end at third.
    # A serial rollback after the third switch would end at new.
    assert state["active"] not in ("new", "third")


def test_evidence_public_marker_allows_recomputed_foreign_fixture(lab):
    lab.stage_fixture("v1", b"original")
    payload = lab.releases / "v1" / "image.bin"
    marker = lab.releases / "v1" / "manifest.json"
    payload.write_bytes(b"forged")
    record = {"owner": tx.OWNER, "name": "v1",
              "sha256": hashlib.sha256(b"forged").hexdigest(),
              "size": len(b"forged")}
    marker.write_text(json.dumps(record))
    lab.switch("v1")
    assert lab.status()["active"] == "v1"


def test_evidence_unchecked_ancestor_symlink_under_runner_temp(tmp_path, monkeypatch):
    outside = tmp_path / "outside"
    (outside / "runner").mkdir(parents=True)
    alias = tmp_path / "alias"
    alias.symlink_to(outside, target_is_directory=True)
    base = alias / "runner"
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("RUNNER_TEMP", str(base))
    lab = tx.TransactionLab(base / "flight-transaction-lab" / "case")
    lab.stage_fixture("one", b"dummy")
    assert (outside / "runner" / "flight-transaction-lab" / "case" / "releases" / "one" / "image.bin").exists()


def test_evidence_writable_fixture_root_not_rejected(lab):
    lab.stage_fixture("one", b"one")
    lab.root.chmod(0o777)
    assert stat.S_IMODE(lab.root.stat().st_mode) == 0o777
    assert lab.status()["active"] is None


def test_evidence_switch_does_not_fsync_parent_directory(lab, monkeypatch):
    lab.stage_fixture("one", b"one")
    real_fsync = tx.os.fsync
    calls = []
    def track_fsync(fd):
        calls.append(stat.S_ISDIR(os.fstat(fd).st_mode))
        return real_fsync(fd)
    monkeypatch.setattr(tx.os, "fsync", track_fsync)
    lab.switch("one")
    assert calls and not any(calls), "Only files, not containing dirs, were fsynced"


def test_evidence_orphan_stage_has_no_reaper(lab):
    lab.stage_fixture("one", b"one")
    orphan = lab.releases / ".stage-orphaned"
    orphan.mkdir()
    (orphan / "image.bin").write_bytes(b"abandoned")
    lab.stage_fixture("two", b"two")
    assert orphan.exists(), "Orphaned stage remains after next transaction"


def test_evidence_fake_pipx_archive_settings_noninterference(lab, tmp_path):
    fake = tmp_path / "protected-user-home"
    sentinels = {
        fake / ".local/pipx/venvs/tihulu-flight-radar/installed.marker": b"pipx intact",
        fake / ".config/Tihulu/Flight Radar.conf": b"QSettings intact",
        fake / "Archives/flight-0.3.1.tar": b"0.3.1 preserved",
        fake / ".local/share/tihulu-flight-radar/recordings/index": b"userdata preserved",
    }
    for path, payload in sentinels.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    baseline = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sentinels}
    lab.stage_fixture("one", b"one")
    lab.stage_fixture("two", b"two")
    lab.switch("one")
    lab.switch("two", fault="after_pointer") if False else None
    lab.switch("two")
    lab.rollback()
    assert {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sentinels} == baseline


def test_evidence_just_env_flags_do_not_attest_github_runner(lab):
    # In real use these environment variables can be set by any local process.
    assert os.environ["GITHUB_ACTIONS"] == "true"
    assert os.environ["CI"] == "true"
    assert lab.status()["owner"] == tx.OWNER
