# -*- coding: utf-8 -*-
"""Presentation styles scoped to AssetForge's own Maya controls."""
from __future__ import absolute_import, unicode_literals

import io
import json
import math
import os
import re


def maya_pixel_scale(cmds):
    """Return Maya's visual scale in Qt logical pixels, accounting for Qt's own DPI handling."""
    try:
        from PySide6 import QtWidgets
    except ImportError:
        from PySide2 import QtWidgets
    try:
        maya_scale = float(cmds.mayaDpiSetting(query=True, realScaleValue=True))
    except (AttributeError, RuntimeError, TypeError):
        maya_scale = 1.0
    screen = QtWidgets.QApplication.primaryScreen()
    return max(1.0, maya_scale / float(screen.devicePixelRatio())) if screen else max(1.0, maya_scale)


class WorkbenchSkin(object):
    def __init__(self, directory, scale=1.0):
        self.scale = scale
        try:
            from PySide6 import QtCore, QtGui, QtWidgets
            from shiboken6 import wrapInstance
        except ImportError:
            from PySide2 import QtCore, QtGui, QtWidgets
            from shiboken2 import wrapInstance
        self.core, self.gui, self.widgets = QtCore, QtGui, QtWidgets
        self.wrap = wrapInstance
        self.directory = directory
        with io.open(os.path.join(directory, "theme.json"), encoding="utf-8") as stream:
            self.theme = json.load(stream)
        self.icons = {}
        self.icon_sources = {}

    def apply_typeface(self, dock_path):
        if os.name != "nt":
            return
        families = self.gui.QFontDatabase().families()
        family = next((f for f in ("Microsoft YaHei UI", "Microsoft YaHei", "微软雅黑")
                       if f in families), None)
        if family:
            dock = self.widget(dock_path)
            dock.setStyleSheet(dock.styleSheet() + '\nQWidget {font-family: "' + family + '";}')

    def tooltip_style(self):
        return ("QToolTip {{background-color:{button};color:{text};border:1px solid {muted};"
                "border-radius:2px;padding:4px;}}").format(**self.theme)

    def apply_tooltips(self, dock_path):
        dock = self.widget(dock_path)
        if dock is not None:
            dock.setStyleSheet(dock.styleSheet() + "\n" + self.tooltip_style())

    def px(self, value):
        return int(round(value * self.scale))

    def _style(self, widget, css):
        if self.scale != 1.0:
            css = re.sub(r"(\d+)px", lambda m: str(self.px(int(m.group(1)))) + "px", css)
        widget.setStyleSheet(css)

    def pixmap(self, icon, size):
        return self.icon(icon).pixmap(self.px(size), self.px(size))

    def widget(self, path, kind=None):
        import maya.OpenMayaUI as omui
        pointer = omui.MQtUtil.findControl(path) or omui.MQtUtil.findLayout(path)
        if not pointer:
            return None
        # Maya's private button/label subclasses do not always acquire the correct Python
        # type when wrapped as QWidget. Ask for the documented base of this specific command.
        kind = kind or self.widgets.QWidget
        widget = self.wrap(int(pointer), kind)
        if isinstance(widget, kind) and widget.inherits(kind.staticMetaObject.className()):
            return widget
        return widget.findChild(kind)

    def icon(self, name):
        if name in self.icons:
            return self.icons[name]
        native = {
            "component": ("selectByComponent.png", "selectComponent.png"),
            "vertices": ("componentTag_vertex.png", "polySelectVertex.png"),
            "ring": ("polyGrowSelection.png",),
            "locate": ("frameSelected.png", "traxFrameSelected.png"),
            "settings": ("preferences.png", "menu_options.png"),
            "log": ("scriptEditor.png", "scriptEdPersp.png"),
        }
        atlas = {"inspect": "inspect_asset", "publish": "export_package", "publish-on-accent": "export_package",
                 "geometry": "focus_camera", "locate": "focus_camera", "refresh": "rescan_asset",
                 "component": "select_vertex", "vertices": "select_vertex", "ring": "grow_selection"}
        folder = os.path.join(self.directory, "icons")
        candidates = [":/" + filename for filename in native.get(name, ())]
        file_name = atlas.get(name, name)
        if name == "brand":
            candidates.append(os.path.join(self.directory, "brand", "af_shelf.png"))
        else:
            candidates.extend(os.path.join(folder, file_name + suffix) for suffix in (".svg", ".png"))
        icon = self.gui.QIcon()
        for path in candidates:
            if self.core.QFile.exists(path):
                icon = self.gui.QIcon(path)
                if not icon.pixmap(self.px(16), self.px(16)).isNull():
                    self.icon_sources[name] = path
                    break
        # Preserve the source alpha when placing the package mark on the light primary action.
        if name == "publish-on-accent" or name.startswith("chevron-"):
            ink = self.theme["onAccent" if name == "publish-on-accent" else "muted"]
            pixmap = icon.pixmap(64, 64)
            if not pixmap.isNull():
                painter = self.gui.QPainter(pixmap)
                painter.setCompositionMode(self.gui.QPainter.CompositionMode_SourceIn)
                painter.fillRect(pixmap.rect(), self.gui.QColor(ink))
                painter.end()
                icon = self.gui.QIcon(pixmap)
        if name == "folder" and icon.isNull():
            icon = self.widgets.QApplication.style().standardIcon(self.widgets.QStyle.SP_DirOpenIcon)
        self.icons[name] = icon
        return icon

    def box(self, path, role):
        widget = self.widget(path)
        if widget is None:
            return
        t = self.theme
        target = widget.viewport() if isinstance(widget, self.widgets.QAbstractScrollArea) else widget
        target.setAttribute(self.core.Qt.WA_StyledBackground, True)
        target.setProperty("afSurface", role)
        fill = t[role] if role in ("canvas", "header", "card") else "transparent"
        border = "1px solid " + t["cardStroke"] if role == "card" else "none"
        radius = t["cardRadius"] if role in ("card", "header") else 0
        self._style(target, 'QWidget[afSurface="%s"] { background: %s; border: %s; border-radius: %spx; }'
                             % (role, fill, border, radius))
        if role == "canvas":
            scroll = widget if isinstance(widget, self.widgets.QAbstractScrollArea) else widget.findChild(self.widgets.QAbstractScrollArea)
            if scroll:
                self._style(scroll, ("QScrollArea {{border: none; background:{canvas};}} "
                                      "QScrollBar:vertical {{width:9px;margin:2px 1px 8px 1px;background:{canvas};}} "
                                      "QScrollBar::handle:vertical {{background:{muted};border-radius:3px;min-height:22px;}} "
                                      "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {{height:0px;}}").format(**t))
                scroll.viewport().setAutoFillBackground(True)
                palette = scroll.viewport().palette()
                palette.setColor(self.gui.QPalette.Window, self.gui.QColor(t["canvas"]))
                scroll.viewport().setPalette(palette)

    def fill_dock(self, dock_path, scroll_path, surface_path):
        dock = self.widget(dock_path)
        surface = self.widget(surface_path)
        part = self.widget(scroll_path)
        if dock is None or surface is None or part is None:
            return
        # Maya can leave the unused part of its native viewport outside the content layout.
        # Paint the full viewport even when the review stack occupies only its top portion.
        color = self.gui.QColor(self.theme["canvas"])
        self._canvas_widgets = []
        part = surface.parentWidget()
        while part is not None and (part == dock or dock.isAncestorOf(part)):
            self._canvas_widgets.append(part)
            part.setAutoFillBackground(True)
            palette = part.palette()
            palette.setColor(self.gui.QPalette.Window, color)
            palette.setColor(self.gui.QPalette.Base, color)
            part.setPalette(palette)
            part.setProperty("afCanvasFill", True)
            part.setAttribute(self.core.Qt.WA_StyledBackground, True)
            part.setStyleSheet(part.styleSheet() + '\nQWidget[afCanvasFill="true"] {background-color:' + color.name() + ';}')
            if part == dock:
                break
            part = part.parentWidget()

        # The workspace contains nested scroll fields. Match the ancestor of the main column
        # using Qt's own widget tree, without casting Maya's placeholder as a QScrollArea.
        scroll = next((area for area in dock.findChildren(self.widgets.QScrollArea)
                       if area.isAncestorOf(surface)), None)
        if scroll is None:
            return
        content = scroll.widget()
        self._canvas_widgets.extend((scroll, content, surface, scroll.viewport()))
        # Let Qt resize the content on both axes. The Maya wrapper's horizontal size hint
        # includes hidden fields and should not determine the dock width. Vertical sizing
        # still uses the real height hint, so expanding a section enables normal scrolling.
        for widget in (surface, content):
            widget.setSizePolicy(self.widgets.QSizePolicy.Ignored, self.widgets.QSizePolicy.Preferred)
            widget.setMinimumWidth(0)
            if widget.layout():
                widget.layout().setSizeConstraint(self.widgets.QLayout.SetNoConstraint)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(self.core.Qt.ScrollBarAsNeeded)

    def fields(self, path):
        widget = self.widget(path)
        if widget is None:
            return
        # Only descendants of this card receive these rules; Maya's own editors keep their host theme.
        t = self.theme
        arrow = os.path.join(self.directory, "icons", "chevron-down.svg").replace("\\", "/")
        self._style(widget, (
            "QLabel {{color:{secondary}; background:transparent;border:none;}} "
            "QLineEdit,QComboBox,QSpinBox,QDoubleSpinBox,QTextEdit,QPlainTextEdit "
            "{{background:{button};color:{text};border:1px solid {stroke};border-radius:{controlRadius}px;"
            "padding:2px 4px;selection-background-color:{hover};}} "
            "QLineEdit:focus,QComboBox:focus,QSpinBox:focus,QDoubleSpinBox:focus,QTextEdit:focus "
            "{{border-color:{accent};}} "
            "QComboBox {{padding:2px;}} QComboBox::drop-down {{width:14px;border:0;}} "
            "QComboBox::down-arrow {{width:10px;height:10px;image:url('{arrow}');}} "
            "QComboBox QAbstractItemView {{background:{button};color:{text};selection-background-color:{hover};}} "
            "QPushButton,QToolButton {{background:{button};color:{secondary};border:1px solid {stroke};"
            "border-radius:{controlRadius}px;padding:2px 5px;}} "
            "QPushButton:hover,QToolButton:hover {{background:{hover};color:{text};}} "
            "QAbstractButton:pressed {{border-color:{accent};}} "
            "QGroupBox {{background:{card};border:1px solid {cardStroke};color:{text};}}"
        ).format(arrow=arrow, **t))

    def reader(self, path, fit_height=None):
        container = self.widget(path)
        if container is None:
            return
        editor = None
        for kind in (self.widgets.QTextEdit, self.widgets.QPlainTextEdit):
            if container.inherits(kind.staticMetaObject.className()):
                editor = self.widget(path, kind)
            else:
                editor = container.findChild(kind)
            if editor is not None:
                break
        if editor is None:
            return
        t = self.theme
        self._style(editor, ("QTextEdit,QPlainTextEdit {{background:{card};color:{text};"
                            "border:0;padding:4px 2px;font-size:12px;selection-background-color:{hover};}} "
                            "QScrollBar:vertical {{background:{card};width:7px;margin:0;}} "
                            "QScrollBar::handle:vertical {{background:{muted};min-height:18px;border-radius:3px;}} "
                            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {{height:0;}}").format(**t))
        editor.setHorizontalScrollBarPolicy(self.core.Qt.ScrollBarAlwaysOff)
        editor.setWordWrapMode(self.gui.QTextOption.WrapAtWordBoundaryOrAnywhere)
        if fit_height is not None:
            self._fit_result(editor, fit_height)

    def _fit_result(self, editor, set_height):
        core = self.core
        viewport = editor.viewport()
        editor.document().setDocumentMargin(self.px(1))

        class Fit(core.QObject):
            def eventFilter(self, watched, event):
                if event.type() == core.QEvent.Show or (
                        event.type() == core.QEvent.Resize and event.size().width() != event.oldSize().width()):
                    timer.start(0)
                return False

        fit = Fit(editor)
        timer = core.QTimer(fit)
        timer.setSingleShot(True)
        # QPlainTextEdit reports document height in lines. Measure its wrapped plain
        # text in a QTextDocument so both Maya editor types use actual pixel heights.
        measure = self.gui.QTextDocument(fit)

        def update():
            if not editor.isVisible() or viewport.width() < 1:
                return
            measure.setDefaultFont(editor.font())
            measure.setDefaultTextOption(editor.document().defaultTextOption())
            measure.setDocumentMargin(editor.document().documentMargin())
            measure.setPlainText(editor.toPlainText())
            measure.setTextWidth(viewport.width())
            margins = editor.height() - viewport.height()
            logical = int(math.ceil((measure.size().height() + margins) / self.scale))
            logical = min(96, max(20, logical))
            if editor.property("afResultHeight") != logical:
                editor.setProperty("afResultHeight", logical)
                set_height(logical)

        timer.timeout.connect(update)
        editor.textChanged.connect(lambda: timer.start(0))
        viewport.installEventFilter(fit)
        self._result_fit = fit

    def text(self, path, color="text", size=12, weight=400):
        widget = self.widget(path, self.widgets.QLabel)
        if widget is not None:
            self._style(widget, "QLabel {color:%s; background:transparent; border:none; "
                                 "font-size:%dpx; font-weight:%d;}" % (self.theme[color], size, weight))

    def pill(self, path, label, tone):
        widget = self.widget(path, self.widgets.QLabel)
        if widget is None:
            return
        self._paint_pill(widget, label, tone)

    def _paint_pill(self, widget, label, tone):
        t = self.theme
        ink = t.get(tone, t["muted"])
        base = self.gui.QColor(t["card"])
        color = self.gui.QColor(ink)
        fill = self.gui.QColor.fromRgb(*[int(round(color.getRgb()[i] * .13 + base.getRgb()[i] * .87)) for i in range(3)]).name()
        widget.setText(label)
        widget.setAlignment(self.core.Qt.AlignCenter)
        widget.setFixedHeight(self.px(18))
        text_ink = self.gui.QColor(ink).lighter(130).name() if tone == "danger" else ink
        self._style(widget, "QLabel {background:%s; color:%s; border:1px solid %s; border-radius:%dpx;"
                             "font-size:10px; font-weight:600; padding:0 6px;}" % (fill, text_ink, ink, min(7, t["pillRadius"])))
        widget.ensurePolished()
        widget.setFixedWidth(widget.fontMetrics().boundingRect(label).width() + self.px(18))

    def button(self, path, icon, role="action"):
        widget = self.widget(path, self.widgets.QPushButton)
        if widget is None:
            return
        t = self.theme
        widget.setIcon(self.icon(icon) if icon else self.gui.QIcon())
        widget.setIconSize(self.core.QSize(self.px(self.theme["iconSize"]), self.px(self.theme["iconSize"])))
        widget.setCursor(self.core.Qt.PointingHandCursor)
        widget.setProperty("afRole", role)
        widget.setProperty("afActive", False)
        if role == "navigation":
            self._style(widget, ("QPushButton {{background:transparent;color:{secondary};border:none;"
                                 "border-radius:4px;padding:0;font-size:17px;}} "
                                 "QPushButton:hover,QPushButton:focus {{background:{hover};color:{text};}}").format(**t))
            return widget
        if role == "publish":
            base, border, ink = t["accent"], t["accent"], t["onAccent"]
            hover, align = self.gui.QColor(base).lighter(113).name(), "center"
        elif role == "header":
            base, border, ink = t["card"], t["card"], t["text"]
            hover, align = t["hover"], "left"
        else:
            base, border, ink = t["button"], t["stroke"], t["text"]
            hover, align = t["hover"], "center"
        self._style(widget, (
            "QPushButton {{ background:{base}; color:{ink}; border:{borderWidth}px solid {border};"
            "border-radius:{controlRadius}px;padding:0 {pad}px;text-align:{align};font-size:12px;font-weight:{weight};}} "
            "QPushButton:hover {{background:{hover};border-color:{muted};}} "
            "QPushButton:pressed {{border-color:{accent};}} "
            'QPushButton[afActive="true"] {{background:{selected};border-color:{accent};}} '
            "QPushButton:disabled {{color:{muted};background:{card};border-color:{cardStroke};}}").format(
                base=base, ink=ink, border=border, hover=hover, selected=t["hover"], align=align,
                pad=1 if role == "tool" else 4, weight=600 if role in ("header", "publish") else 450,
                **{key: t[key] for key in ("borderWidth", "controlRadius", "accent", "muted", "card", "cardStroke")}))
        return widget

    def active(self, path, active):
        widget = self.widget(path, self.widgets.QPushButton)
        if widget is not None and bool(widget.property("afActive")) != active:
            widget.setProperty("afActive", active)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()

    def _icon_label(self, icon, parent, size):
        label = self.widgets.QLabel(parent)
        label.setPixmap(self.pixmap(icon, size))
        label.setAttribute(self.core.Qt.WA_TransparentForMouseEvents)
        self._style(label, "background:transparent;border:none;")
        label.setFixedSize(self.px(size), self.px(size))
        return label

    def _label(self, text, parent, color, size, bold=False):
        label = self.widgets.QLabel(text, parent)
        label.setAttribute(self.core.Qt.WA_TransparentForMouseEvents)
        label.setSizePolicy(self.widgets.QSizePolicy.Ignored, self.widgets.QSizePolicy.Preferred)
        self._style(label, "background:transparent;border:none;color:%s;font-size:%dpx;font-weight:%d;"
                            % (self.theme[color], size, 600 if bold else 400))
        return label

    def brand(self, path):
        title = self.widget(path, self.widgets.QLabel)
        title.setText("")
        title.setAccessibleName("AssetForge v0.2")
        layout = self.widgets.QHBoxLayout(title)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self.px(5))
        layout.addWidget(self._icon_label("brand", title, 16))
        name = self._label("AssetForge", title, "text", 14, True)
        name.setSizePolicy(self.widgets.QSizePolicy.Maximum, self.widgets.QSizePolicy.Preferred)
        layout.addWidget(name)
        version = self.widgets.QLabel("v0.2", title)
        version.setAttribute(self.core.Qt.WA_TransparentForMouseEvents)
        self._style(version, 'color:%s;font:10px "Consolas", monospace;background:transparent;border:none;' % self.theme["muted"])
        layout.addWidget(version)
        layout.addStretch()

    def card_title(self, path, title, icon, expanded):
        button = self.button(path, icon if icon != "log" else None, "header")
        button.setText("")
        button.setIcon(self.gui.QIcon())
        button.setAccessibleName(title)
        layout = self.widgets.QHBoxLayout(button)
        layout.setContentsMargins(self.px(8), 0, self.px(8), 0)
        layout.setSpacing(self.px(7))
        if icon != "log":
            layout.addWidget(self._icon_label(icon, button, 18))
        layout.addWidget(self._label(title, button, "text", 13, True), 1)
        arrow = self._icon_label("chevron-down" if expanded else "chevron-right", button, 12)
        layout.addWidget(arrow)
        return arrow

    def rule(self, path, label):
        widget = self.widget(path, self.widgets.QPushButton)
        if widget is None:
            return
        widget.setText("")
        widget.setAccessibleName(label)
        self._style(widget, "QPushButton {background:transparent; border:none;} QPushButton:hover {background:"
                             + self.theme["button"] + ";}")
        layout = self.widgets.QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self.px(5))
        arrow = self._icon_label("chevron-down", widget, 10)
        layout.addWidget(arrow)
        title = self._label(label, widget, "secondary", 12, True)
        title.setSizePolicy(self.widgets.QSizePolicy.Maximum, self.widgets.QSizePolicy.Preferred)
        layout.addWidget(title)
        line = self.widgets.QFrame(widget)
        line.setFixedHeight(self.px(1))
        line.setStyleSheet("background:" + self.theme["cardStroke"] + ";border:none;")
        layout.addWidget(line, 1)
        return arrow

    def issue(self, path, row, target):
        severity = row["severity"]
        button = self.button(path, "locate", "issue")
        button.setAccessibleName(button.text())
        button.setText("")
        button.setIcon(self.gui.QIcon())
        tone = "danger" if severity == "error" else "warning"
        t = self.theme
        self._style(button, (
            'QPushButton {{background:{card};border:1px solid {cardStroke};border-left:3px solid {tone};'
            'border-radius:6px;}} QPushButton:hover {{background:{hover};}} '
            'QPushButton[afActive="true"] {{background:{hover};border:1px solid {secondary};'
            'border-left:3px solid {tone};}}').format(tone=t[tone], **{k: t[k] for k in ("card", "hover", "secondary", "cardStroke")}))
        layout = self.widgets.QGridLayout(button)
        layout.setContentsMargins(self.px(8), self.px(3), self.px(6), self.px(3))
        layout.setHorizontalSpacing(self.px(4))
        layout.setVerticalSpacing(0)
        icon = {"zero_area_triangles": "warn_zero_area", "zero_length_edges": "warn_zero_edge"}.get(
            row["rule"], "status_reject" if severity == "error" else "warn_zero_area")
        layout.addWidget(self._icon_label(icon, button, 16), 0, 0)
        title = self._label(row["label"], button, "text", 12, True)
        layout.addWidget(title, 0, 1)
        count = len(row["components"])
        kind = "面" if row["kind"] == "f" else "边"
        tag = ("阻断" if severity == "error" else "警告") + (" · {0}{1}".format(count, kind) if count else "")
        badge = self._label(tag, button, tone, 10, True)
        self._paint_pill(badge, tag, tone)
        badge.setSizePolicy(self.widgets.QSizePolicy.Fixed, self.widgets.QSizePolicy.Fixed)
        layout.setColumnMinimumWidth(2, badge.width())
        layout.addWidget(badge, 0, 2)
        if target:
            layout.addWidget(self._label(target, button, "secondary", 10), 1, 1, 1, 2)
        layout.setColumnStretch(1, 1)
