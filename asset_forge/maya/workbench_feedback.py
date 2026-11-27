# -*- coding: utf-8 -*-
"""View-local guidance for Maya workbench actions."""
from __future__ import absolute_import, unicode_literals

from asset_forge.maya.workbench_locator import _model_panel


def check_result(validation, rows=None):
    checks = validation.get("checks", [])
    severities = [item.get("status") for item in checks]
    errors = severities.count("error")
    warnings = severities.count("warning")
    passes = severities.count("pass")
    first = (rows or [None])[0]
    title = "（{0}）".format(first["label"]) if first else ""
    kind = (first or {}).get("diagnostic", {}).get("action_kind")
    if errors or not validation.get("can_export"):
        finding = "{0} 项阻断".format(errors) if errors else "{0} 个警告 · 当前预设阻断导出".format(warnings)
        next_step = "在下方指定贴图集" if kind == "candidate" else "查看问题原因和处理方式"
        tone, badge, icon = "error", finding, "✕"
    elif warnings:
        finding = "{0} 个警告".format(warnings)
        next_step = "点击问题行高亮定位，或继续导出" if kind == "components" else "查看下方原因，或继续导出"
        tone, badge, icon = "warning", finding, "⚠"
    else:
        finding = "通过全部 {0} 项检查".format(passes)
        next_step = "点击「检查并导出 Package」"
        tone, badge, icon = "ok", "已通过", "✓"
    return {"tone": tone, "text": "{0} {1}{2} · {3}".format(icon, finding, title, next_step),
            "finding": finding + title, "badge": badge, "icon": icon, "next": next_step}


def toast_geometry(view_width, view_height, preferred_width, height_for_width, obstacle, gap):
    """Choose an in-viewport rectangle. All coordinates are relative to the model panel."""
    left, right = gap, view_width - gap
    top, bottom = 2 * gap, view_height - gap

    def fit(x1, x2, y):
        width = min(preferred_width, x2 - x1)
        if width <= 0 or y >= bottom:
            return None
        height = height_for_width(width)
        if height > bottom - y:
            return None
        # Stay close to the viewport center within this free area.
        x = max(x1, min((view_width - width) // 2, x2 - width))
        return x, y, width, height

    center = fit(left, right, top)
    if center is None or obstacle is None:
        return center
    x, y, w, h = center
    ox, oy, ow, oh = obstacle
    if x + w <= ox or ox + ow <= x or y + h <= oy or oy + oh <= y:
        return center
    sides = sorted(((left, min(right, ox - gap)), (max(left, ox + ow + gap), right)),
                   key=lambda span: span[1] - span[0], reverse=True)
    for start, end in sides:
        if end - start >= min(preferred_width, 12 * gap):
            side = fit(start, end, top)
            if side:
                return side
    return fit(left, right, max(top, oy + oh + gap))


def viewport_toast(window, message):
    from maya.api import OpenMayaUI
    panel = _model_panel(window.cmds)
    if not panel:
        return None
    skin = window.skin
    core, widgets = skin.core, skin.widgets
    view = OpenMayaUI.M3dView.getM3dViewFromModelPanel(panel)
    viewport = skin.wrap(int(view.widget()), widgets.QWidget)
    flags = core.Qt.ToolTip | core.Qt.FramelessWindowHint | core.Qt.WindowTransparentForInput
    gui = skin.gui
    padding_x, padding_y = skin.px(14), skin.px(8)
    text_flags = core.Qt.AlignCenter | core.Qt.TextWordWrap

    class Toast(widgets.QLabel):
        def paintEvent(self, event):
            # Qt 5 on Windows ignores QLabel's stylesheet background on translucent tooltips.
            painter = gui.QPainter(self)
            painter.setRenderHint(gui.QPainter.Antialiasing)
            painter.setPen(gui.QPen(gui.QColor("#3A3A3A"), skin.px(1)))
            painter.setBrush(gui.QColor(20, 20, 20, 224))
            inset = skin.px(1) / 2.0
            shape = core.QRectF(self.rect()).adjusted(inset, inset, -inset, -inset)
            painter.drawRoundedRect(shape, skin.px(6), skin.px(6))
            painter.setPen(gui.QColor("white"))
            painter.drawText(self.rect().adjusted(padding_x, padding_y, -padding_x, -padding_y),
                             text_flags, message)
            painter.end()

    toast = Toast(viewport, flags)
    toast.setObjectName("assetForgeViewportToast")
    toast.setAttribute(core.Qt.WA_TranslucentBackground)
    toast.setAttribute(core.Qt.WA_ShowWithoutActivating)
    toast.setAttribute(core.Qt.WA_TransparentForMouseEvents)
    toast.setFocusPolicy(core.Qt.NoFocus)
    toast.setTextFormat(core.Qt.PlainText)
    toast.setText(message)
    font = toast.font()
    font.setPixelSize(skin.px(13))
    toast.setFont(font)
    metrics = toast.fontMetrics()
    width = metrics.horizontalAdvance(message) if hasattr(metrics, "horizontalAdvance") else metrics.width(message)
    def height_for_width(box_width):
        inner = max(1, box_width - 2 * padding_x)
        bounds = metrics.boundingRect(core.QRect(0, 0, inner, 10000), text_flags, message)
        return bounds.height() + 2 * padding_y

    obstacle = None
    workbench = window.chrome.top if window.chrome else None
    if workbench is not None and workbench.isVisible():
        frame = workbench.frameGeometry()
        offset = viewport.mapFromGlobal(frame.topLeft())
        obstacle = (offset.x(), offset.y(), frame.width(), frame.height())
    rect = toast_geometry(viewport.width(), viewport.height(), width + skin.px(3) + 2 * padding_x,
                          height_for_width, obstacle, skin.px(8))
    if rect is None:
        toast.deleteLater()
        return None
    x, y, box_width, box_height = rect
    toast.resize(box_width, box_height)
    toast.move(viewport.mapToGlobal(core.QPoint(x, y)))
    animation = core.QPropertyAnimation(toast, b"windowOpacity", toast)
    animation.setDuration(3500)
    animation.setStartValue(1.0)
    animation.setKeyValueAt(.86, 1.0)
    animation.setEndValue(0.0)
    animation.finished.connect(toast.deleteLater)
    toast.show()
    animation.start()
    return toast
