"""Touch & Roll Stage Editor — desktop GUI (PySide6). All editing logic is in tredit.project."""
from __future__ import annotations

import os
import subprocess
import sys
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

from trcore.stagemodel import floor_below

from . import EDITOR_NAME, __version__
from .mapview import COLORS, PROJECTIONS, MapView
from .project import EditorError, Project, find_original_rom, verify_saved_rom
from trcore.romwrite import patch_record_path

Qt = QtCore.Qt
KIND_NAMES = {"start": "Start", "goal": "Goal", "bumper": "Bumper", "banana": "Banana"}

EDITABLE_HELP = """<b>What this version can change</b> (meanings confirmed in-game, evidence Level 4):
<ul>
<li>Start: position and facing</li>
<li>Goals: position, facing (turn about the vertical axis) and red / normal</li>
<li>Bumpers: position</li>
<li>Bananas: position and single / bunch</li>
</ul>
<b>Shown but locked</b>: bumper rotation (not testable, bumpers are round), stage groups and their
motion, collision, everything not listed above. Adding or removing objects comes in a later version.
<p>Objects in a group other than the stage's first group belong to a part that may move
(drawn with a dashed outline); their positions are shown at the stage's rest pose and they move with
their part in-game.</p>
<p>The map is the stage's own model from the ROM, drawn at rest (moving parts in their starting
position). Nothing is written to the ROM you opened: saving always writes a separate copy plus a
.patch.json record, and every edit is checked against the original bytes before it is written.</p>"""

LEGEND_HTML = """<b>Map legend</b><br>
<span style='color:#3cdc5a'>&#9679;</span> start (arrow = facing)<br>
<span style='color:#46a0ff'>&#9644;</span> goal (arrow = front) &nbsp; <span style='color:#f03c3c'>&#9644;</span> red goal<br>
<span style='color:#e646e6'>&#9679;</span> bumper &nbsp; <span style='color:#ffdc28'>&#9679;</span> banana,
three dots = bunch (5)<br>
white ring = changed &nbsp; dashed outline = in a moving part<br>
Top view: forward (the start's direction at angle 0) is up, x to the right.<br>
Drag to move &middot; arrows / PgUp / PgDn nudge &middot; Q / E turn (Shift = 1&deg;) &middot;
wheel zoom &middot; right-drag pan &middot; F fit"""


class PropertiesPanel(QtWidgets.QWidget):
    changed = QtCore.Signal(str, str, object)      # obj_id, property, value

    def __init__(self, parent=None):
        super().__init__(parent)
        self.obj = None
        lay = QtWidgets.QVBoxLayout(self)
        self.title = QtWidgets.QLabel("Nothing selected")
        f = self.title.font()
        f.setBold(True)
        f.setPointSize(f.pointSize() + 1)
        self.title.setFont(f)
        lay.addWidget(self.title)
        self.sub = QtWidgets.QLabel("")
        self.sub.setWordWrap(True)
        lay.addWidget(self.sub)
        form = QtWidgets.QFormLayout()
        self.pos = []
        for axis in "XYZ":
            sb = QtWidgets.QDoubleSpinBox()
            sb.setRange(-500000, 500000)
            sb.setDecimals(4)
            sb.setSingleStep(0.25)
            sb.setKeyboardTracking(False)
            sb.editingFinished.connect(self._pos_edited)
            self.pos.append(sb)
            form.addRow(f"{axis}", sb)
        self.heading = QtWidgets.QDoubleSpinBox()
        self.heading.setRange(-720, 720)
        self.heading.setDecimals(2)
        self.heading.setSingleStep(15)
        self.heading.setWrapping(False)
        self.heading.setSuffix("°")
        self.heading.setKeyboardTracking(False)
        self.heading.editingFinished.connect(self._heading_edited)
        form.addRow("Facing", self.heading)
        self.red = QtWidgets.QCheckBox("Red goal")
        self.red.clicked.connect(lambda v: self._emit("red", bool(v)))
        form.addRow("", self.red)
        self.bunch = QtWidgets.QCheckBox("Bunch (worth 5)")
        self.bunch.clicked.connect(lambda v: self._emit("bunch", bool(v)))
        form.addRow("", self.bunch)
        lay.addLayout(form)
        self.note = QtWidgets.QLabel("")
        self.note.setWordWrap(True)
        self.note.setStyleSheet("color: #8a8f9c;")
        lay.addWidget(self.note)
        lay.addStretch(1)
        self.show_object(None)

    def _emit(self, prop, value):
        if self.obj:
            self.changed.emit(self.obj["id"], prop, value)

    def _pos_edited(self):
        if not self.obj:
            return
        new = [sb.value() for sb in self.pos]
        if any(abs(a - b) > 1e-9 for a, b in zip(new, self.obj["position"])):
            self._emit("position", new)

    def _heading_edited(self):
        if self.obj and self.obj.get("heading") is not None:
            v = self.heading.value() % 360.0
            if abs(v - self.obj["heading"]) > 1e-6:
                self._emit("heading", v)

    def show_object(self, obj: Optional[dict]):
        self.obj = obj
        widgets = self.pos + [self.heading, self.red, self.bunch]
        for w in widgets:
            w.blockSignals(True)
        try:
            if obj is None:
                self.title.setText("Nothing selected")
                self.sub.setText("Click an object on the map.")
                self.note.setText("")
                for w in widgets:
                    w.setEnabled(False)
                for sb in self.pos:
                    sb.setValue(0)
                self.heading.setValue(0)
                self.red.setChecked(False)
                self.bunch.setChecked(False)
                self.red.setVisible(False)
                self.bunch.setVisible(False)
                return
            k = obj["kind"]
            self.title.setText(f"{KIND_NAMES[k]} {obj['index'] + 1}")
            grp = obj.get("group_name") or f"group {obj['group']}"
            moving = " — may move with this part" if obj["in_moving_group"] else ""
            self.sub.setText(f"Group: {grp}{moving}\nRecord at {obj['offset']} in the stage file")
            for sb, v in zip(self.pos, obj["position"]):
                sb.setValue(v)
                sb.setEnabled("position" in obj["editable"])
            h = obj.get("heading")
            self.heading.setEnabled("heading" in obj["editable"])
            self.heading.setValue(h if h is not None else 0)
            self.red.setVisible(k == "goal")
            self.red.setChecked(bool(obj.get("red")))
            self.red.setEnabled("red" in obj["editable"])
            self.bunch.setVisible(k == "banana")
            self.bunch.setChecked(bool(obj.get("bunch")))
            self.bunch.setEnabled("bunch" in obj["editable"])
            notes = []
            if k == "bumper":
                notes.append("Rotation is locked (not confirmed in-game).")
                self.heading.setToolTip("locked")
            if k == "goal" and "heading" not in obj["editable"]:
                notes.append("This goal is tilted so far that its facing cannot be edited.")
            if k == "start":
                notes.append("Facing: 0° = towards -z (up on the top view); larger turns left.")
            if k == "goal":
                notes.append("Facing is the direction of the goal's front (the side you roll through).")
            notes.append("Values are shown as stored (1/4096 steps).")
            self.note.setText("\n".join(notes))
        finally:
            for w in widgets:
                w.blockSignals(False)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, rom_path: Optional[str] = None):
        super().__init__()
        self.settings = QtCore.QSettings("TouchRollResearch", "tredit")
        self.project: Optional[Project] = None
        self.stage_key: Optional[str] = None
        self.selected: Optional[str] = None
        self.objects = {}
        self.resize(1400, 900)

        self.top = MapView("top", self.describe)
        self.side = MapView("right", self.describe)
        for v in (self.top, self.side):
            v.on_select = self.select
            v.on_move = self.move_object
            v.floor_height = self.floor_height
        self.top.on_hover = self.hover_top
        self.side_combo = QtWidgets.QComboBox()
        self.side_combo.addItem("Automatic (along the longer side)", "auto")
        for key in ("right", "behind"):
            self.side_combo.addItem(PROJECTIONS[key][3], key)
        self.side_combo.currentIndexChanged.connect(self.change_side_projection)
        side_box = QtWidgets.QWidget()
        sl = QtWidgets.QVBoxLayout(side_box)
        sl.setContentsMargins(0, 0, 0, 0)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Side view:"))
        row.addWidget(self.side_combo)
        row.addStretch(1)
        sl.addLayout(row)
        sl.addWidget(self.side)
        split = QtWidgets.QSplitter(Qt.Vertical)
        split.addWidget(self.top)
        split.addWidget(side_box)
        split.setSizes([640, 240])
        self.setCentralWidget(split)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemActivated.connect(self.tree_activated)
        self.tree.itemClicked.connect(self.tree_activated)
        dock = QtWidgets.QDockWidget("Stages", self)
        dock.setObjectName("stages")
        dock.setWidget(self.tree)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)

        self.props = PropertiesPanel()
        self.props.changed.connect(self.property_changed)
        self.info = QtWidgets.QPlainTextEdit()
        self.info.setReadOnly(True)
        self.info.setStyleSheet("font-family: Consolas, 'DejaVu Sans Mono', monospace; font-size: 9pt;")
        legend = QtWidgets.QLabel(LEGEND_HTML)
        legend.setWordWrap(True)
        legend.setTextFormat(Qt.RichText)
        right = QtWidgets.QTabWidget()
        right.addTab(self.props, "Selected")
        right.addTab(self.info, "Stage info (read-only)")
        rbox = QtWidgets.QWidget()
        rl = QtWidgets.QVBoxLayout(rbox)
        rl.addWidget(right, 1)
        rl.addWidget(legend)
        dock2 = QtWidgets.QDockWidget("Properties", self)
        dock2.setObjectName("properties")
        dock2.setWidget(rbox)
        self.addDockWidget(Qt.RightDockWidgetArea, dock2)

        self.status_edits = QtWidgets.QLabel("")
        self.statusBar().addPermanentWidget(self.status_edits)
        self._build_actions()
        self.update_title()
        if rom_path:
            QtCore.QTimer.singleShot(0, lambda: self.open_rom(rom_path))
        else:
            self.statusBar().showMessage("File > Open ROM… to start (your original ROM is never modified).")

    # ------------------------------------------------------------------ actions
    def _act(self, menu, text, slot, shortcut=None, checkable=False, checked=False):
        a = QtGui.QAction(text, self)
        if shortcut:
            a.setShortcut(QtGui.QKeySequence(shortcut))
        a.setCheckable(checkable)
        if checkable:
            a.setChecked(checked)
            a.toggled.connect(slot)
        else:
            a.triggered.connect(slot)
        menu.addAction(a)
        return a

    def _build_actions(self):
        mb = self.menuBar()
        f = mb.addMenu("&File")
        self._act(f, "&Open ROM…", self.choose_rom, QtGui.QKeySequence.Open)
        f.addSeparator()
        self.a_save = self._act(f, "&Save", self.save, QtGui.QKeySequence.Save)
        self.a_save_as = self._act(f, "Save as &new copy…", self.save_as, "Ctrl+Shift+S")
        f.addSeparator()
        self.a_import = self._act(f, "&Import edits (plan or .patch.json)…", self.import_edits)
        self.a_export = self._act(f, "&Export edits as plan (.json)…", self.export_edits)
        f.addSeparator()
        self.a_play = self._act(f, "&Play saved copy in BizHawk", self.play, "F5")
        self._act(f, "Set BizHawk (EmuHawk.exe) location…", self.choose_bizhawk)
        f.addSeparator()
        self._act(f, "&Quit", self.close, QtGui.QKeySequence.Quit)
        e = mb.addMenu("&Edit")
        self.a_undo = self._act(e, "&Undo", self.undo, QtGui.QKeySequence.Undo)
        self.a_redo = self._act(e, "&Redo", self.redo, QtGui.QKeySequence.Redo)
        e.addSeparator()
        self._act(e, "Turn left 15°", lambda: self.turn(15), "Q")
        self._act(e, "Turn right 15°", lambda: self.turn(-15), "E")
        self._act(e, "Turn left 1°", lambda: self.turn(1), "Shift+Q")
        self._act(e, "Turn right 1°", lambda: self.turn(-1), "Shift+E")
        self._act(e, "Reset selected object to original", self.reset_selected)
        v = mb.addMenu("&View")
        self._act(v, "Zoom to &fit", lambda: (self.top.fit(), self.side.fit()), "F")
        self._act(v, "Show &grid", self.toggle_grid, checkable=True, checked=True)
        self._act(v, "Keep height above the floor while dragging", self.toggle_follow, checkable=True, checked=True)
        snap = v.addMenu("&Snap when dragging")
        grp = QtGui.QActionGroup(self)
        for label, val in (("Off (1/4096)", 0.0), ("0.125", 0.125), ("0.25", 0.25), ("0.5", 0.5), ("1", 1.0)):
            a = QtGui.QAction(label, self, checkable=True)
            a.setChecked(val == 0.25)
            a.triggered.connect(lambda _c=False, x=val: self.set_snap(x))
            grp.addAction(a)
            snap.addAction(a)
        self.set_snap(0.25)
        h = mb.addMenu("&Help")
        self._act(h, "What can be edited", lambda: QtWidgets.QMessageBox.information(self, EDITOR_NAME, EDITABLE_HELP))
        self._act(h, "About", self.about)
        for key, dx, dz, dy in ((Qt.Key_Up, 0, -1, 0), (Qt.Key_Down, 0, 1, 0), (Qt.Key_Left, -1, 0, 0),
                                (Qt.Key_Right, 1, 0, 0), (Qt.Key_PageUp, 0, 0, 1), (Qt.Key_PageDown, 0, 0, -1)):
            sc = QtGui.QShortcut(QtGui.QKeySequence(key), self)
            sc.activated.connect(lambda dx=dx, dz=dz, dy=dy: self.nudge(dx, dy, dz))
        self.update_actions()

    def update_actions(self):
        p = self.project
        has = bool(p and p.changed_stages())
        self.a_save.setEnabled(has)
        self.a_save_as.setEnabled(has)
        self.a_export.setEnabled(has)
        self.a_import.setEnabled(p is not None)
        self.a_undo.setEnabled(bool(p and p.undo_stack))
        self.a_redo.setEnabled(bool(p and p.redo_stack))
        self.a_undo.setText(f"&Undo {p.undo_stack[-1]['label']}" if p and p.undo_stack else "&Undo")
        self.a_redo.setText(f"&Redo {p.redo_stack[-1]['label']}" if p and p.redo_stack else "&Redo")
        self.a_play.setEnabled(bool(p and p.output_path))
        n = p.edit_count if p else 0
        self.status_edits.setText(f"{n} changed field(s) in {len(p.changed_stages())} stage(s)" if p else "")

    def update_title(self):
        t = EDITOR_NAME
        if self.project:
            t += f" — {os.path.basename(self.project.rom_path)}"
            if self.project.output_path:
                t += f" → {os.path.basename(self.project.output_path)}"
            if self.project.dirty and self.project.changed_stages():
                t += " *"
        self.setWindowTitle(t)

    # ------------------------------------------------------------------ helpers
    def error(self, msg):
        QtWidgets.QMessageBox.warning(self, EDITOR_NAME, str(msg))

    def notice(self, msg):
        QtWidgets.QMessageBox.information(self, EDITOR_NAME, str(msg))

    def describe(self, o: dict) -> str:
        p = ", ".join(f"{v:.4g}" for v in o["position"])
        s = f"{KIND_NAMES[o['kind']]} {o['index'] + 1}  ({p})"
        if o.get("heading") is not None:
            s += f"  facing {o['heading']:.1f}°"
        if o["kind"] == "goal":
            s += "  RED" if o.get("red") else ""
        if o["kind"] == "banana" and o.get("bunch"):
            s += "  bunch"
        if o["in_moving_group"]:
            s += f"\nin part '{o.get('group_name')}' (may move)"
        return s

    def floor_height(self, x, z, y_limit):
        st = self.project and self.stage_key and self.project.stage(self.stage_key)
        m = st and st.model
        if not m:
            return None
        return floor_below(m["triangles"], (x, y_limit, z), tol=0.0)

    def hover_top(self, sp):
        if not self.project or not self.stage_key:
            return
        x, z = sp
        f = self.floor_height(x, z, 1e9)
        surf = f"  surface y {f:.3f}" if f is not None else ""
        self.statusBar().showMessage(f"x {x:.3f}  z {z:.3f}{surf}")

    # ------------------------------------------------------------------ ROM / stages
    def choose_rom(self):
        if not self.confirm_discard():
            return
        start = self.settings.value("last_rom_dir", "")
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open Touch & Roll ROM (it is never modified)",
                                                        start, "Nintendo DS ROM (*.nds)")
        if path:
            self.open_rom(path)

    def open_rom(self, path):
        try:
            QtWidgets.QApplication.setOverrideCursor(Qt.WaitCursor)
            proj = Project(path)
        except EditorError as exc:
            QtWidgets.QApplication.restoreOverrideCursor()
            self.error(exc)
            return
        QtWidgets.QApplication.restoreOverrideCursor()
        self.settings.setValue("last_rom_dir", os.path.dirname(os.path.abspath(path)))
        rec = proj.opened_editor_output
        if rec:
            orig = find_original_rom(path, rec)
            if orig and self.ask(
                    f"{os.path.basename(path)} is a copy this editor saved from {os.path.basename(orig)}.\n\n"
                    f"Open {os.path.basename(orig)} and load this copy's edits instead? (Recommended: every save "
                    "then stays one step from the original, and Save keeps replacing this copy.)"):
                try:
                    base = Project(orig)
                    if rec.get("plan"):
                        base.import_plan(patch_record_path(path))
                    base.output_path = os.path.abspath(path)
                    base.saved_action = base.undo_stack[-1]["id"] if base.undo_stack else None
                except EditorError as exc:
                    self.error(f"Could not load the edits onto the original ({exc}); opening the copy as it is.")
                else:
                    self.open_project(base, orig)
                    return
        self.open_project(proj, path)

    def ask(self, question) -> bool:
        return QtWidgets.QMessageBox.question(self, EDITOR_NAME, question) == QtWidgets.QMessageBox.Yes

    def open_project(self, proj: Project, path: str):
        self.project = proj
        self.stage_key = None
        self.fill_tree()
        self.update_actions()
        self.update_title()
        if proj.opened_editor_output:
            src = (proj.opened_editor_output.get("input_rom") or {}).get("name", "the original ROM")
            self.notice(
                f"This ROM is a copy the editor saved earlier (made from {src}). New edits will be added on "
                "top of it, and saves will record that chain.\n\nTo keep every save one step from the original "
                f"instead, open {src} and use File > Import edits with "
                f"{os.path.splitext(os.path.basename(path))[0]}.patch.json, then Save over the copy.")
        first = proj.worlds[0]["stages"][0]["stage_key"] if proj.worlds else None
        if first:
            self.load_stage(first)

    def fill_tree(self):
        self.tree.clear()
        p = self.project
        changed = set(p.changed_stages())
        self.tree_items = {}
        for w in p.worlds:
            wi = QtWidgets.QTreeWidgetItem([f"World {w['world']} — {w['title']}"])
            self.tree.addTopLevelItem(wi)
            for s in w["stages"]:
                it = QtWidgets.QTreeWidgetItem([self._stage_label(p.entries[s["stage_key"]], s["stage_key"] in changed)])
                it.setData(0, Qt.UserRole, s["stage_key"])
                it.setToolTip(0, f"{s['stage_key']} (stage id {s['stage_id']})")
                wi.addChild(it)
                self.tree_items[s["stage_key"]] = it
        oi = QtWidgets.QTreeWidgetItem(["Other stage files (party / unused)"])
        self.tree.addTopLevelItem(oi)
        for k in p.other_keys:
            e = p.entries[k]
            it = QtWidgets.QTreeWidgetItem([self._stage_label(e, k in changed)])
            it.setData(0, Qt.UserRole, k)
            it.setToolTip(0, k if e.get("loadable") else f"{k}: not in the game's stage name table (never loaded)")
            oi.addChild(it)
            self.tree_items[k] = it
        self.tree.expandItem(self.tree.topLevelItem(0))

    def _stage_label(self, e, changed):
        lab = e["label"] if e.get("world") else e["stage_key"] + ("" if e.get("loadable", True) else "  (unused)")
        return ("● " if changed else "") + lab

    def refresh_tree_marks(self):
        changed = set(self.project.changed_stages())
        for k, it in self.tree_items.items():
            it.setText(0, self._stage_label(self.project.entries[k], k in changed))

    def tree_activated(self, item, _col=0):
        k = item.data(0, Qt.UserRole)
        if k and k != self.stage_key:
            self.load_stage(k)

    def load_stage(self, key):
        try:
            QtWidgets.QApplication.setOverrideCursor(Qt.WaitCursor)
            st = self.project.stage(key)
            tris = st.model["triangles"] if st.model else []
        except EditorError as exc:
            QtWidgets.QApplication.restoreOverrideCursor()
            self.error(exc)
            return
        finally:
            if QtWidgets.QApplication.overrideCursor():
                QtWidgets.QApplication.restoreOverrideCursor()
        self.stage_key = key
        self.selected = None
        objs = st.objects()
        self.objects = {o["id"]: o for o in objs}
        bounds = self._bounds(st)
        self.side.proj = self._side_proj_for(st)
        self.top.set_stage(tris, objs, bounds)
        self.side.set_stage(tris, objs, bounds)
        self.props.show_object(None)
        self.info.setPlainText(self.stage_info(st))
        it = self.tree_items.get(key)
        if it:
            self.tree.setCurrentItem(it)
        msg = f"{st.entry['label']} ({key})"
        if not st.model:
            msg += " — no model file for this stage; objects only" if not st.model_error else \
                f" — model could not be read: {st.model_error}"
        self.statusBar().showMessage(msg, 8000)

    @staticmethod
    def _bounds(st):
        """Header 0x1C..0x33 (bounds-like values, Level 2) for a dashed reference rectangle."""
        h = st.doc.header
        try:
            lo = [h[f"bounds_min_{a}"]["value"] for a in "xyz"]
            hi = [h[f"bounds_max_{a}"]["value"] for a in "xyz"]
        except KeyError:
            return None
        return lo, hi

    def stage_info(self, st) -> str:
        e = st.entry
        lines = [f"Stage:  {e['label']}", f"Key:    {st.key}", f"File:   stcoli/{st.key}_stc.lz",
                 f"Model:  {st.model['path'] if st.model else '(none)'}"]
        if st.model:
            lines.append(f"        {len(st.model['triangles'])} triangles, {len(st.model['model'].nodes)} nodes, "
                         f"posScale {st.model['model'].pos_scale:g}")
            for n in st.model["notes"]:
                lines.append(f"        note: {n}")
        d = st.doc
        lines.append(f"Layout: {d.layout_variant}")
        lines.append("Objects: " + ", ".join(f"{len([o for o in self.objects.values() if o['kind'] == k])} {k}"
                                             for k in ("start", "goal", "bumper", "banana")))
        lines.append("")
        lines.append("Groups (parts) — read-only:")
        kinds = st.group_kinds
        for g in d.groups:
            n = {k: g["slices"][k]["count"] for k in "ABC"}
            t = ", ".join(f"{v:g}" for v in g["translation"])
            lines.append(f"  {g['index']:2d} {g.get('name_text_04') or '?':24s} goals {n['A']} bumpers {n['B']} "
                         f"bananas {n['C']}  [{kinds.get(g['index'])}]  T=({t})")
        lines.append("")
        lines.append("Edits in this stage:")
        pe = st.plan_edits()
        if not pe:
            lines.append("  (none)")
        for x in pe:
            lines.append(f"  {x['target']}: {x['from']} -> {x['to']}")
        return "\n".join(lines)

    # ------------------------------------------------------------------ selection & edits
    def select(self, oid):
        self.selected = oid if oid in self.objects else None
        self.top.set_selected(self.selected)
        self.side.set_selected(self.selected)
        self.props.show_object(self.objects.get(self.selected))

    def sync(self):
        st = self.project.stage(self.stage_key)
        objs = st.objects()
        self.objects = {o["id"]: o for o in objs}
        self.top.update_objects(objs)
        self.side.update_objects(objs)
        self.props.show_object(self.objects.get(self.selected))
        self.info.setPlainText(self.stage_info(st))
        self.refresh_tree_marks()
        self.update_actions()
        self.update_title()

    def do_change(self, oid, prop, value, label=None):
        if not self.project or not self.stage_key:
            return
        try:
            self.project.change(self.stage_key, oid, prop, value, label)
        except EditorError as exc:
            self.error(exc)
        self.sync()

    def move_object(self, oid, pos):
        self.do_change(oid, "position", pos, f"move {oid}")

    def property_changed(self, oid, prop, value):
        self.do_change(oid, prop, value, f"{prop} of {oid}")

    def nudge(self, dx, dy, dz):
        o = self.objects.get(self.selected)
        if not o or "position" not in o["editable"]:
            return
        step = self.top.snap or 0.25
        p = list(o["position"])
        p[0] += dx * step
        p[1] += dy * step
        p[2] += dz * step
        self.do_change(o["id"], "position", p, f"nudge {o['id']}")

    def turn(self, deg):
        o = self.objects.get(self.selected)
        if not o or "heading" not in o["editable"]:
            return
        self.do_change(o["id"], "heading", (o["heading"] + deg) % 360.0, f"turn {o['id']}")

    def reset_selected(self):
        o = self.objects.get(self.selected)
        if not o:
            return
        st = self.project.stage(self.stage_key)
        prefix = {"start": "start", "goal": "pool_A", "bumper": "pool_B", "banana": "pool_C"}[o["kind"]]
        changes = {t: st.original_raw(t) for t in st.edits if t.startswith(f"{prefix}[{o['index']}].")}
        if changes:
            try:
                self.project.apply(self.stage_key, changes, f"reset {o['id']}")
            except EditorError as exc:
                self.error(exc)
            self.sync()

    def undo(self):
        a = self.project and self.project.undo()
        self._after_history(a)

    def redo(self):
        a = self.project and self.project.redo()
        self._after_history(a)

    def _after_history(self, a):
        if not a:
            return
        if a["key"] != self.stage_key:
            self.load_stage(a["key"])
        self.sync()

    # ------------------------------------------------------------------ view options
    def _side_proj_for(self, st) -> str:
        choice = self.side_combo.currentData()
        if choice != "auto":
            return choice
        pts = [o["position"] for o in self.objects.values()]
        if st.model and st.model["bounds"]:
            b = st.model["bounds"]
            pts += [b["min"], b["max"]]
        if not pts:
            return "right"
        ex = max(p[0] for p in pts) - min(p[0] for p in pts)
        ez = max(p[2] for p in pts) - min(p[2] for p in pts)
        return "behind" if ex > ez else "right"

    def change_side_projection(self, _i):
        if self.stage_key:
            self.side.proj = self._side_proj_for(self.project.stage(self.stage_key))
            st = self.project.stage(self.stage_key)
            self.side.set_stage(st.model["triangles"] if st.model else [], list(self.objects.values()),
                                self._bounds(st))
            self.side.set_selected(self.selected)

    def toggle_grid(self, on):
        for v in (self.top, self.side):
            v.show_grid = on
            v.viewport().update()
            v.scene().update()

    def toggle_follow(self, on):
        self.top.follow_floor = on

    def set_snap(self, val):
        self.top.snap = self.side.snap = val

    # ------------------------------------------------------------------ saving
    def save(self):
        if not self.project:
            return
        if not self.project.output_path:
            return self.save_as()
        self._write(self.project.output_path, replace_own=True)

    def save_as(self):
        if not self.project:
            return
        start = self.project.output_path or os.path.join(os.path.dirname(self.project.rom_path), "My Touch & Roll hack.nds")
        dlg = QtWidgets.QFileDialog(self, "Save edited ROM as a new copy", start, "Nintendo DS ROM (*.nds)")
        dlg.setAcceptMode(QtWidgets.QFileDialog.AcceptSave)
        dlg.setDefaultSuffix("nds")
        dlg.setOption(QtWidgets.QFileDialog.DontConfirmOverwrite, True)
        if not dlg.exec():
            return
        path = dlg.selectedFiles()[0]
        if os.path.exists(path):
            r = QtWidgets.QMessageBox.question(
                self, EDITOR_NAME,
                f"{os.path.basename(path)} already exists.\n\nReplace it? This is only allowed for a copy this "
                "editor saved from the same original ROM and that has not been changed since.")
            if r != QtWidgets.QMessageBox.Yes:
                return
        self._write(path, replace_own=True)

    def _write(self, path, replace_own):
        try:
            QtWidgets.QApplication.setOverrideCursor(Qt.WaitCursor)
            rec = self.project.save(path, replace_own=replace_own)
            problems = verify_saved_rom(path, self.project)
        except EditorError as exc:
            QtWidgets.QApplication.restoreOverrideCursor()
            self.error(exc)
            return
        QtWidgets.QApplication.restoreOverrideCursor()
        if problems:
            self.error("The copy was written but re-reading it found problems:\n" + "\n".join(problems))
        verb = "Replaced" if rec.get("replaced_previous_output") else "Saved"
        self.statusBar().showMessage(f"{verb} {os.path.basename(path)} and {os.path.basename(rec['record_path'])} "
                                     f"(checked: only the edited stage files changed)", 10000)
        self.update_actions()
        self.update_title()

    def import_edits(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Import edits", self.settings.value("last_rom_dir", ""),
                                                        "Edit plan or patch record (*.json)")
        if not path:
            return
        try:
            n = self.project.import_plan(path)
        except EditorError as exc:
            self.error(exc)
            return
        self.refresh_tree_marks()
        if self.stage_key:
            self.sync()
        self.update_actions()
        self.statusBar().showMessage(f"Imported {n} edit(s) from {os.path.basename(path)}", 8000)

    def export_edits(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export edits as a plan (contains no game data)",
                                                        os.path.join(self.settings.value("last_rom_dir", ""),
                                                                     "my_edits.plan.json"), "Edit plan (*.json)")
        if not path:
            return
        try:
            self.project.export_plan(path)
        except (EditorError, OSError) as exc:
            self.error(exc)
            return
        self.statusBar().showMessage(f"Exported edits to {os.path.basename(path)}", 8000)

    # ------------------------------------------------------------------ BizHawk
    def choose_bizhawk(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Where is EmuHawk.exe?",
                                                        self.settings.value("bizhawk", ""), "EmuHawk (EmuHawk*)")
        if path:
            self.settings.setValue("bizhawk", path)

    def play(self):
        p = self.project
        if not p or not p.output_path:
            return
        if p.dirty:
            r = QtWidgets.QMessageBox.question(self, EDITOR_NAME, "Save the latest edits before playing?")
            if r == QtWidgets.QMessageBox.Yes:
                self.save()
        exe = self.settings.value("bizhawk", "")
        if not exe or not os.path.exists(exe):
            self.choose_bizhawk()
            exe = self.settings.value("bizhawk", "")
            if not exe:
                return
        try:
            subprocess.Popen([exe, p.output_path], cwd=os.path.dirname(exe))
        except OSError as exc:
            self.error(f"Could not start BizHawk: {exc}")

    # ------------------------------------------------------------------ closing
    def confirm_discard(self) -> bool:
        p = self.project
        if not p or not p.changed_stages() or not p.dirty:
            return True
        r = QtWidgets.QMessageBox.question(
            self, EDITOR_NAME, "There are unsaved edits. Save them first?",
            QtWidgets.QMessageBox.Save | QtWidgets.QMessageBox.Discard | QtWidgets.QMessageBox.Cancel)
        if r == QtWidgets.QMessageBox.Save:
            self.save()
            return not p.dirty
        return r == QtWidgets.QMessageBox.Discard

    def closeEvent(self, ev):
        if self.confirm_discard():
            ev.accept()
        else:
            ev.ignore()

    def about(self):
        QtWidgets.QMessageBox.about(
            self, EDITOR_NAME,
            f"<b>{EDITOR_NAME}</b> {__version__}<br>Super Monkey Ball: Touch &amp; Roll (USA) stage editor.<br>"
            "Built on trcore. Your original ROM is never modified; every save is a verified copy with a "
            ".patch.json record.")


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    QtWidgets.QApplication.setApplicationName(EDITOR_NAME)
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(argv)
    app.setStyle("Fusion")
    pal = QtGui.QPalette()
    pal.setColor(QtGui.QPalette.Window, QtGui.QColor(40, 42, 50))
    pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor(225, 228, 235))
    pal.setColor(QtGui.QPalette.Base, QtGui.QColor(28, 30, 38))
    pal.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(40, 42, 50))
    pal.setColor(QtGui.QPalette.Text, QtGui.QColor(225, 228, 235))
    pal.setColor(QtGui.QPalette.Button, QtGui.QColor(50, 53, 62))
    pal.setColor(QtGui.QPalette.ButtonText, QtGui.QColor(225, 228, 235))
    pal.setColor(QtGui.QPalette.Highlight, QtGui.QColor(230, 140, 30))
    pal.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor(20, 20, 20))
    pal.setColor(QtGui.QPalette.ToolTipBase, QtGui.QColor(50, 53, 62))
    pal.setColor(QtGui.QPalette.ToolTipText, QtGui.QColor(225, 228, 235))
    pal.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.Text, QtGui.QColor(120, 124, 135))
    pal.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.WindowText, QtGui.QColor(120, 124, 135))
    app.setPalette(pal)
    rom = argv[1] if len(argv) > 1 else None
    w = MainWindow(rom)
    w.show()
    return app.exec()
