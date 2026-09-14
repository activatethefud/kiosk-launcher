"""Tests for kiosk_launcher. Run with:

    python3 -m unittest discover -s tests -v
    # or: pytest tests/
"""

import json
import os
import re
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
# Config (settings + password only; apps now live in apps.json)
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
        self.assertNotIn("apps", cfg)  # apps are no longer in the config

    def test_load_creates_file(self):
        self.assertFalse(os.path.exists(self.path))
        cfg, path = k.load_config(self.path)
        self.assertTrue(os.path.exists(self.path))
        self.assertEqual(path, self.path)
        self.assertIn("password", cfg)
        self.assertIn("columns", cfg)

    def test_load_repairs_missing_password(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"fullscreen": True, "columns": 2}, f)
        cfg, _ = k.load_config(self.path)
        self.assertIn("salt", cfg["password"])
        self.assertIn("hash", cfg["password"])

    def test_load_preserves_settings(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"fullscreen": True, "columns": 3}, f)
        cfg, _ = k.load_config(self.path)
        self.assertTrue(cfg["fullscreen"])
        self.assertEqual(cfg["columns"], 3)

    def test_save_load_roundtrip(self):
        cfg, _ = k.load_config(self.path)
        cfg["columns"] = 3
        k.save_config(cfg, self.path)
        cfg2, _ = k.load_config(self.path)
        self.assertEqual(cfg, cfg2)


# ---------------------------------------------------------------------------
# App templates (apps.json)
# ---------------------------------------------------------------------------
class TestAppTemplates(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "apps.json")
        self.addCleanup(self.tmp.cleanup)

    def test_load_seeds_file_from_presets_when_missing(self):
        self.assertFalse(os.path.exists(self.path))
        apps, path = k.load_apps(self.path)
        self.assertEqual(path, self.path)
        self.assertTrue(os.path.exists(self.path))
        self.assertEqual(apps, k.BUILTIN_APPS)

    def test_load_reads_list(self):
        data = [{"name": "GIMP", "patterns": [r"gimp(?:\.exe)?$"], "args": []}]
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        apps, _ = k.load_apps(self.path)
        self.assertEqual(apps, data)

    def test_load_accepts_wrapped_dict(self):
        data = {"apps": [{"name": "X", "patterns": ["x$"], "args": []}]}
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        apps, _ = k.load_apps(self.path)
        self.assertEqual(len(apps), 1)
        self.assertEqual(apps[0]["name"], "X")

    def test_normalize_coerces_string_patterns_and_args(self):
        data = [{"name": "X", "patterns": "x$", "args": "--flag --two"}]
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        apps, _ = k.load_apps(self.path)
        self.assertEqual(apps[0]["patterns"], ["x$"])
        self.assertEqual(apps[0]["args"], ["--flag", "--two"])

    def test_invalid_entries_are_skipped(self):
        data = [
            {"name": "Good", "patterns": ["good$"], "args": []},
            {"name": "", "patterns": ["x$"], "args": []},          # no name
            {"name": "NoPatterns", "patterns": [], "args": []},    # no patterns
            "not-a-dict",
        ]
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        apps, _ = k.load_apps(self.path)
        self.assertEqual([a["name"] for a in apps], ["Good"])

    def test_invalid_json_falls_back_without_overwriting(self):
        original = "{ this is not valid json"
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(original)
        with mock.patch("sys.stderr"):
            apps, _ = k.load_apps(self.path)
        self.assertEqual(apps, k.BUILTIN_APPS)
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(f.read(), original)  # not clobbered

    def test_explicitly_empty_file_is_respected(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump([], f)
        apps, _ = k.load_apps(self.path)
        self.assertEqual(apps, [])

    def test_save_load_roundtrip(self):
        apps, _ = k.load_apps(self.path)
        apps.append({"name": "GIMP", "patterns": [r"gimp(?:\.exe)?$"], "args": []})
        k.save_apps(apps, self.path)
        apps2, _ = k.load_apps(self.path)
        self.assertEqual(apps, apps2)

    def test_normalize_app_rejects_missing_name(self):
        self.assertIsNone(k.normalize_app({"patterns": ["x$"], "args": []}))

    def test_normalize_app_rejects_missing_patterns(self):
        self.assertIsNone(k.normalize_app({"name": "X", "args": []}))


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
        apps = [
            {"name": "GIMP", "patterns": [r"gimp(?:\.exe)?$"], "args": []},
            {"name": "Scratch", "patterns": [r"scratch(?: ?3)?(?:\.exe)?$"], "args": []},
            {"name": "Game", "patterns": [r"coolgame(?:\.exe)?$"], "args": []},
            {"name": "Nope", "patterns": [r"nope(?:\.exe)?$"], "args": []},
        ]
        with mock.patch.object(k, "gather_candidates", return_value=candidates):
            found, missing = k.discover_apps(apps)
        names = {a["name"] for a in found}
        self.assertEqual(names, {"GIMP", "Scratch", "Game"})
        self.assertEqual(missing, ["Nope"])

    def test_matching_is_case_insensitive(self):
        candidates = {"/usr/bin/GIMP"}
        apps = [{"name": "G", "patterns": [r"gimp$"], "args": []}]
        with mock.patch.object(k, "gather_candidates", return_value=candidates):
            found, missing = k.discover_apps(apps)
        self.assertEqual(len(found), 1)
        self.assertEqual(missing, [])

    def test_args_are_passed_through(self):
        candidates = {"/usr/bin/app"}
        apps = [{"name": "A", "patterns": ["app$"], "args": ["--flag"]}]
        with mock.patch.object(k, "gather_candidates", return_value=candidates):
            found, _ = k.discover_apps(apps)
        self.assertEqual(found[0]["args"], ["--flag"])

    def test_bad_regex_is_reported_missing_not_fatal(self):
        candidates = {"/usr/bin/app"}
        apps = [{"name": "Bad", "patterns": ["(unclosed"], "args": []}]
        with mock.patch.object(k, "gather_candidates", return_value=candidates):
            with mock.patch("sys.stderr"):
                found, missing = k.discover_apps(apps)
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


class TestBuiltinPresets(unittest.TestCase):
    def test_all_builtin_patterns_compile(self):
        for app in k.BUILTIN_APPS:
            for p in app["patterns"]:
                re.compile(p)  # raises if invalid

    def test_vscodium_matches_windows_exe(self):
        apps = [a for a in k.BUILTIN_APPS if a["name"] == "VSCodium"]
        candidates = {
            r"C:\Users\kid\AppData\Local\Programs\VSCodium\VSCodium.exe"
        }
        with mock.patch.object(k, "gather_candidates", return_value=candidates):
            found, missing = k.discover_apps(apps)
        self.assertEqual(len(found), 1)
        self.assertEqual(missing, [])

    def test_gimp_matches_versioned_windows_exe(self):
        apps = [a for a in k.BUILTIN_APPS if a["name"] == "GIMP"]
        candidates = {r"C:\Program Files\GIMP 2\bin\gimp-2.10.exe"}
        with mock.patch.object(k, "gather_candidates", return_value=candidates):
            found, missing = k.discover_apps(apps)
        self.assertEqual(len(found), 1)
        self.assertEqual(missing, [])

    def test_gimp_ignores_console_variant(self):
        apps = [a for a in k.BUILTIN_APPS if a["name"] == "GIMP"]
        candidates = {r"C:\Program Files\GIMP 2\bin\gimp-console-2.10.exe"}
        with mock.patch.object(k, "gather_candidates", return_value=candidates):
            found, missing = k.discover_apps(apps)
        self.assertEqual(found, [])
        self.assertEqual(missing, ["GIMP"])

    def test_mupdf_matches_viewer_not_pymupdf(self):
        apps = [a for a in k.BUILTIN_APPS if a["name"] == "MuPDF"]
        candidates = {
            r"C:\Program Files\MuPDF\mupdf-gl.exe",
            "/usr/bin/mupdf",
        }
        with mock.patch.object(k, "gather_candidates", return_value=candidates):
            found, missing = k.discover_apps(apps)
        self.assertEqual(len(found), 1)
        self.assertEqual(missing, [])

    def test_mupdf_ignores_pymupdf_cli(self):
        apps = [a for a in k.BUILTIN_APPS if a["name"] == "MuPDF"]
        candidates = {"/home/user/.local/bin/pymupdf"}
        with mock.patch.object(k, "gather_candidates", return_value=candidates):
            found, missing = k.discover_apps(apps)
        self.assertEqual(found, [])
        self.assertEqual(missing, ["MuPDF"])


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
