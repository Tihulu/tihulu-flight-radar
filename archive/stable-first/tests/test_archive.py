"""Source and fail-closed synthetic safety tests. NO receiver or installer launch."""
import hashlib
import importlib.util
import json
import os
import runpy
import stat
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ARCHIVE = Path(__file__).resolve().parents[1]
INSTALLER = ARCHIVE / "installer" / "stable_first.py"
SPEC = importlib.util.spec_from_file_location("stable_first_safety", INSTALLER)
sf = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sf)


class ArchiveTests(unittest.TestCase):
    def test_source_64_sha256_and_executable_modes(self):
        data = sf.verify_source()
        self.assertEqual(data["source_commit"], sf.SOURCE_SHA)
        self.assertEqual(data["source_tree_sha"], "a916732793c405e73f5de996b528ac96437222cd")
        self.assertEqual(len(data["files"]), 64)
        self.assertEqual(len(set(item["path"] for item in data["files"])), 64)
        for entry in data["files"]:
            source = ARCHIVE / "source" / entry["path"]
            content = source.read_bytes()
            self.assertEqual(len(content), entry["size"], source)
            self.assertEqual(hashlib.sha256(content).hexdigest(), entry["sha256"])
            git_object = b"blob " + str(len(content)).encode() + b"\0" + content
            self.assertEqual(hashlib.sha1(git_object).hexdigest(), entry["git_blob_sha1"])
            self.assertEqual(stat.S_IMODE(source.stat().st_mode), int(entry["mode"], 8) & 0o777)

    def test_expected_features_exist_in_original_copy(self):
        files = {e["path"] for e in sf.verify_source()["files"]}
        for required in (
            "pyproject.toml", "tihulu_flight_radar/native.py",
            "tihulu_flight_radar/app.py", "tihulu_flight_radar/control.py",
            "tihulu_flight_radar/bridge.py", "tihulu_flight_radar/core.py",
            "tihulu_flight_radar/map.html", "tihulu_flight_radar/tar_overlay.py",
            "tihulu_flight_radar/web/index.html", "tihulu_flight_radar/web/app.js",
            "tests/test_control.py", "scripts/qt_smoke.py",
        ):
            self.assertIn(required, files)

    def test_symlink_in_source_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            temp = Path(root)
            (temp / "pyproject.toml").symlink_to(ARCHIVE / "source" / "pyproject.toml")
            with mock.patch.object(sf, "SOURCE", temp):
                with self.assertRaises(RuntimeError):
                    sf.verify_source()

    def test_corrupted_source_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            temp = Path(root)
            target = temp / "pyproject.toml"
            target.write_bytes((ARCHIVE / "source" / "pyproject.toml").read_bytes() + b"\n# tampered\n")
            with mock.patch.object(sf, "SOURCE", temp):
                with self.assertRaises(RuntimeError):
                    sf.verify_source()


class OwnershipTests(unittest.TestCase):
    def test_foreign_launcher_refused_without_state(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            launcher = base / "foreign"
            launcher.write_text("existing pipx launcher")
            with mock.patch.object(sf, "CURRENT", base / "current"), \
                 mock.patch.object(sf, "LAUNCHER", launcher), \
                 mock.patch.object(sf, "DESKTOP", base / "desktop"):
                with self.assertRaises(RuntimeError):
                    sf.check_state(None)
            self.assertEqual(launcher.read_text(), "existing pipx launcher")

    def test_foreign_symlink_refused(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / "link"
            p.symlink_to("/tmp")
            with self.assertRaises(RuntimeError):
                sf.owner_file(p)
            self.assertTrue(p.is_symlink())

    def test_release_inventory_rejects_untracked_file(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            (folder / "owned.txt").write_text("owned")
            data = sf.inventory(folder)
            (folder / "inventory.json").write_text(json.dumps(data))
            known_hash = sf.digest(folder / "inventory.json")
            sf.verify_inventory(folder, known_hash)
            (folder / "foreign-model.gguf").write_text("private file")
            with self.assertRaises(RuntimeError):
                sf.verify_inventory(folder, known_hash)
            self.assertTrue((folder / "foreign-model.gguf").exists())

    def test_interrupted_install_preserves_foreign_files_and_leaves_no_stage(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            foreign = folder / "old-pipx-script"
            foreign.write_text("NEVER_CHANGE")
            def local_dir(path):
                Path(path).mkdir(parents=True, exist_ok=True)
            with mock.patch.object(sf, "BASE", folder), \
                 mock.patch.object(sf, "RELEASES", folder / "releases"), \
                 mock.patch.object(sf, "CURRENT", folder / "current"), \
                 mock.patch.object(sf, "STATE", folder / "state.json"), \
                 mock.patch.object(sf, "LAUNCHER", folder / "launcher"), \
                 mock.patch.object(sf, "DESKTOP", folder / "desktop"), \
                 mock.patch.object(sf, "secure_dir", side_effect=local_dir), \
                 mock.patch.object(sf.subprocess, "run", side_effect=RuntimeError("interrupted venv creation")):
                with self.assertRaisesRegex(RuntimeError, "interrupted"):
                    sf.install()
            self.assertEqual(foreign.read_text(), "NEVER_CHANGE")
            self.assertFalse((folder / "launcher").exists())
            self.assertFalse((folder / "desktop").exists())
            self.assertFalse((folder / "current").exists())
            self.assertEqual(list((folder / "releases").iterdir()), [])

    def test_rollback_never_calls_receiver_commands(self):
        state = {"owner": sf.OWNER, "source_sha": sf.SOURCE_SHA,
                 "active": "new", "previous": "old", "releases": {"new": {}, "old": {}}}
        with mock.patch.object(sf, "read_state", return_value=state), \
             mock.patch.object(sf, "check_state"), \
             mock.patch.object(sf, "replace_active") as replace, \
             mock.patch.object(sf, "atomic_write") as write, \
             mock.patch.object(sf.subprocess, "run", side_effect=AssertionError("subprocess forbidden")):
            sf.rollback()
        replace.assert_called_once_with("old")
        write.assert_called_once()
        self.assertEqual(state["active"], "old")

    def test_check_and_dry_run_do_not_spawn_processes(self):
        with mock.patch.object(sf.subprocess, "run", side_effect=AssertionError("spawn forbidden")):
            sf.verify_source()
            sf.expected_shortcuts()


class PassiveRuntimeTests(unittest.TestCase):
    def test_block_mutating_receiver_actions_even_when_gui_requests_them(self):
        pkg = types.ModuleType("tihulu_flight_radar")
        pkg.__path__ = []
        control = types.ModuleType("tihulu_flight_radar.control")
        native = types.ModuleType("tihulu_flight_radar.native")

        class DataError(Exception):
            pass

        class Receiver:
            def __init__(self):
                self.process = None
            def start(self):
                return "UNSAFE"
            def stop(self):
                return "UNSAFE"
            def restart(self):
                return "UNSAFE"
            def close(self, **kwargs):
                return "UNSAFE"

        control.DataError = DataError
        control.ReceiverController = Receiver
        control.service_action = lambda action: "UNSAFE " + action
        native.main = lambda: 0
        pkg.control = control
        with mock.patch.dict(sys.modules, {
            "tihulu_flight_radar": pkg,
            "tihulu_flight_radar.control": control,
            "tihulu_flight_radar.native": native,
        }), mock.patch.dict(os.environ, {"TIHULU_STABLE_FIRST_PASSIVE": "1"}):
            runpy.run_path(str(ARCHIVE / "installer" / "safe_entry.py"),
                           run_name="stable_first_mock_test")
            controller = Receiver()
            for method in ("start", "stop", "restart"):
                with self.assertRaises(DataError, msg=method):
                    getattr(controller, method)()
            for action in ("start", "stop", "restart", "enable", "disable"):
                with self.assertRaises(DataError):
                    control.service_action(action)
            self.assertIsNone(controller.close(release_local_service=True))


if __name__ == "__main__":
    unittest.main()
