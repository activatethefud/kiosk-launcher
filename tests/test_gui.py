"""GUI behavior tests — "click around" the launcher offscreen.

Run with:
    python3 -m unittest discover -s tests -v
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import kiosk_launcher as k  # noqa: E402

from PySide6.QtCore import Qt, QTimer  # noqa: E402
from PySide6.QtGui import QFont, QFontMetrics  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
)

_APP = None


def setUpModule():
    global _APP
    _APP = QApplication.instance() or QApplication([])


def tearDownModule():
    global _APP
    if _APP is not None:
        _APP.quit()


# ---------------------------------------------------------------------------
# Helpers for driving modal dialogs and popups from timers
# ---------------------------------------------------------------------------
def _active_modal():
    w = QApplication.activeModalWidget()
    if w is not None:
        return w
    for w in QApplication.topLevelWidgets():
        if isinstance(w, (QDialog, QMessageBox)) and w.isVisible():
            return w
    return None


def _active_menu():
    w = QApplication.activePopupWidget()
    if isinstance(w, QMenu):
        return w
    for w in QApplication.topLevelWidgets():
        if isinstance(w, QMenu) and w.isVisible():
            return w
    return None


def _fill_input(text):
    dlg = _active_modal()
    assert dlg is not None, "no modal input dialog open"
    for le in dlg.findChildren(QLineEdit):
        le.setText(text)
        break
    dlg.accept()
    return dlg


def _dismiss_message():
    w = _active_modal()
    if w is not None and isinstance(w, (QMessageBox, QDialog)):
        w.accept()


def _click_ok(dlg):
    for b in dlg.findChildren(QPushButton):
        if "OK" in b.text():
            QTest.mouseClick(b, Qt.LeftButton)
            return True
    dlg.accept()
    return False


def _trigger_menu(substring):
    menu = _active_menu()
    if menu is None:
        return False
    for action in menu.actions():
        if substring in action.text():
            action.trigger()
            return True
    return False


class GuiTestBase(unittest.TestCase):
    def make_window(self, kiosk=False, apps=None, password="secret", card_size=None, columns=None):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        cfg = k.seed_config()
        k.set_password(cfg, password)
        if card_size is not None:
            cfg["card_size"] = card_size
        if columns is not None:
            cfg["columns"] = columns
        cfg_path = os.path.join(tmp, "config.json")
        apps_path = os.path.join(tmp, "apps.json")
        if apps is None:
            apps = [
                {"name": "Alpha", "patterns": ["alpha$"], "args": []},
                {"name": "Beta", "patterns": ["beta$"], "args": []},
            ]
        k.save_apps(apps, apps_path)
        win = k.MainWindow(cfg, cfg_path, apps, apps_path, kiosk=kiosk)
        win.show()
        self._win = win
        return win, cfg, cfg_path, apps_path, apps

    def tearDown(self):
        for w in (QApplication.activeModalWidget(), QApplication.activePopupWidget()):
            if w is not None:
                w.close()
        win = getattr(self, "_win", None)
        if win is not None:
            win.close()
            win.deleteLater()
        QApplication.processEvents()
        QTest.qWait(50)

    @staticmethod
    def _app_buttons(win):
        return [
            b for b in win.findChildren(QPushButton) if b.property("class") == "app"
        ]


# ---------------------------------------------------------------------------
# Grid + launching
# ---------------------------------------------------------------------------
class TestGridAndLaunch(GuiTestBase):
    def test_grid_builds_one_button_per_found_app(self):
        found = [
            {"name": "Alpha", "path": "/usr/bin/alpha", "args": []},
            {"name": "Beta", "path": "/usr/bin/beta", "args": []},
        ]
        with mock.patch.object(k, "discover_apps", return_value=(found, [])):
            win, *_ = self.make_window()
        self.assertEqual(len(self._app_buttons(win)), 2)
        self.assertIsNotNone(win.findChild(QPushButton, "app:Alpha"))
        self.assertIsNotNone(win.findChild(QPushButton, "app:Beta"))

    def test_missing_apps_reported_in_status(self):
        found = [{"name": "Alpha", "path": "/usr/bin/alpha", "args": []}]
        with mock.patch.object(k, "discover_apps", return_value=(found, ["Beta"])):
            win, *_ = self.make_window()
        self.assertIn("missing: Beta", win.status_label.text())

    def test_click_app_launches_it(self):
        found = [{"name": "Alpha", "path": "/usr/bin/alpha", "args": ["--x"]}]
        with mock.patch.object(k, "discover_apps", return_value=(found, [])):
            win, *_ = self.make_window()
        btn = win.findChild(QPushButton, "app:Alpha")
        self.assertIsNotNone(btn)
        with mock.patch.object(k, "launch", return_value=None) as m:
            QTest.mouseClick(btn, Qt.LeftButton)
        m.assert_called_once()
        self.assertEqual(m.call_args[0][0]["name"], "Alpha")
        self.assertEqual(m.call_args[0][0]["args"], ["--x"])

    def test_launch_error_shows_message(self):
        found = [{"name": "Alpha", "path": "/x/alpha", "args": []}]
        with mock.patch.object(k, "discover_apps", return_value=(found, [])):
            win, *_ = self.make_window()
        seen = []

        def dismiss():
            w = _active_modal()
            if isinstance(w, QMessageBox):
                seen.append(w)
                w.accept()

        QTimer.singleShot(100, dismiss)
        with mock.patch.object(k, "launch", return_value="boom"):
            win.launch(found[0])
        self.assertEqual(len(seen), 1)


# ---------------------------------------------------------------------------
# Admin flow
# ---------------------------------------------------------------------------
class TestAdminFlow(GuiTestBase):
    def test_wrong_password_is_denied(self):
        win, *_ = self.make_window(password="secret")
        seen_warning = []

        def enter_wrong():
            _fill_input("wrong")

        def note_and_dismiss():
            seen_warning.append(_active_modal())
            _dismiss_message()

        QTimer.singleShot(100, enter_wrong)
        QTimer.singleShot(400, note_and_dismiss)
        win.on_admin()
        self.assertEqual(len(seen_warning), 1)
        self.assertIsInstance(seen_warning[0], QMessageBox)
        self.assertIsNone(_active_menu())

    def test_correct_password_opens_menu(self):
        win, *_ = self.make_window(password="secret")
        seen_menu = []

        def close_menu():
            menu = _active_menu()
            if menu is not None:
                seen_menu.append(menu)
                menu.close()

        QTimer.singleShot(100, lambda: _fill_input("secret"))
        QTimer.singleShot(400, close_menu)
        win.on_admin()
        self.assertEqual(len(seen_menu), 1)

    def test_admin_cancel_does_nothing(self):
        win, *_ = self.make_window(password="secret")

        def cancel():
            dlg = _active_modal()
            if dlg is not None:
                dlg.reject()

        QTimer.singleShot(100, cancel)
        win.on_admin()
        self.assertIsNone(_active_menu())

    def test_add_app_dialog_values_direct(self):
        dlg = k.AddAppDialog()
        self.addCleanup(dlg.deleteLater)
        dlg.name_edit.setText("Gamma")
        dlg.patterns_edit.setPlainText("gamma$\nbeta$")
        dlg.args_edit.setText("--flag --two")
        v = dlg.values()
        self.assertEqual(v["name"], "Gamma")
        self.assertEqual(v["patterns"], ["gamma$", "beta$"])
        self.assertEqual(v["args"], ["--flag", "--two"])

    def test_add_app_flow(self):
        win, cfg, cfg_path, apps_path, apps = self.make_window(password="secret")

        def fill_add_dialog():
            dlg = _active_modal()
            assert dlg is not None
            dlg.findChild(QLineEdit, "addapp_name").setText("Gamma")
            dlg.findChild(QPlainTextEdit, "addapp_patterns").setPlainText("gamma$")
            _click_ok(dlg)

        QTimer.singleShot(100, lambda: _fill_input("secret"))
        QTimer.singleShot(300, lambda: _trigger_menu("Add app"))
        QTimer.singleShot(600, fill_add_dialog)
        win.on_admin()

        self.assertIn("Gamma", [a["name"] for a in win.apps])
        loaded, _ = k.load_apps(apps_path)
        self.assertIn("Gamma", [a["name"] for a in loaded])

    def test_remove_app_flow(self):
        win, cfg, cfg_path, apps_path, apps = self.make_window(password="secret")
        self.assertEqual(len(win.apps), 2)

        def fill_remove_dialog():
            dlg = _active_modal()
            assert dlg is not None
            lw = dlg.findChild(QListWidget, "removeapp_list")
            lw.item(0).setSelected(True)
            _click_ok(dlg)

        QTimer.singleShot(100, lambda: _fill_input("secret"))
        QTimer.singleShot(300, lambda: _trigger_menu("Remove app"))
        QTimer.singleShot(600, fill_remove_dialog)
        win.on_admin()

        self.assertEqual(len(win.apps), 1)
        loaded, _ = k.load_apps(apps_path)
        self.assertEqual(len(loaded), 1)

    def test_change_password_flow(self):
        win, cfg, cfg_path, apps_path, apps = self.make_window(password="old")

        QTimer.singleShot(100, lambda: _fill_input("old"))
        QTimer.singleShot(300, lambda: _trigger_menu("Change password"))
        QTimer.singleShot(500, lambda: _fill_input("newpass"))
        QTimer.singleShot(700, lambda: _fill_input("newpass"))
        QTimer.singleShot(900, _dismiss_message)
        win.on_admin()

        self.assertTrue(k.verify_password("newpass", win.cfg["password"]))
        self.assertFalse(k.verify_password("old", win.cfg["password"]))

    def test_add_app_invalid_regex_shows_warning(self):
        win, *_ = self.make_window(password="secret")
        warnings = []

        def fill_bad():
            dlg = _active_modal()
            dlg.findChild(QLineEdit, "addapp_name").setText("Gamma")
            dlg.findChild(QPlainTextEdit, "addapp_patterns").setPlainText("(unclosed")
            _click_ok(dlg)

        def dismiss_warning():
            w = _active_modal()
            if isinstance(w, QMessageBox):
                warnings.append(w)
                w.accept()

        def reject_dialog():
            dlg = _active_modal()
            if dlg is not None:
                dlg.reject()

        QTimer.singleShot(100, lambda: _fill_input("secret"))
        QTimer.singleShot(300, lambda: _trigger_menu("Add app"))
        QTimer.singleShot(600, fill_bad)
        QTimer.singleShot(900, dismiss_warning)
        QTimer.singleShot(1100, reject_dialog)
        win.on_admin()

        self.assertEqual(len(warnings), 1)
        self.assertNotIn("Gamma", [a["name"] for a in win.apps])

    def test_add_app_empty_name_shows_warning(self):
        win, *_ = self.make_window(password="secret")
        warnings = []

        def fill_empty():
            dlg = _active_modal()
            dlg.findChild(QLineEdit, "addapp_name").setText("")
            dlg.findChild(QPlainTextEdit, "addapp_patterns").setPlainText("gamma$")
            _click_ok(dlg)

        def dismiss_warning():
            w = _active_modal()
            if isinstance(w, QMessageBox):
                warnings.append(w)
                w.accept()

        def reject_dialog():
            dlg = _active_modal()
            if dlg is not None:
                dlg.reject()

        QTimer.singleShot(100, lambda: _fill_input("secret"))
        QTimer.singleShot(300, lambda: _trigger_menu("Add app"))
        QTimer.singleShot(600, fill_empty)
        QTimer.singleShot(900, dismiss_warning)
        QTimer.singleShot(1100, reject_dialog)
        win.on_admin()

        self.assertEqual(len(warnings), 1)
        self.assertNotIn("Gamma", [a["name"] for a in win.apps])


# ---------------------------------------------------------------------------
# Kiosk-mode behavior
# ---------------------------------------------------------------------------
class TestKioskBehavior(GuiTestBase):
    def test_escape_key_opens_admin_prompt(self):
        win, *_ = self.make_window(kiosk=True, password="secret")
        seen_menu = []

        def close_menu():
            menu = _active_menu()
            if menu is not None:
                seen_menu.append(menu)
                menu.close()

        QTimer.singleShot(100, lambda: _fill_input("secret"))
        QTimer.singleShot(400, close_menu)
        QTest.keyClick(win, Qt.Key_Escape)
        self.assertEqual(len(seen_menu), 1)

    def test_f11_key_opens_admin_prompt(self):
        win, *_ = self.make_window(kiosk=True, password="secret")
        seen_menu = []

        def close_menu():
            menu = _active_menu()
            if menu is not None:
                seen_menu.append(menu)
                menu.close()

        QTimer.singleShot(100, lambda: _fill_input("secret"))
        QTimer.singleShot(400, close_menu)
        QTest.keyClick(win, Qt.Key_F11)
        self.assertEqual(len(seen_menu), 1)

    def test_programmatic_close_does_not_prompt(self):
        win, *_ = self.make_window(kiosk=True, password="secret")
        win.close()  # non-spontaneous → must not show a password dialog
        QApplication.processEvents()
        self.assertIsNone(QApplication.activeModalWidget())
        self.assertFalse(win.isVisible())

    def test_live_reload_on_apps_file_change(self):
        def fake_discover(apps):
            found = [
                {"name": a["name"], "path": "/x/" + a["name"], "args": a.get("args", [])}
                for a in apps
            ]
            return found, []

        with mock.patch.object(k, "discover_apps", side_effect=fake_discover):
            win, cfg, cfg_path, apps_path, apps = self.make_window()
            self.assertEqual(len(self._app_buttons(win)), 2)

            new_apps = apps + [{"name": "Gamma", "patterns": ["gamma$"], "args": []}]
            k.save_apps(new_apps, apps_path)

            QTest.qWait(900)  # debounce (400ms) + reload + rebuild
            self.assertEqual(len(win.apps), 3)
            self.assertEqual(len(self._app_buttons(win)), 3)

    def test_reload_with_broken_apps_falls_back_to_presets(self):
        with mock.patch.object(k, "discover_apps", return_value=([], [])):
            win, cfg, cfg_path, apps_path, apps = self.make_window()
        with open(apps_path, "w", encoding="utf-8") as f:
            f.write("{ not valid json")
        with mock.patch.object(k, "discover_apps", return_value=([], [])):
            win._reload_apps()
        self.assertEqual(win.apps, k.BUILTIN_APPS)


class TestTextWrapping(GuiTestBase):
    @staticmethod
    def _font():
        f = QFont()
        f.setPixelSize(20)
        f.setWeight(QFont.Weight.DemiBold)
        return f

    def test_wrapped_lines_fit_max_width(self):
        fm = QFontMetrics(self._font())
        for name in (
            "Microsoft PowerPoint",
            "Visual Studio Code",
            "IntelliJ IDEA",
            "Microsoft Publisher",
            "A" * 40,
        ):
            wrapped = k.wrap_text(name, self._font(), 130)
            for line in wrapped.split("\n"):
                self.assertLessEqual(fm.horizontalAdvance(line), 130)

    def test_long_name_wraps_to_multiple_lines(self):
        wrapped = k.wrap_text("Microsoft PowerPoint", self._font(), 130)
        self.assertGreaterEqual(len(wrapped.split("\n")), 2)

    def test_short_name_stays_single_line(self):
        wrapped = k.wrap_text("GIMP", self._font(), 130)
        self.assertEqual(wrapped, "GIMP")

    def test_wrap_text_nonstring_and_empty(self):
        self.assertEqual(k.wrap_text(None, self._font(), 130), "")
        self.assertEqual(k.wrap_text("", self._font(), 130), "")
        self.assertEqual(k.wrap_text(123, self._font(), 130), "123")


class TestLayoutAndOverflow(GuiTestBase):
    def test_kiosk_fullscreen_matches_screen(self):
        win, *_ = self.make_window(kiosk=True, password="secret")
        win.showFullScreen()
        QTest.qWait(300)
        screen = QApplication.primaryScreen()
        self.assertEqual(win.size(), screen.geometry().size())
        self.assertTrue(win.windowFlags() & Qt.FramelessWindowHint)

    def test_many_apps_scroll_not_overflow(self):
        apps = [
            {"name": f"App{i}", "patterns": [f"app{i}$"], "args": []}
            for i in range(40)
        ]
        found = [
            {"name": a["name"], "path": "/x/" + a["name"], "args": []}
            for a in apps
        ]
        with mock.patch.object(k, "discover_apps", return_value=(found, [])):
            win, *_ = self.make_window(kiosk=False, card_size="medium")
        QTest.qWait(300)

        # Window stays at its configured size — it does not grow to fit 40 apps.
        self.assertEqual((win.width(), win.height()), (1000, 700))
        scroll = win.findChild(QScrollArea)
        self.assertIsNotNone(scroll)
        # Overflow becomes a vertical scrollbar, never a horizontal one.
        self.assertGreater(scroll.verticalScrollBar().maximum(), 0)
        self.assertEqual(scroll.horizontalScrollBar().maximum(), 0)
        # Buttons keep their fixed size — they are never stretched.
        for b in self._app_buttons(win)[:5]:
            self.assertEqual((b.width(), b.height()), (180, 130))

    def test_card_size_preset_changes_button_size(self):
        found = [{"name": "Alpha", "path": "/x/alpha", "args": []}]
        with mock.patch.object(k, "discover_apps", return_value=(found, [])):
            win, *_ = self.make_window(card_size="small")
        btn = win.findChild(QPushButton, "app:Alpha")
        self.assertIsNotNone(btn)
        self.assertEqual((btn.width(), btn.height()), (150, 110))

    def test_fixed_columns_override(self):
        found = [{"name": f"A{i}", "path": f"/x/a{i}", "args": []} for i in range(10)]
        with mock.patch.object(k, "discover_apps", return_value=(found, [])):
            win, *_ = self.make_window(columns=3)
        self.assertEqual(win._compute_columns(), 3)

    def test_version_label_shows_version(self):
        with mock.patch.object(k, "discover_apps", return_value=([], [])):
            win, *_ = self.make_window()
        lbl = win.findChild(QLabel, "version_label")
        self.assertIsNotNone(lbl)
        self.assertEqual(lbl.text(), f"v{k.VERSION}")


if __name__ == "__main__":
    unittest.main()
