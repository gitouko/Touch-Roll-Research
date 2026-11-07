"""2D map views: top-down (x right, -z up = the start's forward direction) and two side views.

The stage outline is the stage's own model read from the ROM (trcore.stagemodel),
drawn at the stage's rest pose. Object markers are drawn on top; dragging a
marker reports the new position to the main window, which commits it through
the project (and then re-syncs every view from the re-parsed stage bytes).
"""
from __future__ import annotations

import math
from typing import Callable, Dict, List, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from trcore.nitro.nsbmd import triangle_normal

Qt = QtCore.Qt

# projection name -> (scene x from world, scene y from world, which world axes a drag may change, label)
PROJECTIONS = {
    "top": (lambda p: p[0], lambda p: p[2], (0, 2), "Top (x right, forward up)"),
    "right": (lambda p: -p[2], lambda p: -p[1], (1,), "Side from the right (forward to the right)"),
    "behind": (lambda p: p[0], lambda p: -p[1], (1,), "Side from behind (x right)"),
}

COLORS = {
    "start": QtGui.QColor(60, 220, 90),
    "goal": QtGui.QColor(70, 160, 255),
    "goal_red": QtGui.QColor(240, 60, 60),
    "bumper": QtGui.QColor(230, 70, 230),
    "banana": QtGui.QColor(255, 220, 40),
}
MARKER_PX = {"start": 9, "goal": 9, "bumper": 8, "banana": 5}


def to_scene(proj: str, p) -> QtCore.QPointF:
    fx, fy, _axes, _l = PROJECTIONS[proj]
    return QtCore.QPointF(fx(p), fy(p))


class OutlineItem(QtWidgets.QGraphicsItem):
    """All model triangles, painted far-to-near with height / facing shading."""

    def __init__(self, triangles, proj: str):
        super().__init__()
        self.proj = proj
        self.setCacheMode(QtWidgets.QGraphicsItem.DeviceCoordinateCache)
        self.setZValue(-10)
        self.polys: List[tuple] = []
        if not triangles:
            self._rect = QtCore.QRectF()
            return
        ys = [v[1] for t in triangles for v in t[:3]]
        y0, y1 = min(ys), max(ys)
        span = (y1 - y0) or 1.0
        if proj == "top":
            depth = lambda t: max(v[1] for v in t[:3])
            view = (0.0, 1.0, 0.0)
        elif proj == "right":
            depth = lambda t: max(v[0] for v in t[:3])
            view = (1.0, 0.0, 0.0)
        else:
            depth = lambda t: max(v[2] for v in t[:3])
            view = (0.0, 0.0, 1.0)
        for t in sorted(triangles, key=depth):
            n = triangle_normal(t)
            facing = abs(n[0] * view[0] + n[1] * view[1] + n[2] * view[2])
            h = (sum(v[1] for v in t[:3]) / 3 - y0) / span
            if proj == "top":
                if abs(n[1]) >= 0.3:           # floor / slope: lighter when higher
                    c = QtGui.QColor.fromRgbF(0.22 + 0.45 * h, 0.30 + 0.42 * h, 0.42 + 0.40 * h)
                else:                          # wall seen from above
                    c = QtGui.QColor(95, 70, 72)
            else:                              # side views: lit by how directly a face looks at the viewer
                k = 0.55 + 0.45 * facing
                c = QtGui.QColor.fromRgbF(min(1.0, (0.40 + 0.25 * h) * k), min(1.0, (0.46 + 0.22 * h) * k),
                                          min(1.0, (0.62 + 0.18 * h) * k))
            poly = QtGui.QPolygonF([to_scene(proj, v) for v in t[:3]])
            self.polys.append((poly, c))
        r = QtCore.QRectF()
        for poly, _c in self.polys:
            r = r.united(poly.boundingRect())
        self._rect = r.adjusted(-1, -1, 1, 1)

    def boundingRect(self):
        return self._rect

    def paint(self, painter, option, widget=None):
        edge = QtGui.QPen(QtGui.QColor(20, 24, 34, 160) if self.proj == "top" else QtGui.QColor(150, 165, 200, 200), 0)
        edge.setCosmetic(True)
        painter.setPen(edge)
        for poly, c in self.polys:
            painter.setBrush(c)
            painter.drawPolygon(poly)


class Marker(QtWidgets.QGraphicsItem):
    """One stage object. Fixed pixel size; draggable along the view's editable axes."""

    def __init__(self, view: "MapView", obj: dict):
        super().__init__()
        self.view = view
        self.obj = obj
        self.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations, True)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable, True)
        movable = "position" in obj["editable"]
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, movable)
        self.setFlag(QtWidgets.QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setZValue({"banana": 1, "bumper": 2, "goal": 3, "start": 4}[obj["kind"]])
        self.dragging = False
        self.press_pos = None
        self.update_from(obj)

    def update_from(self, obj: dict):
        self.obj = obj
        self.setPos(to_scene(self.view.proj, obj["position"]))
        self.setToolTip(self.view.describe(obj))
        self.update()

    def boundingRect(self):
        r = MARKER_PX[self.obj["kind"]] + 14
        return QtCore.QRectF(-r, -r, 2 * r, 2 * r)

    def _heading_vector(self):
        """Screen direction of the object's facing in this view (top view only)."""
        h = self.obj.get("heading")
        if h is None or self.view.proj != "top":
            return None
        a = math.radians(h)
        # facing (-sin a, 0, -cos a) in world; top view: screen x = x, screen y = z
        return QtCore.QPointF(-math.sin(a), -math.cos(a))

    def paint(self, painter, option, widget=None):
        o = self.obj
        k = o["kind"]
        r = MARKER_PX[k]
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        col = COLORS["goal_red"] if (k == "goal" and o.get("red")) else COLORS[k]
        outline = QtGui.QPen(QtGui.QColor(15, 15, 20), 1.5)
        if o["in_moving_group"]:
            outline.setStyle(Qt.DashLine)
        painter.setPen(outline)
        painter.setBrush(col)
        hv = self._heading_vector()
        if k == "start":
            painter.drawEllipse(QtCore.QPointF(0, 0), r, r)
        elif k == "goal":
            if hv is not None:
                # bar across the facing direction
                px, py = -hv.y(), hv.x()
                bar = QtGui.QPolygonF([QtCore.QPointF(px * r * 1.4 + hv.x() * 3, py * r * 1.4 + hv.y() * 3),
                                       QtCore.QPointF(-px * r * 1.4 + hv.x() * 3, -py * r * 1.4 + hv.y() * 3),
                                       QtCore.QPointF(-px * r * 1.4 - hv.x() * 3, -py * r * 1.4 - hv.y() * 3),
                                       QtCore.QPointF(px * r * 1.4 - hv.x() * 3, py * r * 1.4 - hv.y() * 3)])
                painter.drawPolygon(bar)
            else:
                painter.drawRect(QtCore.QRectF(-r, -r * 0.6, 2 * r, 1.2 * r))
        elif k == "bumper":
            painter.drawEllipse(QtCore.QPointF(0, 0), r, r)
            painter.setBrush(QtGui.QColor(255, 255, 255, 160))
            painter.drawEllipse(QtCore.QPointF(0, 0), r * 0.4, r * 0.4)
        else:
            if o.get("bunch"):
                for dx, dy in ((-3, 2), (3, 2), (0, -3)):
                    painter.drawEllipse(QtCore.QPointF(dx, dy), r * 0.9, r * 0.9)
            else:
                painter.drawEllipse(QtCore.QPointF(0, 0), r, r)
        if hv is not None:
            pen = QtGui.QPen(QtGui.QColor(255, 255, 255), 2)
            painter.setPen(pen)
            tip = QtCore.QPointF(hv.x() * (r + 11), hv.y() * (r + 11))
            painter.drawLine(QtCore.QPointF(0, 0), tip)
            side = QtCore.QPointF(-hv.y() * 4, hv.x() * 4)
            back = QtCore.QPointF(hv.x() * (r + 5), hv.y() * (r + 5))
            painter.setBrush(QtGui.QColor(255, 255, 255))
            painter.drawPolygon(QtGui.QPolygonF([tip, back + side, back - side]))
        if o.get("changed"):
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255), 1.5))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QtCore.QPointF(0, 0), r + 4, r + 4)
        if self.isSelected():
            pen = QtGui.QPen(QtGui.QColor(255, 160, 0), 2.5)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QtCore.QPointF(0, 0), r + 7, r + 7)

    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.ItemPositionChange and self.dragging:
            return self.view.constrain(self, value)
        return super().itemChange(change, value)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.view.select_requested(self.obj["id"])
            self.press_pos = self.pos()
            self.dragging = bool(self.flags() & QtWidgets.QGraphicsItem.ItemIsMovable)
        super().mousePressEvent(ev)

    def mouseReleaseEvent(self, ev):
        super().mouseReleaseEvent(ev)
        if self.dragging:
            self.dragging = False
            if self.press_pos is not None and self.pos() != self.press_pos:
                self.view.drag_finished(self)


class MapView(QtWidgets.QGraphicsView):
    def __init__(self, proj: str, describe: Callable[[dict], str], parent=None):
        super().__init__(parent)
        self.proj = proj
        self.describe = describe
        self.setScene(QtWidgets.QGraphicsScene(self))
        self.setRenderHint(QtGui.QPainter.Antialiasing, False)
        self.setViewportUpdateMode(QtWidgets.QGraphicsView.SmartViewportUpdate)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setDragMode(QtWidgets.QGraphicsView.NoDrag)
        self.setBackgroundBrush(QtGui.QColor(18, 20, 28))
        self.markers: Dict[str, Marker] = {}
        self.outline: Optional[OutlineItem] = None
        self.bounds_item = None
        self.snap = 0.0
        self.on_select: Callable[[Optional[str]], None] = lambda oid: None
        self.on_move: Callable[[str, list], None] = lambda oid, pos: None
        self.on_hover: Callable[[Optional[list]], None] = lambda p: None
        self.floor_height: Callable[[float, float, float], Optional[float]] = lambda x, z, y: None
        self.follow_floor = True
        self._pan = None
        self.show_grid = True
        self.setMouseTracking(True)

    # ---- content
    def set_stage(self, triangles, objects: List[dict], bounds=None):
        sc = self.scene()
        sc.clear()
        self.markers.clear()
        self.outline = OutlineItem(triangles, self.proj) if triangles else None
        if self.outline:
            sc.addItem(self.outline)
        if bounds:
            lo, hi = bounds
            a, b = to_scene(self.proj, lo), to_scene(self.proj, hi)
            pen = QtGui.QPen(QtGui.QColor(120, 120, 140), 0, Qt.DashLine)
            pen.setCosmetic(True)
            self.bounds_item = sc.addRect(QtCore.QRectF(a, b).normalized(), pen)
            self.bounds_item.setZValue(-20)
        for o in objects:
            m = Marker(self, o)
            sc.addItem(m)
            self.markers[o["id"]] = m
        rect = sc.itemsBoundingRect()
        for m in self.markers.values():
            rect = rect.united(QtCore.QRectF(m.pos() - QtCore.QPointF(1, 1), QtCore.QSizeF(2, 2)))
        sc.setSceneRect(rect.adjusted(-rect.width() - 10, -rect.height() - 10, rect.width() + 10, rect.height() + 10))
        self._content_rect = rect.adjusted(-2, -2, 2, 2)
        self.fit()

    def update_objects(self, objects: List[dict]):
        for o in objects:
            m = self.markers.get(o["id"])
            if m is not None:
                m.update_from(o)

    def set_selected(self, oid: Optional[str]):
        for k, m in self.markers.items():
            m.setSelected(k == oid)
            m.update()

    def fit(self):
        if getattr(self, "_content_rect", None) and not self._content_rect.isEmpty():
            self.resetTransform()
            self.fitInView(self._content_rect, Qt.KeepAspectRatio)

    # ---- dragging
    def select_requested(self, oid):
        self.on_select(oid)

    def _snap(self, v: float) -> float:
        return round(v / self.snap) * self.snap if self.snap else v

    def constrain(self, marker: Marker, value: QtCore.QPointF) -> QtCore.QPointF:
        start = to_scene(self.proj, marker.obj["position"])
        if self.proj == "top":
            return QtCore.QPointF(self._snap(value.x()), self._snap(value.y()))
        return QtCore.QPointF(start.x(), self._snap(value.y()))      # side views: height only

    def drag_finished(self, marker: Marker):
        p = list(marker.obj["position"])
        s = marker.pos()
        if self.proj == "top":
            nx, nz = s.x(), s.y()
            if self.follow_floor:
                f0 = self.floor_height(p[0], p[2], p[1])
                f1 = self.floor_height(nx, nz, p[1] + 3.0)
                if f0 is not None and f1 is not None:
                    p[1] = f1 + max(0.0, p[1] - f0)
            p[0], p[2] = nx, nz
        else:
            p[1] = -s.y()
        self.on_move(marker.obj["id"], p)

    # ---- navigation
    def wheelEvent(self, ev):
        f = 1.0015 ** ev.angleDelta().y()
        cur = self.transform().m11()
        if 0.5 < cur * f < 4000:
            self.scale(f, f)

    def mousePressEvent(self, ev):
        if ev.button() in (Qt.RightButton, Qt.MiddleButton):
            self._pan = ev.position()
            self.setCursor(Qt.ClosedHandCursor)
            return
        item = self.itemAt(ev.position().toPoint())
        if item is None or not isinstance(item, Marker):
            self.on_select(None)
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._pan is not None:
            d = ev.position() - self._pan
            self._pan = ev.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(d.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(d.y()))
            return
        s = self.mapToScene(ev.position().toPoint())
        self.on_hover([s.x(), s.y()])
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if self._pan is not None and ev.button() in (Qt.RightButton, Qt.MiddleButton):
            self._pan = None
            self.unsetCursor()
            return
        super().mouseReleaseEvent(ev)

    def drawBackground(self, painter, rect):
        super().drawBackground(painter, rect)
        if not self.show_grid:
            return
        scale = self.transform().m11()
        for step, alpha in ((1.0, 28), (10.0, 60)):
            if step * scale < 6:
                continue
            pen = QtGui.QPen(QtGui.QColor(150, 160, 190, alpha), 0)
            pen.setCosmetic(True)
            painter.setPen(pen)
            x = math.floor(rect.left() / step) * step
            while x <= rect.right():
                painter.drawLine(QtCore.QLineF(x, rect.top(), x, rect.bottom()))
                x += step
            y = math.floor(rect.top() / step) * step
            while y <= rect.bottom():
                painter.drawLine(QtCore.QLineF(rect.left(), y, rect.right(), y))
                y += step
        pen = QtGui.QPen(QtGui.QColor(200, 120, 120, 90), 0)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawLine(QtCore.QLineF(rect.left(), 0, rect.right(), 0))
        painter.drawLine(QtCore.QLineF(0, rect.top(), 0, rect.bottom()))
