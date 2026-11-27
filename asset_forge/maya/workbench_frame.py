# -*- coding: utf-8 -*-
"""Frameless chrome scoped to an independent Maya workspace window."""
from __future__ import absolute_import, unicode_literals

import math
import os


def _external_border(hwnd, value, expected=None):
    if os.name != "nt":
        return None
    import ctypes
    try:
        api = ctypes.windll.dwmapi
        handle = ctypes.c_void_p(hwnd)
        previous, new = ctypes.c_uint32(), ctypes.c_uint32(value)
        if api.DwmGetWindowAttribute(handle, 34, ctypes.byref(previous), ctypes.sizeof(previous)) == 0:
            if expected is not None and previous.value != expected:
                return None
            if api.DwmSetWindowAttribute(handle, 34, ctypes.byref(new), ctypes.sizeof(new)) == 0:
                return previous.value
    except (AttributeError, OSError):
        pass
    return None


def _fit_tab_page(dock):
    stack = dock.parentWidget()
    if stack is None or not stack.inherits("QStackedWidget") or stack.currentWidget() is not dock:
        return
    bounds = stack.contentsRect()
    if dock.geometry() != bounds:
        # Maya can restore the old tab-title offset after leaving the bar hidden.
        stack.layout().setGeometry(bounds)


def create(window):
    skin = window.skin
    core, gui, widgets = skin.core, skin.gui, skin.widgets
    try:
        from shiboken6 import isValid
    except ImportError:
        from shiboken2 import isValid
    qt = core.Qt
    class Outline(widgets.QWidget):
        def __init__(self, owner):
            super(Outline, self).__init__(owner)
            self.setObjectName("assetForgeWindowOutline")
            self.setAttribute(qt.WA_TransparentForMouseEvents)
            self.setAttribute(qt.WA_NoSystemBackground)
            self.setFocusPolicy(qt.NoFocus)
            self.radius = 8

        def fit(self, rect, radius, outer):
            self.radius = radius
            self.setGeometry(rect)
            # Cover Maya's stock docking rim. Only the narrow ring can paint above Chromium.
            inset = skin.px(3)
            inner = gui.QPainterPath()
            inner.addRoundedRect(core.QRectF(rect).adjusted(inset, inset, -inset, -inset),
                                 radius-inset, radius-inset)
            self.setMask(outer.subtracted(gui.QRegion(inner.toFillPolygon().toPolygon())))
            self.show()
            self.raise_()
            self.update()

        def paintEvent(self, event):
            painter = gui.QPainter(self)
            painter.fillRect(self.rect(), gui.QColor(skin.theme["stroke"]))
            painter.setRenderHint(gui.QPainter.Antialiasing)
            painter.setPen(qt.NoPen)
            painter.setBrush(gui.QColor(skin.theme["canvas"]))
            rect = core.QRectF(self.rect()).adjusted(1, 1, -1, -1)
            painter.drawRoundedRect(rect, self.radius-1, self.radius-1)
            painter.end()

    class ResizeHandler(core.QObject):
        def __init__(self, frame):
            super(ResizeHandler, self).__init__(frame)
            self.frame = frame
            self.watched = set()
            self.update = core.QTimer(self)
            self.update.setSingleShot(True)
            self.update.timeout.connect(self.attach)
            self.origin = None
            self.cursor_target = None

        def attach(self):
            top = self.frame.top
            if self.frame.closed or top is None or not isValid(top):
                return
            # A WebEngine render widget consumes the mouse before it reaches its parent.
            # Observe only widgets belonging to this independent window, including late children.
            current = set(top.findChildren(widgets.QWidget))
            current.add(top)
            web = window.web
            if web is not None and web.native_slot is not None:
                current.add(web.view)
                current.update(web.view.findChildren(widgets.QWidget))
            for child in self.watched - current:
                if isValid(child):
                    child.removeEventFilter(self)
            for child in current - self.watched:
                child.installEventFilter(self)
            self.watched = current

        def clear_cursor(self):
            widget = self.cursor_target
            self.cursor_target = None
            if widget is not None and isValid(widget):
                if self.explicit_cursor:
                    widget.setCursor(self.previous_cursor)
                else:
                    widget.unsetCursor()

        def stop(self):
            self.update.stop()
            for child in self.watched:
                if isValid(child):
                    child.removeEventFilter(self)
            self.watched.clear()
            self.clear_cursor()
            if self.origin is not None and self.frame.top is not None and isValid(self.frame.top):
                self.frame.top.releaseMouse()
            self.origin = None

        def hit_test(self, top, point):
            x, y = point.x(), point.y()
            w, h = top.width(), top.height()
            edge, corner = skin.px(5), skin.px(15)
            if not top.rect().contains(point):
                return None, None
            left, right = x < corner, x >= w-corner
            upper, lower = y < corner, y >= h-corner
            if (left or right) and (upper or lower):
                return ((qt.LeftEdge if left else qt.RightEdge) | (qt.TopEdge if upper else qt.BottomEdge),
                        qt.SizeFDiagCursor if left == upper else qt.SizeBDiagCursor)
            if x < edge or x >= w-edge:
                return (qt.LeftEdge if x < edge else qt.RightEdge), qt.SizeHorCursor
            if y < edge or y >= h-edge:
                return (qt.TopEdge if y < edge else qt.BottomEdge), qt.SizeVerCursor
            return None, None

        def eventFilter(self, widget, event):
            kind = event.type()
            if kind in (core.QEvent.ChildAdded, core.QEvent.ChildRemoved):
                if not self.frame.closed and not self.update.isActive():
                    self.update.start(0)
                return False
            if kind not in (core.QEvent.MouseMove, core.QEvent.MouseButtonPress,
                            core.QEvent.MouseButtonRelease, core.QEvent.Leave):
                return False
            if kind == core.QEvent.Leave:
                if widget is self.cursor_target:
                    self.clear_cursor()
                return False
            if not widget.isWidgetType():
                return False
            owner = widget.window()
            web = window.web
            if owner is not self.frame.top and not (web and web.native_slot is not None and owner is web.view):
                return False
            top = self.frame.top
            if self.origin is not None:
                if kind == core.QEvent.MouseButtonRelease and event.button() == qt.LeftButton:
                    top.releaseMouse()
                    self.origin = None
                    return True
                if kind == core.QEvent.MouseMove:
                    self.resize(top, gui.QCursor.pos() - self.origin)
                    return True
                return False
            point = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
            edges, cursor = self.hit_test(top, top.mapFromGlobal(point))
            if edges is None:
                self.clear_cursor()
                return False
            if kind == core.QEvent.MouseMove:
                if widget is not self.cursor_target:
                    self.clear_cursor()
                    self.cursor_target = widget
                    self.explicit_cursor = widget.testAttribute(qt.WA_SetCursor)
                    self.previous_cursor = widget.cursor()
                if widget.cursor().shape() != cursor:
                    widget.setCursor(cursor)
            if kind != core.QEvent.MouseButtonPress or event.button() != qt.LeftButton:
                return False
            system = getattr(top.windowHandle(), "startSystemResize", None)
            if not system or not system(edges):
                self.edges, self.origin, self.original_rect = edges, point, top.geometry()
                top.grabMouse()
            return True

        def resize(self, top, delta):
            rect = core.QRect(self.original_rect)
            if self.edges & qt.LeftEdge:
                rect.setLeft(min(rect.right() - top.minimumWidth() + 1, rect.left() + delta.x()))
            elif self.edges & qt.RightEdge:
                rect.setWidth(max(top.minimumWidth(), rect.width() + delta.x()))
            if self.edges & qt.TopEdge:
                rect.setTop(min(rect.bottom() - top.minimumHeight() + 1, rect.top() + delta.y()))
            elif self.edges & qt.BottomEdge:
                rect.setHeight(max(top.minimumHeight(), rect.height() + delta.y()))
            top.setGeometry(rect)

    class Frame(core.QObject):
        def __init__(self):
            # Maya rebuilds the workspace widget during restoration and when changing docks.
            super(Frame, self).__init__(widgets.QApplication.instance())
            self.setObjectName("assetForgeWorkspaceFrame")
            self.dock = None
            self.floating = None
            self.top = None
            self.radius = 8
            self.resize_handler = ResizeHandler(self)
            self.watched_branch = []
            self.dock_tab = None
            self.floating_tab = None
            self.outline = None
            self.closed = False
            self.retries = 0
            self.border_state = None
            self.settling = None
            self.render_host = None
            self.drop_zone = None
            self.drop_hint = None
            self.drag_labels = []
            self.pending = core.QTimer(self)
            self.pending.setSingleShot(True)
            self.pending.timeout.connect(self.refresh)
            self.move_timer = core.QTimer(self)
            self.move_timer.timeout.connect(self.track_drag)
            widgets.QApplication.instance().aboutToQuit.connect(self.shutdown)
            self.pending.start(0)

        def current_dock(self):
            web = getattr(window, "web", None)
            source = web.panel if web else next((w for w in self.drag_labels if isValid(w)), None)
            if source is not None and isValid(source):
                current = source
                while current is not None:
                    if current.inherits("TworkspaceControl") and current.objectName() == window.workspace_name:
                        return current
                    current = current.parentWidget()
            return skin.widget(window.workspace_name)

        def schedule(self):
            if not self.closed and not self.pending.isActive():
                self.pending.start(0)

        def retry(self):
            # Workspace reconstruction and floating can settle on separate Qt event turns.
            if self.retries < 12 and not self.closed:
                self.retries += 1
                self.pending.start(75)

        def bind_drag(self, control):
            widget = skin.widget(control)
            self.drag_labels.append(widget)
            widget.installEventFilter(self)

        def restore_dock_tab(self):
            if self.dock_tab is None:
                return
            bar, hidden, auto_hide = self.dock_tab
            self.dock_tab = None
            if isValid(bar):
                bar.removeEventFilter(self)
                bar.setAutoHide(auto_hide)
                if bar.count() == 1:
                    bar.setVisible(not hidden)

        def restore_floating_tab(self):
            if self.floating_tab is None:
                return
            bar, was_hidden = self.floating_tab
            self.floating_tab = None
            if isValid(bar):
                bar.removeEventFilter(self)
                if bar.count() == 1 and not was_hidden:
                    bar.show()

        def hide_floating_tab(self, branch):
            tabs = next((widget for widget in branch if isinstance(widget, widgets.QTabWidget)), None)
            bar = None
            if tabs is not None and tabs.count() == 1:
                bar = tabs.tabBar()
            if self.floating_tab and self.floating_tab[0] is not bar:
                self.restore_floating_tab()
            if bar is not None:
                if self.floating_tab is None:
                    self.floating_tab = (bar, bar.isHidden())
                    bar.installEventFilter(self)
                bar.hide()

        def show_dock_tab(self, branch, floating):
            tabs = next((w for w in branch if w.inherits("QTabWidget")), None)
            bar = None
            if not floating and tabs is not None and tabs.count() == 1:
                page = tabs.widget(0)
                if page is self.dock or page.isAncestorOf(self.dock):
                    bar = tabs.tabBar()
            if self.dock_tab and self.dock_tab[0] is not bar:
                self.restore_dock_tab()
            # Some Maya layouts explicitly hide even their single native tab after toolbar docking.
            if bar is not None and bar.isHidden() and tabs.isVisible():
                if self.dock_tab is None:
                    self.dock_tab = (bar, bar.isHidden(), bar.autoHide())
                    bar.installEventFilter(self)
                bar.setAutoHide(False)
                bar.show()

        def refresh(self):
            if self.closed or not window.cmds.workspaceControl(window.workspace_name, exists=True):
                return
            self.dock = self.current_dock()
            if self.dock is None or not isValid(self.dock):
                self.retry()
                return
            # Maya may move an entire tab or splitter without reparenting workspaceControl itself.
            branch = [self.dock]
            while not branch[-1].isWindow():
                parent = branch[-1].parentWidget()
                if parent is None:
                    break
                branch.append(parent)
            for widget in self.watched_branch:
                if isValid(widget) and widget not in branch:
                    widget.removeEventFilter(self)
            for widget in branch:
                if widget not in self.watched_branch:
                    widget.installEventFilter(self)
            self.watched_branch = branch
            top = self.dock.window()
            floating = window.cmds.workspaceControl(window.workspace_name, query=True, floating=True)
            link = (floating, top)
            # The native tab drag temporarily owns a transparent docking panel. Decorating
            # it while Maya still holds the mouse changes its HWND under the drag loop.
            if widgets.QApplication.mouseButtons() & qt.LeftButton:
                self.settling = None
                self.pending.start(75)
                return
            if self.render_host != link:
                if self.settling != link:
                    self.settling = link
                    self.pending.start(90)
                    return
            if floating != self.floating:
                self.floating = floating
                window._native_window_mode(floating)
                # Maya's gripped toolbar mode hides the native tab. Keep the tab when docked.
                if window.cmds.workspaceControl(window.workspace_name, query=True, actLikeMayaUIElement=True) != floating:
                    window.cmds.workspaceControl(window.workspace_name, edit=True, actLikeMayaUIElement=floating)
                    self.schedule()
                    return
            self.show_dock_tab(branch, floating)
            if not floating or not self.exclusive_window(top):
                self.restore_floating_tab()
                self.release()
                if floating and top.metaObject().className() != "TworkspaceDockingPanel":
                    self.retry()
                else:
                    # A real floating group can be shared with other Maya panels.
                    # Refresh Chromium there too, leaving that group's chrome to Maya.
                    self.commit_host(link)
                return
            self.retries = 0
            self.hide_floating_tab(branch)
            if self.floating_tab is not None and top.isVisible() and not top.isMinimized():
                _fit_tab_page(self.dock)
            if self.top is top:
                if top.isVisible() and not top.isMinimized():
                    self.layout_frame()
                    if window.web and window.web.mode in ("main", "loading"):
                        window.web.fit()
                self.commit_host(link)
                return
            self.release()
            self.top = top
            self.old_flags = top.windowFlags()
            self.old_mask = top.mask()
            self.applied_mask = None
            geometry = top.geometry()
            top.setWindowFlags(self.old_flags | qt.FramelessWindowHint)
            top.setGeometry(geometry)
            self.outline = Outline(top)
            self.resize_handler.attach()
            top.installEventFilter(self)
            top.show()
            hwnd = int(top.winId())
            previous = _external_border(hwnd, 0xFFFFFFFE)
            if previous is not None:
                self.border_state = (hwnd, previous)
            self.layout_frame()
            self.commit_host(link)

        def exclusive_window(self, top):
            if top is None or not isValid(top) or not top.isWindow() or top.metaObject().className() != "TworkspaceDockingPanel":
                return False
            stack, found = [top], False
            while stack:
                item = stack.pop()
                if item.inherits("TworkspaceControl"):
                    if item.objectName() != window.workspace_name:
                        return False
                    found = True
                else:
                    # Skip the controls and chromium widgets inside each workspace.
                    stack.extend(child for child in item.children() if child.isWidgetType())
            return found

        def commit_host(self, link):
            if self.render_host != link:
                previous = self.render_host
                self.render_host = link
                if previous is not None and window.web:
                    window.web.rehost()

        def release(self, restore_flags=True):
            top = self.top
            if top is not None:
                self.resize_handler.stop()
            self.top = None
            self.stop_drag()
            if top is not None and isValid(top):
                if self.border_state and int(top.internalWinId() or 0) == self.border_state[0]:
                    _external_border(self.border_state[0], self.border_state[1], expected=0xFFFFFFFE)
                if self.outline is not None and isValid(self.outline):
                    self.outline.hide()
                    self.outline.deleteLater()
                # Maya can reuse this wrapper for a split/tab group. Undo only our
                # still-present decoration; never replace Maya's intervening flags or mask.
                if self.applied_mask is not None and top.mask() == self.applied_mask:
                    if self.old_mask.isEmpty():
                        top.clearMask()
                    else:
                        top.setMask(self.old_mask)
                if (restore_flags and top.isWindow() and top.metaObject().className() == "TworkspaceDockingPanel"
                        and not self.old_flags & qt.FramelessWindowHint and top.windowFlags() & qt.FramelessWindowHint):
                    visible, rect = top.isVisible(), top.geometry()
                    top.setWindowFlag(qt.FramelessWindowHint, False)
                    top.setGeometry(rect)
                    if visible:
                        top.show()
            self.border_state = None
            self.outline = None

        def close(self, *_):
            self.retire(quitting=False)

        def shutdown(self, *_):
            self.retire(quitting=True)

        def retire(self, quitting):
            if self.closed:
                return
            self.closed = True
            self.pending.stop()
            if quitting:
                self.resize_handler.stop()
                self.stop_drag()
                self.top = None
            else:
                self.restore_dock_tab()
                self.restore_floating_tab()
                self.release(restore_flags=False)
            for widget in self.watched_branch + self.drag_labels:
                if isValid(widget):
                    widget.removeEventFilter(self)
            self.watched_branch = []
            self.drag_labels = []
            self.deleteLater()

        def layout_frame(self):
            top = self.top
            if not self.exclusive_window(top):
                return
            w, h = top.width(), top.height()
            radius = min(skin.px(self.radius), w//2, h//2)
            # A polygon approximation can cut through a one-pixel arc. Quantize each scanline.
            outer = gui.QRegion(0, radius, w, h-2*radius)
            for y in range(radius):
                inset = int(round(radius - math.sqrt(radius**2 - (radius-y-.5)**2)))
                outer |= gui.QRegion(inset, y, w-2*inset, 1)
                outer |= gui.QRegion(inset, h-1-y, w-2*inset, 1)
            if top.mask() != outer:
                top.setMask(outer)
            self.applied_mask = outer
            if self.outline is not None:
                self.outline.fit(top.rect(), radius, outer)

        def sidebar_target(self):
            main = skin.widget("MayaWindow")
            if main is None or not main.isVisible():
                return None, None
            workspace = window.cmds.workspaceControl
            for name in ("ChannelBoxLayerEditor", "AttributeEditor"):
                if not workspace(name, exists=True) or workspace(name, query=True, floating=True):
                    continue
                side = skin.widget(name)
                if side is not None and side.isVisible() and main.isAncestorOf(side):
                    return main, core.QRect(main.mapFromGlobal(side.mapToGlobal(core.QPoint())), side.size())
            # With the built-in sidebar closed, the right edge still accepts the workbench.
            body = main.rect().adjusted(0, skin.px(55), 0, -skin.px(40))
            body.setLeft(max(body.left(), body.right() - skin.px(42)))
            return main, body

        def start_drag(self):
            top = self.top
            if top is None or not isValid(top) or self.move_timer.isActive():
                return
            self.drag_start = gui.QCursor.pos()
            self.drag_offset = self.drag_start - top.frameGeometry().topLeft()
            self.drop_main, self.drop_zone = self.sidebar_target()
            self.dragged = False
            self.move_timer.start(16)

        def stop_drag(self):
            self.move_timer.stop()
            if self.drop_hint is not None and isValid(self.drop_hint):
                self.drop_hint.hide()
                self.drop_hint.deleteLater()
            self.drop_hint = None
            self.drop_zone = None

        def track_drag(self):
            top = self.top
            if top is None or not isValid(top):
                self.stop_drag()
                return
            point = gui.QCursor.pos()
            if (point - self.drag_start).manhattanLength() >= widgets.QApplication.startDragDistance():
                self.dragged = True
            hover = self.dragged and self.drop_zone is not None and self.drop_zone.contains(self.drop_main.mapFromGlobal(point))
            if not (widgets.QApplication.mouseButtons() & qt.LeftButton):
                self.stop_drag()
                if hover:
                    window._switch_docking()
                return
            if not self.dragged:
                return
            top.move(point - self.drag_offset)
            if hover:
                if self.drop_hint is None:
                    self.drop_hint = widgets.QRubberBand(widgets.QRubberBand.Rectangle, self.drop_main)
                    self.drop_hint.setAttribute(qt.WA_TransparentForMouseEvents)
                    self.drop_hint.setGeometry(self.drop_zone)
                self.drop_hint.show()
            elif self.drop_hint is not None:
                self.drop_hint.hide()

        def eventFilter(self, watched, event):
            kind = event.type()
            if self.dock_tab and watched is self.dock_tab[0] and kind == core.QEvent.Hide:
                self.schedule()
            elif self.floating_tab and watched is self.floating_tab[0] and kind == core.QEvent.Show:
                self.schedule()
            elif watched is self.top and kind == core.QEvent.WindowStateChange:
                self.schedule()
            elif watched is self.dock and self.floating_tab and kind in (core.QEvent.Move, core.QEvent.ShowToParent):
                self.schedule()
            elif watched is self.top and kind == core.QEvent.Resize:
                self.layout_frame()
            elif kind in (core.QEvent.Show, core.QEvent.ParentChange, core.QEvent.ChildAdded, core.QEvent.ChildRemoved):
                if watched in self.watched_branch:
                    self.schedule()
            elif kind == core.QEvent.MouseButtonPress and watched in self.drag_labels and event.button() == qt.LeftButton:
                self.start_drag()
                return True
            return False

    return Frame()
