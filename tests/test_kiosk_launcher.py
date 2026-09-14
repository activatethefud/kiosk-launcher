"""Tests for kiosk_launcher. Run with:

    python3 -m unittest discover -s tests -v
    # or: pytest tests/
"""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import kiosk_launcher as k  # noqa: E402


# ---------------------------------------------------------------------------
# Password
# ---------------------------------------------------------------------------
class TestPassword(unittest.TestCase):
    def test_roundtrip(self):
        salt, digest, it = k.hash_password("hunter2")
        pw_cfg = {"salt": salt, "hash": digest, "iterations": it}
        self.assertTrue(k.verify_password("hunter2", pw_cfg))

    def test_wrong_password_rejected(self):
        salt, digest, it = k.hash_password("hunter2")
        pw_cfg = {"salt": salt, "hash": digest, "iterations": it}
        self.assertFalse(k.verify_password("hunter3", pw_cfg))

    def test_salt_is_unique(self):
        s1, _, _ = k.hash_password("pw")
        s2, _, _ = k.hash_password("pw")
        self.assertNotEqual(s1, s2)

    def test_iterations_defaults_to_200k_when_missing(self):
        salt, digest, _ = k.hash_password("pw")  # uses default 200_000
        self.assertTrue(k.verify_password("pw", {"salt": salt, "hash": digest}))

    def test_salt_is_hex(self):
        salt, _, _ = k.hash_password("pw")
        int(salt, 16)  # raises if not hex


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
class TestConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "config.json")
        self.addCleanup(self.tmp.cleanup)

    def test_seed_structure(self):
        cfg = k.seed_config()
        self.assertIn("salt", cfg["password"])
        self.assertIn("hash", cfg["password"])
        self.assertIn("iterations", cfg["password"])
        self.assertIn("fullscreen", cfg)
        self.assertIn("columns", cfg)
        self.assertGreater(len(cfg["apps"]), 0)
        for app in cfg["apps"]:
            self.assertIn("name", app)
            self.assertIn("patterns", app)
            self.assertIn("args", app)

    def test_load_creates_file(self):
        self.assertFalse(os.path.exists(self.path))
        cfg, path = k.load_config(self.path)
        self.assertTrue(os.path.exists(self.path))
        self.assertEqual(path, self.path)
        self.assertGreater(len(cfg["apps"]), 0)

    def test_load_repairs_missing_password(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"fullscreen": True, "columns": 2, "apps": []}, f)
        cfg, _ = k.load_config(self.path)
        self.assertIn("salt", cfg["password"])
        self.assertIn("hash", cfg["password"])

    def test_load_repairs_missing_apps(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"fullscreen": False, "columns": 4}, f)
        cfg, _ = k.load_config(self.path)
        self.assertEqual(cfg["apps"], k.BUILTIN_APPS)

    def test_save_load_roundtrip(self):
        cfg, _ = k.load_config(self.path)
        cfg["apps"].append({"name": "X", "patterns": ["x$"], "args": [], "custom": True})
        cfg["columns"] = 3
        k.save_config(cfg, self.path)
        cfg2, _ = k.load_config(self.path)
        self.assertEqual(cfg, cfg2)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------
class TestDiscovery(unittest.TestCase):
    def test_discover_finds_and_reports_missing(self):
        candidates = {
            "/usr/bin/gimp",
            r"C:\Program Files\Scratch 3\Scratch 3.exe",
            "/opt/games/MyCoolGame",
        }
        cfg = {
            "apps": [
                {"name": "GIMP", "patterns": [r"gimp(?:\.exe)?$"], "args": []},
                {"name": "Scratch", "patterns": [r"scratch(?: ?3)?(?:\.exe)?$"], "args": []},
                {"name": "Game", "patterns": [r"coolgame(?:\.exe)?$"], "args": []},
                {"name": "Nope", "patterns": [r"nope(?:\.exe)?$"], "args": []},
            ]
        }
        with mock.patch.object(k, "gather_candidates", return_value=candidates):
            found, missing = k.discover_apps(cfg)
        names = {a["name"] for a in found}
        self.assertEqual(names, {"GIMP", "Scratch", "Game"})
        self.assertEqual(missing, ["Nope"])

    def test_matching_is_case_insensitive(self):
        candidates = {"/usr/bin/GIMP"}
        cfg = {"apps": [{"name": "G", "patterns": [r"gimp$"], "args": []}]}
        with mock.patch.object(k, "gather_candidates", return_value=candidates):
            found, missing = k.discover_apps(cfg)
        self.assertEqual(len(found), 1)
        self.assertEqual(missing, [])

    def test_args_are_passed_through(self):
        candidates = {"/usr/bin/app"}
        cfg = {"apps": [{"name": "A", "patterns": ["app$"], "args": ["--flag"]}]}
        with mock.patch.object(k, "gather_candidates", return_value=candidates):
            found, _ = k.discover_apps(cfg)
        self.assertEqual(found[0]["args"], ["--flag"])

    def test_bad_regex_is_reported_missing_not_fatal(self):
        candidates = {"/usr/bin/app"}
        cfg = {"apps": [{"name": "Bad", "patterns": ["(unclosed"], "args": []}]}
        with mock.patch.object(k, "gather_candidates", return_value=candidates):
            with mock.patch("sys.stderr"):
                found, missing = k.discover_apps(cfg)
        self.assertEqual(found, [])
        self.assertEqual(missing, ["Bad"])

    def test_gather_candidates_includes_path_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = os.path.join(tmp, "someapp")
            with open(exe, "w", encoding="utf-8"):
                pass
            with mock.patch.dict(os.environ, {"PATH": tmp}):
                candidates = k.gather_candidates()
        self.assertIn(exe, candidates)


class TestWalkDepth(unittest.TestCase):
    def test_respects_max_depth(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "a", "b", "c"))
            l0 = os.path.join(tmp, "l0")
            l1 = os.path.join(tmp, "a", "l1")
            l3 = os.path.join(tmp, "a", "b", "c", "l3")
            for p in (l0, l1, l3):
                with open(p, "w", encoding="utf-8"):
                    pass
            got = set(k._walk_depth(tmp, max_depth=2))
            self.assertIn(l0, got)
            self.assertIn(l1, got)
            self.assertNotIn(l3, got)


# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------
class TestLaunch(unittest.TestCase):
    def test_launch_missing_path_returns_error(self):
        err = k.launch({"path": os.path.join("no", "such", "app"), "args": []})
        self.assertIsNotNone(err)

    @unittest.skipIf(os.name == "nt", "POSIX-only smoke test")
    def test_launch_ok_returns_none(self):
        err = k.launch({"path": "/bin/true", "args": []})
        self.assertIsNone(err)


if __name__ == "__main__":
    unittest.main()
