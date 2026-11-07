"""Offscreen smoke test of the desktop GUI (skipped when PySide6 is not installed)."""
import os
import shutil
import tempfile
import unittest

try:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6 import QtCore, QtWidgets
    HAVE_QT = True
except ImportError:          # pragma: no cover
    HAVE_QT = False

from tests.test_editor_project import make_synth, open_synth


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class GuiSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tredit import app as A
        cls.A = A
        cls.qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication(["test"])

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tredit_gui_")
        self.base = make_synth(self.tmp)
        QtCore.QCoreApplication.setOrganizationName("TouchRollResearchTest")
        self.w = self.A.MainWindow(None)
        self.errors = []
        self.w.error = self.errors.append
        self.w.notice = lambda m: None
        self.w.confirm_discard = lambda: True    # no modal dialogs offscreen
        self.w.show()
        self.w.open_project(open_synth(self.base), self.base)
        self.qapp.processEvents()

    def tearDown(self):
        self.w.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_load_select_drag_turn_undo_save(self):
        w = self.w
        self.assertEqual(w.stage_key, "s1")
        self.assertEqual(set(w.top.markers), {"start:0", "goal:0", "banana:0", "banana:1"})
        self.assertIsNotNone(w.top.outline)
        w.select("banana:0")
        self.assertEqual(w.props.obj["id"], "banana:0")
        m = w.top.markers["banana:0"]
        m.dragging = True
        m.setPos(QtCore.QPointF(3.1, 2.2))       # snapped to 0.25 while dragging
        m.dragging = False
        w.top.drag_finished(m)
        self.assertEqual(w.objects["banana:0"]["position"][0], 3.0)
        self.assertEqual(w.objects["banana:0"]["position"][2], 2.25)
        w.nudge(0, 0, -1)                        # forward = -z
        self.assertEqual(w.objects["banana:0"]["position"][2], 2.0)
        w.select("goal:0")
        w.turn(-90)
        self.assertEqual(w.objects["goal:0"]["heading"], 90.0)
        w.props.red.click()
        self.assertTrue(w.objects["goal:0"]["red"])
        self.assertEqual(len(w.project.undo_stack), 4)
        self.assertTrue(w.a_save.isEnabled())
        w.undo()
        self.assertFalse(w.objects["goal:0"]["red"])
        w.redo()
        self.assertTrue(w.objects["goal:0"]["red"])
        self.assertIn("●", w.tree_items["s1"].text(0))
        out = os.path.join(self.tmp, "gui_copy.nds")
        w._write(out, replace_own=True)
        self.assertEqual(self.errors, [])
        self.assertTrue(os.path.exists(out))
        self.assertTrue(os.path.exists(os.path.splitext(out)[0] + ".patch.json"))
        self.assertEqual(w.project.output_path, out)
        self.assertNotIn("*", w.windowTitle())
        w.select("banana:1")
        w.props.bunch.click()
        w.save()                                 # replaces its own copy
        self.assertEqual(self.errors, [])

    def test_side_view_changes_height_only(self):
        w = self.w
        w.side_combo.setCurrentIndex(2)          # from behind
        m = w.side.markers["start:0"]
        before = list(w.objects["start:0"]["position"])
        m.dragging = True
        m.setPos(QtCore.QPointF(m.pos().x() + 5, -2.0))
        m.dragging = False
        w.side.drag_finished(m)
        after = w.objects["start:0"]["position"]
        self.assertEqual(after[0], before[0])
        self.assertEqual(after[2], before[2])
        self.assertEqual(after[1], 2.0)

    def test_opening_a_copy_offers_the_original(self):
        w = self.w
        w.select("goal:0")
        w.props.red.click()
        out = os.path.join(self.tmp, "copy.nds")
        w._write(out, replace_own=True)
        asked = []
        w.ask = lambda q: asked.append(q) or True
        orig_project = self.A.Project
        self.A.Project = lambda path: open_synth(path)
        try:
            w.open_rom(out)
        finally:
            self.A.Project = orig_project
        self.assertEqual(len(asked), 1)
        self.assertEqual(os.path.abspath(w.project.rom_path), os.path.abspath(self.base))
        self.assertEqual(w.project.output_path, os.path.abspath(out))
        self.assertTrue(w.objects["goal:0"]["red"])
        self.assertFalse(w.project.dirty)
        w.select("banana:0")
        w.props.bunch.click()
        w.save()                                 # replaces the copy, built from the original
        self.assertEqual(self.errors, [])

    def test_errors_are_reported_not_raised(self):
        w = self.w
        w.do_change("goal:0", "position", [1e9, 0, 0])
        self.assertEqual(len(self.errors), 1)
        self.assertFalse(w.project.changed_stages())

    def test_other_stage_without_model(self):
        w = self.w
        w.load_stage("s2")
        self.assertIsNone(w.top.outline)
        self.assertTrue(w.top.markers)
        img = w.grab()
        self.assertFalse(img.isNull())


if __name__ == "__main__":
    unittest.main()
