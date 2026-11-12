"""Agent 07 regression acceptance: replaces Agent 06 vulnerability demonstrations.

Tests operate ONLY on disposable GitHub-runner tmp_path fixtures, no real host
or installed application. A PASS means the named simulated boundary was held;
it does not prove resistance to a malicious same-UID actor or power loss.
"""
import hashlib
import json
import multiprocessing
import os
import stat
import sys

import pytest
import tools.flight_transaction_lab as tx

pytestmark = pytest.mark.skipif(sys.platform != "linux",
                                reason="POSIX descriptor/renameat2 test only")


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    return tx.TransactionLab(tmp_path / "flight-transaction-lab" / "qa")


def _prepare(lab):
    lab.stage_fixture("old", b"old")
    lab.stage_fixture("new", b"new")
    lab.switch("old")


def test_invalid_before_keeps_journal_and_old_state(lab):
    _prepare(lab)
    with pytest.raises(RuntimeError, match="Injected fault"):
        lab.switch("new", fault="after_journal")
    state_before = lab.state_path.read_bytes()
    journal = json.loads(lab.pending.read_text())
    journal["before"]["owner"] = "FOREIGN"
    lab.pending.write_text(json.dumps(journal))
    expected_journal = lab.pending.read_bytes()
    with pytest.raises(RuntimeError, match="Foreign or corrupt transaction state"):
        lab.recover()
    assert lab.pending.read_bytes() == expected_journal
    assert lab.state_path.read_bytes() == state_before
    assert os.readlink(lab.current) == "releases/old"


@pytest.mark.parametrize("bad", [
    {"before": {"owner": tx.OWNER, "active": "../escape", "previous": None}},
    {"to": "../../escape"},
    {"unexpected": "extra"},
    {"before": {"owner": tx.OWNER, "active": None}},
])
def test_invalid_journal_schema_refuses_without_mutation(lab, bad):
    _prepare(lab)
    with pytest.raises(RuntimeError, match="Injected fault"):
        lab.switch("new", fault="after_journal")
    source = json.loads(lab.pending.read_text())
    source.update(bad)
    lab.pending.write_text(json.dumps(source))
    before = lab.state_path.read_bytes()
    with pytest.raises((RuntimeError, TypeError, KeyError)):
        lab.recover()
    assert lab.pending.exists()
    assert lab.state_path.read_bytes() == before


def test_duplicate_json_keys_refused(lab):
    _prepare(lab)
    with pytest.raises(RuntimeError):
        lab.switch("new", fault="after_journal")
    lab.pending.write_bytes(b'{"owner":"A","owner":"B"}')
    with pytest.raises(RuntimeError, match="Duplicate JSON key"):
        lab.recover()
    assert lab.pending.is_file()


def test_foreign_current_swap_is_not_overwritten(lab, monkeypatch):
    _prepare(lab)
    rename = tx._rename
    injected = []
    def race(fd, src, dst, flag):
        if dst == "current" and flag == tx._EXCHANGE and not injected:
            lab.current.unlink()
            lab.current.write_bytes(b"FOREIGN_CURRENT_DATA")
            injected.append(True)
        return rename(fd, src, dst, flag)
    monkeypatch.setattr(tx, "_rename", race)
    with pytest.raises(RuntimeError, match="Foreign"):
        lab.switch("new")
    assert injected
    assert lab.current.read_bytes() == b"FOREIGN_CURRENT_DATA"
    assert lab.pending.exists()
    assert json.loads(lab.state_path.read_text())["active"] == "old"


def test_foreign_state_swap_is_not_overwritten(lab, monkeypatch):
    _prepare(lab)
    rename = tx._rename
    injected = []
    def race(fd, src, dst, flag):
        if dst == "state.json" and flag == tx._EXCHANGE and not injected:
            lab.state_path.unlink()
            lab.state_path.write_bytes(b"FOREIGN_STATE_DATA")
            injected.append(True)
        return rename(fd, src, dst, flag)
    monkeypatch.setattr(tx, "_rename", race)
    with pytest.raises(RuntimeError, match="Foreign|Changed protected state"):
        lab.switch("new")
    assert injected
    assert lab.state_path.read_bytes() == b"FOREIGN_STATE_DATA"
    assert lab.pending.exists()


def test_deactivation_race_preserves_foreign_current(lab, monkeypatch):
    _prepare(lab)
    rename = tx._rename
    injected = []
    def race(fd, src, dst, flag):
        if src == "current" and dst.startswith(".retired-") and not injected:
            lab.current.unlink()
            lab.current.write_bytes(b"FOREIGN_DEACTIVATION")
            injected.append(True)
        return rename(fd, src, dst, flag)
    monkeypatch.setattr(tx, "_rename", race)
    with pytest.raises(RuntimeError, match="Foreign"):
        lab.switch(None)
    assert injected
    assert lab.current.read_bytes() == b"FOREIGN_DEACTIVATION"
    assert lab.pending.exists()


def test_rollback_selection_and_commit_are_same_lock(lab, monkeypatch):
    lab.stage_fixture("third", b"third")
    _prepare(lab)
    lab.switch("new")
    def forbidden_switch(*args, **kwargs):
        pytest.fail("Rollback MUST NOT call unlocked public switch")
    monkeypatch.setattr(lab, "switch", forbidden_switch)
    lab.rollback()
    assert lab.status()["active"] == "old"
    assert lab.status()["previous"] == "new"


def test_world_writable_root_refused(lab):
    lab.stage_fixture("one", b"one")
    lab.root.chmod(0o777)
    with pytest.raises(RuntimeError, match="unsafe writable mode"):
        lab.status()


def test_symlinked_runner_ancestor_refused(tmp_path, monkeypatch):
    out = tmp_path / "outside"
    (out / "runner").mkdir(parents=True)
    alias = tmp_path / "alias"
    alias.symlink_to(out, target_is_directory=True)
    base = alias / "runner"
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("RUNNER_TEMP", str(base))
    with pytest.raises(RuntimeError, match="Symlink"):
        tx.TransactionLab(base / "flight-transaction-lab" / "case")


def test_directories_fsynced_during_transaction(lab, monkeypatch):
    lab.stage_fixture("one", b"one")
    fsync = tx.os.fsync
    types = []
    def track(fd):
        types.append(stat.S_ISDIR(os.fstat(fd).st_mode))
        return fsync(fd)
    monkeypatch.setattr(tx.os, "fsync", track)
    lab.switch("one")
    assert True in types
    assert False in types


def test_orphan_stage_is_preserved_and_new_stage_refused(lab):
    lab.stage_fixture("one", b"one")
    orphan = lab.releases / ".stage-abandoned"
    orphan.mkdir()
    (orphan / "image.bin").write_bytes(b"abandoned")
    with pytest.raises(RuntimeError, match="interrupted staging"):
        lab.stage_fixture("two", b"two")
    assert (orphan / "image.bin").read_bytes() == b"abandoned"


def test_manifest_forgery_is_not_claimed_as_authentication(lab):
    lab.stage_fixture("v1", b"original")
    payload = lab.releases / "v1" / "image.bin"
    meta = lab.releases / "v1" / "manifest.json"
    payload.write_bytes(b"forged")
    record = {"owner": tx.OWNER, "name": "v1",
              "sha256": hashlib.sha256(b"forged").hexdigest(),
              "size": len(b"forged")}
    meta.write_text(json.dumps(record))
    # Deliberate HOLD: hash in mutable manifest is not trusted provenance.
    lab.switch("v1")
    assert lab.status()["active"] == "v1"


def test_fake_user_pipx_archive_qsettings_data_untouched(lab, tmp_path):
    fake = tmp_path / "protected-user-home"
    sentinels = {
        fake / ".local/pipx/venvs/tihulu-flight-radar/installed.marker": b"pipx intact",
        fake / ".config/Tihulu/Flight Radar.conf": b"QSettings intact",
        fake / "Archives/flight-0.3.1.tar": b"0.3.1 preserved",
        fake / ".local/share/tihulu-flight-radar/recordings/index": b"data preserved",
    }
    for path, payload in sentinels.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    baseline = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in sentinels}
    _prepare(lab)
    lab.switch("new")
    lab.rollback()
    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in sentinels} == baseline


def test_environment_flags_not_production_authentication(lab):
    # Same-account process can set flags; production release remains HOLD.
    assert os.environ["GITHUB_ACTIONS"] == "true"
    assert os.environ["CI"] == "true"
    assert lab.status()["active"] is None


def test_recovery_after_interrupted_switch_and_after_state(lab):
    _prepare(lab)
    with pytest.raises(RuntimeError, match="Injected fault"):
        lab.switch("new", fault="after_state")
    lab.recover()
    assert lab.status()["active"] == "old"
    assert not lab.pending.exists()

def test_parallel_processes_serialize_switches(lab):
    _prepare(lab)
    lab.stage_fixture("third", b"third")
    ctx = multiprocessing.get_context("fork")
    start = ctx.Event()
    results = ctx.Queue()
    root = lab.root
    def worker(name):
        try:
            start.wait(timeout=4)
            tx.TransactionLab(root).switch(name)
            results.put("PASS")
        except BaseException as exc:
            results.put(repr(exc))
    workers = [ctx.Process(target=worker, args=(name,)) for name in ("new", "third")]
    for process in workers:
        process.start()
    start.set()
    for process in workers:
        process.join(timeout=8)
        if process.is_alive():
            process.terminate()
            process.join()
            pytest.fail("Parallel worker blocked after lock acquisition")
        assert process.exitcode == 0
    assert [results.get(timeout=2) for _ in workers] == ["PASS", "PASS"]
    assert lab.status()["active"] in ("new", "third")


def test_sigkill_after_pointer_recovery(lab):
    _prepare(lab)
    ctx = multiprocessing.get_context("fork")
    root = lab.root
    def crash_after_pointer():
        original = tx._rename
        def terminate_after_swap(fd, src, dst, flag):
            original(fd, src, dst, flag)
            if dst == "current" and flag == tx._EXCHANGE:
                os._exit(66)  # Killed disposable child after durable pointer.
        tx._rename = terminate_after_swap
        tx.TransactionLab(root).switch("new")
    process = ctx.Process(target=crash_after_pointer)
    process.start()
    process.join(timeout=8)
    if process.is_alive():
        process.terminate()
        process.join()
        pytest.fail("Crash-injection child deadlocked")
    assert process.exitcode == 66
    assert lab.pending.exists()
    lab.recover()
    assert lab.status()["active"] == "old"
    assert not lab.pending.exists()
