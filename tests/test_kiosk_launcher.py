"""Tests for kiosk_launcher. Run with:

    python3 -m unittest discover -s tests -v
    # or: pytest tests/
"""

import io
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

    def test_verify_password_handles_corrupt_config(self):
        self.assertFalse(k.verify_password("x", {}))
        self.assertFalse(k.verify_password("x", {"salt": "nothex", "hash": "h"}))
        self.assertFalse(k.verify_password(None, {"salt": "00", "hash": "00"}))

    def test_custom_iterations_roundtrip(self):
        salt, digest, it = k.hash_password("pw", iterations=1000)
        self.assertEqual(it, 1000)
        self.assertTrue(
            k.verify_password("pw", {"salt": salt, "hash": digest, "iterations": 1000})
        )


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
        self.assertTrue(cfg["fullscreen"])
        self.assertIn("columns", cfg)
        self.assertEqual(cfg["columns"], 0)
        self.assertEqual(cfg["card_size"], "auto")
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

    def test_load_config_repairs_non_dict_json(self):
        for bad in ("[]", '"hello"', "123"):
            with open(self.path, "w", encoding="utf-8") as f:
                f.write(bad)
            cfg, _ = k.load_config(self.path)
            self.assertIsInstance(cfg, dict)
            self.assertIn("salt", cfg["password"])

    def test_load_config_repairs_broken_password(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"password": "not-a-dict", "columns": 3}, f)
        cfg, _ = k.load_config(self.path)
        self.assertIsInstance(cfg["password"], dict)
        self.assertIn("salt", cfg["password"])
        self.assertIn("hash", cfg["password"])

    def test_load_config_repairs_password_missing_hash(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"password": {"salt": "abcdef0123456789"}}, f)
        cfg, _ = k.load_config(self.path)
        self.assertIn("hash", cfg["password"])

    def test_save_config_creates_parent_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "a", "b", "config.json")
            k.save_config(k.seed_config(), p)
            self.assertTrue(os.path.exists(p))

    def test_load_defaults_fullscreen_true(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"columns": 3}, f)
        cfg, _ = k.load_config(self.path)
        self.assertTrue(cfg["fullscreen"])

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

    def test_load_apps_dict_with_nonlist_apps_seeds(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"apps": "notalist"}, f)
        apps, _ = k.load_apps(self.path)
        self.assertEqual(apps, k.BUILTIN_APPS)

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

    def test_save_apps_creates_parent_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = os.path.join(tmp, "a", "b", "apps.json")
            k.save_apps([{"name": "A", "patterns": ["a$"], "args": []}], p)
            self.assertTrue(os.path.exists(p))

    def test_normalize_app_rejects_missing_name(self):
        self.assertIsNone(k.normalize_app({"patterns": ["x$"], "args": []}))

    def test_normalize_app_rejects_missing_patterns(self):
        self.assertIsNone(k.normalize_app({"name": "X", "args": []}))

    def test_normalize_app_coerces_nonlist_args(self):
        app = k.normalize_app({"name": "X", "patterns": ["x$"], "args": 123})
        self.assertEqual(app["args"], [])

    def test_normalize_app_filters_nonstring_patterns(self):
        app = k.normalize_app({"name": "X", "patterns": [123, "x$", None], "args": []})
        self.assertEqual(app["patterns"], ["x$"])

    def test_normalize_app_rejects_nonstring_name(self):
        self.assertIsNone(k.normalize_app({"name": 123, "patterns": ["x$"], "args": []}))

    def test_normalize_app_rejects_whitespace_name(self):
        self.assertIsNone(k.normalize_app({"name": "   ", "patterns": ["x$"], "args": []}))


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

    def test_uppercase_pattern_matches_lowercase_candidate(self):
        candidates = {"/usr/bin/gimp"}
        apps = [{"name": "G", "patterns": [r"GIMP$"], "args": []}]
        with mock.patch.object(k, "gather_candidates", return_value=candidates):
            found, _ = k.discover_apps(apps)
        self.assertEqual(len(found), 1)

    def test_mixed_case_windows_path_matches(self):
        candidates = {r"C:\Program Files\GIMP 2\bin\GIMP-2.10.EXE"}
        apps = [
            {"name": "G", "patterns": [r"gimp(?:[._-]?[\d.]+)?(?:\.exe)?$"], "args": []}
        ]
        with mock.patch.object(k, "gather_candidates", return_value=candidates):
            found, _ = k.discover_apps(apps)
        self.assertEqual(len(found), 1)

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

    def test_discover_apps_skips_malformed_entries(self):
        apps = [
            {"name": "Good", "patterns": ["good$"], "args": []},
            "not-a-dict",
            {"name": "NoPatterns", "args": []},
            {"name": "BadRegex", "patterns": ["(unclosed"], "args": []},
        ]
        with mock.patch.object(k, "gather_candidates", return_value={"/x/good"}):
            with mock.patch("sys.stderr"):
                found, missing = k.discover_apps(apps)
        self.assertEqual([a["name"] for a in found], ["Good"])
        self.assertEqual(sorted(missing), ["?", "BadRegex", "NoPatterns"])

    def test_discover_apps_coerces_string_args(self):
        apps = [{"name": "A", "patterns": ["a$"], "args": "--flag --two"}]
        with mock.patch.object(k, "gather_candidates", return_value={"/x/a"}):
            found, missing = k.discover_apps(apps)
        self.assertEqual(found[0]["args"], ["--flag", "--two"])
        self.assertEqual(missing, [])

    def test_discover_apps_coerces_string_patterns(self):
        apps = [{"name": "A", "patterns": "a$", "args": []}]
        with mock.patch.object(k, "gather_candidates", return_value={"/x/a"}):
            found, missing = k.discover_apps(apps)
        self.assertEqual(len(found), 1)
        self.assertEqual(missing, [])

    def test_discover_apps_filters_nonstring_patterns(self):
        apps = [{"name": "A", "patterns": [123, "a$", None], "args": []}]
        with mock.patch.object(k, "gather_candidates", return_value={"/x/a"}):
            found, missing = k.discover_apps(apps)
        self.assertEqual(len(found), 1)
        self.assertEqual(missing, [])

    def test_gather_candidates_includes_path_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = os.path.join(tmp, "someapp")
            with open(exe, "w", encoding="utf-8"):
                pass
            with mock.patch.dict(os.environ, {"PATH": tmp}):
                candidates = k.gather_candidates()
        self.assertIn(exe, candidates)

    def test_gather_candidates_survives_bad_path_dir(self):
        with tempfile.TemporaryDirectory() as good, \
             tempfile.TemporaryDirectory() as bad:
            app = os.path.join(good, "app1")
            with open(app, "w", encoding="utf-8"):
                pass
            real_listdir = os.listdir

            def listdir(p):
                if os.path.normpath(p) == os.path.normpath(bad):
                    raise OSError("boom")
                return real_listdir(p)

            with mock.patch.dict(os.environ, {"PATH": good + os.pathsep + bad}):
                with mock.patch.object(k.os, "listdir", side_effect=listdir):
                    candidates = k.gather_candidates()
            self.assertIn(app, candidates)

    def test_gather_candidates_survives_windows_walk_errors(self):
        with mock.patch.object(k, "_walk_depth", side_effect=OSError("boom")):
            with mock.patch.object(k.os, "name", "nt"):
                with mock.patch.object(k, "_registry_app_paths", return_value=set()):
                    candidates = k.gather_candidates()
        self.assertEqual(candidates, set())

    def test_gather_candidates_windows_branch_collects_exe(self):
        with tempfile.TemporaryDirectory() as pf:
            exe = os.path.join(pf, "app.exe")
            txt = os.path.join(pf, "note.txt")
            for p in (exe, txt):
                with open(p, "w"):
                    pass
            env = {"ProgramFiles": pf, "ProgramFiles(x86)": pf,
                   "ProgramData": pf, "LOCALAPPDATA": pf, "PATH": pf}
            with mock.patch.dict(os.environ, env):
                with mock.patch.object(k.os, "name", "nt"):
                    with mock.patch.object(k, "_registry_app_paths", return_value=set()):
                        cands = k.gather_candidates()
            self.assertIn(exe, cands)
            self.assertNotIn(txt, cands)

    def test_registry_app_paths_handles_missing_winreg(self):
        real_import = __import__

        def fake_import(name, *a, **kw):
            if name == "winreg":
                raise ImportError("no winreg")
            return real_import(name, *a, **kw)

        with mock.patch.object(k.os, "name", "nt"):
            with mock.patch("builtins.__import__", side_effect=fake_import):
                self.assertEqual(k._registry_app_paths(), set())


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

    def test_virtualbox_matches_gui_not_cli(self):
        apps = [a for a in k.BUILTIN_APPS if a["name"] == "VirtualBox"]
        candidates = {
            r"C:\Program Files\Oracle\VirtualBox\VirtualBox.exe",
            "/usr/bin/virtualbox",
        }
        with mock.patch.object(k, "gather_candidates", return_value=candidates):
            found, missing = k.discover_apps(apps)
        self.assertEqual(len(found), 1)
        self.assertEqual(missing, [])

    def test_virtualbox_ignores_vboxmanage(self):
        apps = [a for a in k.BUILTIN_APPS if a["name"] == "VirtualBox"]
        candidates = {r"C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"}
        with mock.patch.object(k, "gather_candidates", return_value=candidates):
            found, missing = k.discover_apps(apps)
        self.assertEqual(found, [])
        self.assertEqual(missing, ["VirtualBox"])

    def test_arduino_matches_ide_and_ignores_cli(self):
        apps = [a for a in k.BUILTIN_APPS if a["name"] == "Arduino IDE"]
        candidates = {
            r"C:\Program Files\Arduino IDE\Arduino IDE.exe",
            "/usr/bin/arduino",
        }
        with mock.patch.object(k, "gather_candidates", return_value=candidates):
            found, missing = k.discover_apps(apps)
        self.assertEqual(len(found), 1)
        self.assertEqual(missing, [])
        # the CLI tool must not match
        candidates = {r"C:\arduino-cli.exe"}
        with mock.patch.object(k, "gather_candidates", return_value=candidates):
            found, missing = k.discover_apps(apps)
        self.assertEqual(found, [])
        self.assertEqual(missing, ["Arduino IDE"])

    def test_musescore_matches_versioned_exe(self):
        apps = [a for a in k.BUILTIN_APPS if a["name"] == "MuseScore"]
        candidates = {
            r"C:\Program Files\MuseScore 4\bin\MuseScore4.exe",
            "/usr/bin/mscore",
        }
        with mock.patch.object(k, "gather_candidates", return_value=candidates):
            found, missing = k.discover_apps(apps)
        self.assertEqual(len(found), 1)
        self.assertEqual(missing, [])

    def test_mu_editor_matches_and_ignores_emu(self):
        apps = [a for a in k.BUILTIN_APPS if a["name"] == "Mu Editor"]
        candidates = {r"C:\Users\kid\AppData\Local\Programs\Mu Editor\Mu.exe"}
        with mock.patch.object(k, "gather_candidates", return_value=candidates):
            found, missing = k.discover_apps(apps)
        self.assertEqual(len(found), 1)
        self.assertEqual(missing, [])
        # "emu.exe" must not match the anchored "mu" pattern
        candidates = {r"C:\tools\emu.exe"}
        with mock.patch.object(k, "gather_candidates", return_value=candidates):
            found, missing = k.discover_apps(apps)
        self.assertEqual(found, [])
        self.assertEqual(missing, ["Mu Editor"])

    def test_no_browser_or_game_presets(self):
        names = {a["name"].lower() for a in k.BUILTIN_APPS}
        for banned in (
            "firefox", "chrome", "chromium", "edge", "opera", "brave",
            "minecraft", "steam", "roblox", "epic games",
        ):
            self.assertNotIn(banned, names)

    def test_office_exes_match(self):
        candidates = {
            r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE",
            r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE",
            r"C:\Program Files\Microsoft Office\root\Office16\OUTLOOK.EXE",
            r"C:\Program Files\Microsoft Office\root\Office16\ONENOTE.EXE",
            r"C:\Program Files\Microsoft Office\root\Office16\MSACCESS.EXE",
            r"C:\Program Files\Microsoft Office\root\Office16\MSPUB.EXE",
            r"C:\Program Files\Microsoft Office\root\Office16\VISIO.EXE",
            r"C:\Program Files\Microsoft Office\root\Office16\WINPROJ.EXE",
        }
        names = {
            "Microsoft Excel", "Microsoft PowerPoint", "Microsoft Outlook",
            "Microsoft OneNote", "Microsoft Access", "Microsoft Publisher",
            "Microsoft Visio", "Microsoft Project",
        }
        apps = [a for a in k.BUILTIN_APPS if a["name"] in names]
        with mock.patch.object(k, "gather_candidates", return_value=candidates):
            found, missing = k.discover_apps(apps)
        self.assertEqual({a["name"] for a in found}, names)
        self.assertEqual(missing, [])

    def test_vim_matches_gvim_not_neovim(self):
        apps = [a for a in k.BUILTIN_APPS if a["name"] == "Vim"]
        candidates = {r"C:\Vim\vim91\gvim.exe", "/usr/bin/vim"}
        with mock.patch.object(k, "gather_candidates", return_value=candidates):
            found, missing = k.discover_apps(apps)
        self.assertEqual(len(found), 1)
        self.assertEqual(missing, [])
        # neovim/nvim must NOT match the anchored "vim" pattern
        with mock.patch.object(
            k, "gather_candidates", return_value={"/usr/bin/nvim", "/usr/bin/neovim"}
        ):
            found, missing = k.discover_apps(apps)
        self.assertEqual(found, [])
        self.assertEqual(missing, ["Vim"])

    def test_notepadpp_and_sublime_match(self):
        apps = [a for a in k.BUILTIN_APPS if a["name"] in ("Notepad++", "Sublime Text")]
        candidates = {
            r"C:\Program Files\Notepad++\notepad++.exe",
            r"C:\Program Files\Sublime Text\sublime_text.exe",
        }
        with mock.patch.object(k, "gather_candidates", return_value=candidates):
            found, missing = k.discover_apps(apps)
        self.assertEqual({a["name"] for a in found}, {"Notepad++", "Sublime Text"})
        self.assertEqual(missing, [])

    def test_gedit_does_not_match_regedit(self):
        apps = [a for a in k.BUILTIN_APPS if a["name"] == "gedit"]
        with mock.patch.object(k, "gather_candidates", return_value={"/bin/regedit"}):
            found, missing = k.discover_apps(apps)
        self.assertEqual(found, [])
        self.assertEqual(missing, ["gedit"])
        with mock.patch.object(k, "gather_candidates", return_value={"/bin/gedit"}):
            found, missing = k.discover_apps(apps)
        self.assertEqual(len(found), 1)

    def test_emacs_does_not_match_ctags_emacs(self):
        apps = [a for a in k.BUILTIN_APPS if a["name"] == "Emacs"]
        with mock.patch.object(k, "gather_candidates", return_value={"/bin/ctags.emacs"}):
            found, missing = k.discover_apps(apps)
        self.assertEqual(found, [])
        self.assertEqual(missing, ["Emacs"])
        with mock.patch.object(
            k, "gather_candidates",
            return_value={r"C:\Program Files\Emacs\emacs\bin\runemacs.exe"},
        ):
            found, missing = k.discover_apps(apps)
        self.assertEqual(len(found), 1)


class TestHotkeyBlocking(unittest.TestCase):
    def test_win_keys_always_blocked(self):
        self.assertTrue(k.is_blocked_hotkey(k.VK_LWIN, False, False))
        self.assertTrue(k.is_blocked_hotkey(k.VK_RWIN, False, False))

    def test_alt_tab_and_alt_space_blocked(self):
        self.assertTrue(k.is_blocked_hotkey(k.VK_TAB, alt_down=True, ctrl_down=False))
        self.assertTrue(k.is_blocked_hotkey(k.VK_SPACE, alt_down=True, ctrl_down=False))

    def test_plain_tab_and_space_not_blocked(self):
        self.assertFalse(k.is_blocked_hotkey(k.VK_TAB, False, False))
        self.assertFalse(k.is_blocked_hotkey(k.VK_SPACE, False, False))

    def test_escape_with_ctrl_or_alt_blocked(self):
        self.assertTrue(k.is_blocked_hotkey(k.VK_ESCAPE, False, True))   # Ctrl+Esc
        self.assertTrue(k.is_blocked_hotkey(k.VK_ESCAPE, True, False))   # Alt+Esc
        self.assertTrue(k.is_blocked_hotkey(k.VK_ESCAPE, True, True))    # Ctrl+Alt+Esc

    def test_plain_escape_not_blocked(self):
        # Plain Esc is handled by the app itself (admin prompt), not the hook.
        self.assertFalse(k.is_blocked_hotkey(k.VK_ESCAPE, False, False))

    def test_alt_shift_allowed_for_language_switch(self):
        for vk in (k.VK_SHIFT, k.VK_LSHIFT, k.VK_RSHIFT):
            self.assertFalse(
                k.is_blocked_hotkey(vk, alt_down=True, ctrl_down=False)
            )

    def test_alt_f4_blocked(self):
        self.assertTrue(k.is_blocked_hotkey(0x73, alt_down=True, ctrl_down=False))

    def test_ctrl_alt_delete_blocked(self):
        self.assertTrue(k.is_blocked_hotkey(k.VK_DELETE, alt_down=True, ctrl_down=True))

    def test_delete_without_ctrl_alt_not_blocked(self):
        self.assertFalse(k.is_blocked_hotkey(k.VK_DELETE, False, False))
        self.assertFalse(k.is_blocked_hotkey(k.VK_DELETE, True, False))
        self.assertFalse(k.is_blocked_hotkey(k.VK_DELETE, False, True))


class TestAddRemoveApps(unittest.TestCase):
    def test_add_app_appends_normalized(self):
        apps = []
        k.add_app(apps, {"name": "GIMP", "patterns": "gimp$", "args": "--flag"})
        self.assertEqual(len(apps), 1)
        self.assertEqual(apps[0]["name"], "GIMP")
        self.assertEqual(apps[0]["patterns"], ["gimp$"])
        self.assertEqual(apps[0]["args"], ["--flag"])

    def test_add_app_rejects_invalid(self):
        apps = []
        with self.assertRaises(ValueError):
            k.add_app(apps, {"name": "", "patterns": ["x$"]})
        with self.assertRaises(ValueError):
            k.add_app(apps, {"name": "X", "patterns": []})
        self.assertEqual(apps, [])

    def test_remove_apps_by_name(self):
        apps = [
            {"name": "GIMP", "patterns": ["gimp$"], "args": []},
            {"name": "Scratch", "patterns": ["scratch$"], "args": []},
        ]
        removed = k.remove_apps(apps, ["gimp"])  # case-insensitive
        self.assertEqual(removed, 1)
        self.assertEqual([a["name"] for a in apps], ["Scratch"])

    def test_remove_apps_is_case_insensitive(self):
        apps = [{"name": "GIMP", "patterns": ["gimp$"], "args": []}]
        k.remove_apps(apps, ["Gimp"])
        self.assertEqual(apps, [])

    def test_remove_apps_accepts_single_string(self):
        apps = [
            {"name": "A", "patterns": ["a$"], "args": []},
            {"name": "B", "patterns": ["b$"], "args": []},
        ]
        k.remove_apps(apps, "B")
        self.assertEqual([a["name"] for a in apps], ["A"])

    def test_remove_apps_missing_name_is_noop(self):
        apps = [{"name": "A", "patterns": ["a$"], "args": []}]
        removed = k.remove_apps(apps, ["nope"])
        self.assertEqual(removed, 0)
        self.assertEqual(len(apps), 1)

    def test_remove_apps_ignores_nonstring_names(self):
        apps = [
            {"name": "A", "patterns": ["a$"], "args": []},
            {"name": "B", "patterns": ["b$"], "args": []},
        ]
        removed = k.remove_apps(apps, [123, "A"])
        self.assertEqual(removed, 1)
        self.assertEqual([a["name"] for a in apps], ["B"])


class TestSetPassword(unittest.TestCase):
    def test_set_password_updates_and_verifies(self):
        cfg = k.seed_config()
        k.set_password(cfg, "newpass")
        self.assertTrue(k.verify_password("newpass", cfg["password"]))
        self.assertFalse(k.verify_password(k.DEFAULT_PASSWORD, cfg["password"]))

    def test_set_password_changes_salt(self):
        cfg = k.seed_config()
        old_salt = cfg["password"]["salt"]
        k.set_password(cfg, "newpass")
        self.assertNotEqual(old_salt, cfg["password"]["salt"])


class TestErrorReportingAndBundling(unittest.TestCase):
    def test_fatal_error_writes_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(k, "_base_dir", return_value=tmp), \
                 mock.patch("sys.stderr"):
                k.fatal_error("boom failure")
            log = os.path.join(tmp, "kiosk-error.log")
            self.assertTrue(os.path.exists(log))
            with open(log, encoding="utf-8") as f:
                self.assertIn("boom failure", f.read())

    def test_bundled_apps_path_none_when_not_frozen(self):
        with mock.patch.object(sys, "frozen", False, create=True):
            self.assertIsNone(k._bundled_apps_path())

    def test_bundled_apps_path_finds_meipass(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "apps.json"), "w", encoding="utf-8") as f:
                f.write("[]")
            with mock.patch.object(sys, "frozen", True, create=True), \
                 mock.patch.object(sys, "_MEIPASS", tmp, create=True):
                self.assertEqual(
                    k._bundled_apps_path(), os.path.join(tmp, "apps.json")
                )

    def test_load_apps_copies_bundled_when_frozen(self):
        with tempfile.TemporaryDirectory() as bundle, \
             tempfile.TemporaryDirectory() as exedir:
            bundled = os.path.join(bundle, "apps.json")
            k.save_apps([{"name": "Bundled", "patterns": ["b$"], "args": []}], bundled)
            target = os.path.join(exedir, "apps.json")
            with mock.patch.object(sys, "frozen", True, create=True), \
                 mock.patch.object(sys, "_MEIPASS", bundle, create=True):
                apps, _ = k.load_apps(target)
            self.assertEqual([a["name"] for a in apps], ["Bundled"])
            self.assertTrue(os.path.exists(target))  # copied next to the exe


class TestLayoutPresets(unittest.TestCase):
    def test_auto_preset_picks_by_screen_width(self):
        self.assertEqual(k.resolve_card_preset("auto", 1024), k.CARD_PRESETS["small"])
        self.assertEqual(k.resolve_card_preset("auto", 1280), k.CARD_PRESETS["medium"])
        self.assertEqual(k.resolve_card_preset("auto", 1920), k.CARD_PRESETS["large"])

    def test_explicit_preset_wins(self):
        self.assertEqual(k.resolve_card_preset("small", 3000), k.CARD_PRESETS["small"])
        self.assertEqual(k.resolve_card_preset("large", 640), k.CARD_PRESETS["large"])

    def test_unknown_key_behaves_like_auto(self):
        self.assertEqual(k.resolve_card_preset("bogus", 1024), k.CARD_PRESETS["small"])

    def test_auto_columns(self):
        self.assertEqual(k.auto_columns(950, 180), 4)
        self.assertEqual(k.auto_columns(1000, 180), 5)
        self.assertEqual(k.auto_columns(400, 180), 1)
        self.assertEqual(k.auto_columns(1920, 220), 8)
        self.assertEqual(k.auto_columns(0, 180), 1)

    def test_auto_columns_tolerates_bad_input(self):
        self.assertEqual(k.auto_columns(None, 180), 1)
        self.assertEqual(k.auto_columns("bogus", 180), 1)

    def test_resolve_card_preset_tolerates_bad_input(self):
        self.assertEqual(k.resolve_card_preset("auto", None), k.CARD_PRESETS["small"])
        self.assertEqual(k.resolve_card_preset("auto", "bogus"), k.CARD_PRESETS["small"])


class TestCliAndBuild(unittest.TestCase):
    def test_default_paths_use_base_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(k, "_base_dir", return_value=tmp):
                self.assertEqual(k.default_config_path(), os.path.join(tmp, "kiosk_config.json"))
                self.assertEqual(k.default_apps_path(), os.path.join(tmp, "apps.json"))
                self.assertEqual(k.error_log_path(), os.path.join(tmp, "kiosk-error.log"))

    def test_base_dir_frozen_uses_executable_dir(self):
        fake_exe = os.path.join("some", "dir", "Kiosk.exe")
        with mock.patch.object(sys, "frozen", True, create=True), \
             mock.patch.object(sys, "executable", fake_exe):
            self.assertEqual(k._base_dir(), os.path.dirname(os.path.abspath(fake_exe)))

    def test_install_excepthook_routes_to_fatal_error(self):
        old = sys.excepthook
        self.addCleanup(setattr, sys, "excepthook", old)
        k._install_excepthook()
        with mock.patch.object(k, "fatal_error") as m:
            sys.excepthook(ValueError, ValueError("x"), None)
        m.assert_called_once()

    def test_set_password_handles_getpass_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = k.argparse.Namespace(config=os.path.join(tmp, "config.json"))
            with mock.patch("getpass.getpass", side_effect=EOFError("no tty")):
                with mock.patch("sys.stderr"):
                    with self.assertRaises(SystemExit) as cm:
                        k.cmd_set_password(args)
            self.assertNotEqual(cm.exception.code, 0)

    def test_kiosk_spec_bundles_apps_and_pyside6(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "Kiosk.spec"), encoding="utf-8") as f:
            spec = f.read()
        self.assertIn("collect_all('PySide6')", spec)
        self.assertIn("'apps.json'", spec)
        self.assertIn("console=False", spec)
        self.assertIn("upx=False", spec)

    def test_cmd_scan_prints_results(self):
        args = k.argparse.Namespace(config="/tmp/c.json", apps="/tmp/a.json")
        with mock.patch.object(k, "load_config", return_value=({}, "/tmp/c.json")), \
             mock.patch.object(
                 k, "load_apps",
                 return_value=([{"name": "Alpha", "patterns": ["a$"], "args": []}], "/tmp/a.json"),
             ), \
             mock.patch.object(
                 k, "discover_apps",
                 return_value=([{"name": "Alpha", "path": "/x/alpha", "args": []}], ["Beta"]),
             ):
            with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
                k.cmd_scan(args)
        text = out.getvalue()
        self.assertIn("Alpha", text)
        self.assertIn("/x/alpha", text)
        self.assertIn("Beta", text)

    def test_cmd_diagnose_writes_report(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        args = k.argparse.Namespace(config=None, apps=None)
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(k, "_base_dir", return_value=tmp), \
                 mock.patch.object(k, "load_apps", return_value=([], os.path.join(tmp, "apps.json"))), \
                 mock.patch.object(k, "gather_candidates", return_value=set()), \
                 mock.patch.object(k, "discover_apps", return_value=([], [])), \
                 mock.patch("sys.stdout", new_callable=io.StringIO):
                k.cmd_diagnose(args)
            report = os.path.join(tmp, "kiosk-diagnose.log")
            self.assertTrue(os.path.exists(report))
            with open(report, encoding="utf-8") as f:
                content = f.read()
            self.assertIn("diagnostic", content.lower())
            self.assertIn("python", content.lower())


class TestDesktopExecPaths(unittest.TestCase):
    @unittest.skipIf(os.name == "nt", "POSIX-only")
    def test_parses_exec_field(self):
        with tempfile.TemporaryDirectory() as d:
            bin_dir = os.path.join(d, "bin")
            os.makedirs(bin_dir)
            absolute = os.path.join(bin_dir, "myapp")
            rel_bin = os.path.join(bin_dir, "relapp")
            for p in (absolute, rel_bin):
                with open(p, "w"):
                    pass
            os.chmod(rel_bin, 0o755)  # shutil.which requires executable

            desktop = os.path.join(d, "apps")
            os.makedirs(desktop)
            with open(os.path.join(desktop, "a.desktop"), "w", encoding="utf-8") as f:
                f.write("[Desktop Entry]\nExec=%s --flag %%U\n" % absolute)
            with open(os.path.join(desktop, "b.desktop"), "w", encoding="utf-8") as f:
                f.write("[Desktop Entry]\nExec=relapp %%f\n")
            with open(os.path.join(desktop, "c.desktop"), "w", encoding="utf-8") as f:
                f.write("[Desktop Entry]\nExec=env VAR=x %s\n" % absolute)

            with mock.patch.dict(os.environ, {"PATH": bin_dir}):
                got = k._desktop_exec_paths(dirs=[desktop])
            self.assertIn(absolute, got)
            self.assertIn(rel_bin, got)


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

    def test_ext_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "a.exe"), "w"):
                pass
            with open(os.path.join(tmp, "a.txt"), "w"):
                pass
            got = set(k._walk_depth(tmp, max_depth=1, exts=(".exe",)))
            self.assertIn(os.path.join(tmp, "a.exe"), got)
            self.assertNotIn(os.path.join(tmp, "a.txt"), got)

    def test_depth_zero_only_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "sub"))
            root_file = os.path.join(tmp, "root.txt")
            sub_file = os.path.join(tmp, "sub", "sub.txt")
            for p in (root_file, sub_file):
                with open(p, "w"):
                    pass
            got = set(k._walk_depth(tmp, max_depth=0))
            self.assertIn(root_file, got)
            self.assertNotIn(sub_file, got)


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

    def test_launch_without_path_returns_error(self):
        self.assertIsNotNone(k.launch({"args": []}))
        self.assertIsNotNone(k.launch({}))

    def test_launch_coerces_string_args(self):
        with mock.patch.object(k.subprocess, "Popen") as m:
            err = k.launch({"path": "/bin/x", "args": "--flag --two"})
        self.assertIsNone(err)
        m.assert_called_once()
        self.assertEqual(m.call_args[0][0], ["/bin/x", "--flag", "--two"])

    def test_launch_windows_windowsapps_branch(self):
        path = r"C:\Users\kid\AppData\Local\Microsoft\WindowsApps\foo.exe"
        with mock.patch.object(k.os, "name", "nt"):
            with mock.patch.object(k.subprocess, "Popen") as m:
                err = k.launch({"path": path, "args": ["--x"]})
        self.assertIsNone(err)
        m.assert_called_once()
        self.assertEqual(m.call_args[0][0], ["cmd", "/c", "start", "", path, "--x"])

    def test_launch_windows_normal_branch(self):
        path = r"C:\Kiosk\Kiosk.exe"
        with mock.patch.object(k.os, "name", "nt"):
            with mock.patch.object(k.subprocess, "Popen") as m:
                err = k.launch({"path": path, "args": []})
        self.assertIsNone(err)
        m.assert_called_once()
        self.assertEqual(m.call_args[0][0], [path])


if __name__ == "__main__":
    unittest.main()
