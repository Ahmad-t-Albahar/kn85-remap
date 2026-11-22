"""Automated checks of the window: accessible names (MSAA), mnemonics, tab
order and the add / remove / apply / restore flows in dry-run mode.

The window is never shown and no keys or clicks are sent anywhere.
This is automated evidence only; it does not replace a check with NVDA.
"""

import ctypes
import io
import os
import sys
import tempfile
import time
import types
import unittest
from ctypes import POINTER, byref

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import wx  # noqa: E402

import kn85_protocol as p  # noqa: E402
import remap_store  # noqa: E402

try:
    import comtypes.client
    IAccessible = comtypes.client.GetModule("oleacc.dll").IAccessible
except Exception:  # pragma: no cover
    IAccessible = None


def msaa_name(window):
    acc = POINTER(IAccessible)()
    ctypes.oledll.oleacc.AccessibleObjectFromWindow(
        window.GetHandle(), ctypes.c_long(-4), byref(IAccessible._iid_), byref(acc))
    return acc.accName(0)


class GuiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.App()
        import kn85_gui
        cls.gui = kn85_gui

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "kn85-remaps.json")
        self.boxes = []
        self.answer = wx.YES

        def fake_box(message, caption="", style=0, parent=None):
            self.boxes.append(message)
            return self.answer
        self._orig_box = wx.MessageBox
        wx.MessageBox = fake_box
        self._stdout = sys.stdout
        sys.stdout = io.StringIO()  # dry-run report output
        self.f = self.gui.MainFrame(types.SimpleNamespace(dry_run=True, file=self.path))
        self.pump()

    def tearDown(self):
        sys.stdout = self._stdout
        wx.MessageBox = self._orig_box
        self.f.Destroy()
        self.pump()
        self.dir.cleanup()

    def pump(self, until=None, timeout=5.0):
        end = time.time() + timeout
        while True:
            self.app.Yield(True)
            if until is None or until() or time.time() > end:
                break
            time.sleep(0.02)

    def test_accessible_names(self):
        if IAccessible is None:
            self.skipTest("comtypes not available")
        f = self.f
        expected = {
            f.key_list: "Physical key:",
            f.target_list: "Sends:",
            f.remap_list: "Saved remaps:",
            f.add_btn: "Add or change remap",
            f.remove_btn: "Remove selected remap",
            f.apply_btn: "Apply to keyboard",
            f.defaults_btn: "Restore keyboard defaults...",
            f.check_btn: "Check connection",
            f.close_btn: "Close",
            f.layer: "Layer",
        }
        for ctrl, name in expected.items():
            self.assertEqual(msaa_name(ctrl).replace("&", ""), name)

    def test_mnemonics_unique(self):
        letters = []
        panel = self.f.key_list.GetParent()
        for child in panel.GetChildren():
            label = child.GetLabel()
            if "&" in label.replace("&&", ""):
                letters.append(label[label.index("&") + 1].lower())
        self.assertEqual(len(letters), len(set(letters)), letters)
        self.assertEqual(sorted(letters), sorted("ampdce"))

    def test_tab_order(self):
        f = self.f
        panel = f.key_list.GetParent()
        focusable = [c for c in panel.GetChildren() if c.AcceptsFocus()]
        self.assertEqual(focusable, [f.layer, f.key_list, f.target_list, f.add_btn,
                                     f.remap_list, f.remove_btn, f.apply_btn,
                                     f.defaults_btn, f.check_btn, f.close_btn])

    def test_seed_shown_and_saved(self):
        self.assertEqual(self.f.remap_list.GetStrings(),
                         ["Fn layer: Right Ctrl sends Applications (context menu)"])
        self.assertTrue(os.path.exists(self.path))

    def select_key(self, name):
        self.f.key_list.SetStringSelection(name)
        self.f.on_selection_changed(None)

    def test_selection_shows_current_target(self):
        self.f.layer.SetSelection(1)
        self.select_key("Right Ctrl")
        self.assertEqual(self.f.target_list.GetStringSelection(), "Applications (context menu)")
        self.f.layer.SetSelection(0)
        self.f.on_selection_changed(None)
        self.assertEqual(self.f.target_list.GetStringSelection(), "Default (no change)")

    def test_add_and_remove(self):
        f = self.f
        f.layer.SetSelection(0)
        self.select_key("Caps Lock")
        f.target_list.SetStringSelection("Escape")
        f.on_add(None)
        self.assertIn("Top layer: Caps Lock sends Escape", f.remap_list.GetStrings())
        self.assertEqual(f.remap_list.GetStringSelection(), "Top layer: Caps Lock sends Escape")
        self.assertTrue(f.pending)
        self.assertEqual(remap_store.load(self.path)[p.LAYER_TOP], {55: 0x29})
        # Choosing Default removes it again.
        f.target_list.SetSelection(0)
        f.on_add(None)
        self.assertNotIn("Top layer: Caps Lock sends Escape", f.remap_list.GetStrings())
        self.assertTrue(self.boxes[-1].startswith("Removed"))
        # Remove button
        f.remap_list.SetSelection(0)
        f.on_remove(None)
        self.assertEqual(f.remap_list.GetCount(), 0)
        self.assertIn("now empty", self.boxes[-1])
        f.on_remove(None)
        self.assertEqual(self.boxes[-1], "There is no remap to remove.")

    def test_risky_top_key_asks(self):
        f = self.f
        f.layer.SetSelection(0)
        self.select_key("Tab")
        f.target_list.SetStringSelection("Escape")
        self.answer = wx.NO
        f.on_add(None)
        self.assertIn("Change it anyway?", self.boxes[-1])
        self.assertNotIn(37, f.record[p.LAYER_TOP])

    def test_add_rolls_back_when_save_fails(self):
        f = self.f
        orig = remap_store.save
        def fail(*a, **k):
            raise OSError("disk is read-only")
        remap_store.save = fail
        try:
            f.layer.SetSelection(0)
            self.select_key("Caps Lock")
            f.target_list.SetStringSelection("Escape")
            f.on_add(None)
        finally:
            remap_store.save = orig
        self.assertNotIn(55, f.record[p.LAYER_TOP])
        self.assertIn("Could not save", self.boxes[-1])

    def test_failed_write_marks_pending_and_unlocks(self):
        f = self.f
        f.pending = False
        orig = p.write_all
        def boom(t, rec):
            raise RuntimeError("surprise")
        p.write_all = boom
        try:
            f.on_apply(None)
            self.pump(until=lambda: not f.busy)
        finally:
            p.write_all = orig
        self.assertFalse(f.busy)
        self.assertTrue(f.pending)
        self.assertIn("Apply failed", self.boxes[-1])
        self.assertFalse(remap_store.load_state(self.path)[1])

    def test_applied_flag_persists(self):
        f = self.f
        self.assertTrue(f.pending)  # seed is not yet applied
        f.on_apply(None)
        self.pump(until=lambda: not f.busy)
        self.assertFalse(f.pending)
        self.assertTrue(remap_store.load_state(self.path)[1])

    def test_unreadable_file_is_set_aside(self):
        bad = os.path.join(self.dir.name, "bad.json")
        with open(bad, "w") as fh:
            fh.write("[1, 2")
        f2 = self.gui.MainFrame(types.SimpleNamespace(dry_run=True, file=bad))
        try:
            self.pump()
            self.assertIn("could not be read", self.boxes[-1])
            self.assertEqual(f2.path, bad)
            self.assertFalse(os.path.exists(bad))
            kept = [n for n in os.listdir(self.dir.name) if ".unreadable-" in n]
            self.assertEqual(len(kept), 1)
        finally:
            f2.Destroy()

    def test_apply_dry_run(self):
        f = self.f
        f.on_apply(None)
        self.pump(until=lambda: not f.busy)
        self.assertFalse(f.busy)
        self.assertIn("Dry run finished", self.boxes[-1])
        self.assertIn("Right Ctrl sends Applications", self.boxes[-1])
        out = sys.stdout.getvalue()
        self.assertEqual(out.count("SET 00 04 18"), 2)
        self.assertIn("SET 00 00 00 00 00 00 00 00 00 02 00 65 00", out)

    def test_restore_defaults_cancel_and_confirm(self):
        f = self.f
        self.answer = wx.NO
        f.on_defaults(None)
        self.assertEqual(f.remap_list.GetCount(), 1)
        self.assertIn("Restore keyboard defaults?", self.boxes[-1])
        self.answer = wx.YES
        f.on_defaults(None)
        self.pump(until=lambda: not f.busy and f.remap_list.GetCount() == 0)
        self.assertEqual(f.remap_list.GetCount(), 0)
        self.assertEqual(remap_store.load(self.path), remap_store.empty())
        backups = [n for n in os.listdir(self.dir.name) if ".backup-" in n]
        self.assertEqual(len(backups), 1)
        self.assertEqual(remap_store.load(os.path.join(self.dir.name, backups[0]))[p.LAYER_FN],
                         {98: 0x65})


if __name__ == "__main__":
    unittest.main()
