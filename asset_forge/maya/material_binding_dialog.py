# -*- coding: utf-8 -*-
"""Modal editor for explicitly matching material slots to external texture sets."""

from asset_forge.maya.workbench_skin import WorkbenchSkin


def choose(skin, choices, overrides):
    import maya.OpenMayaUI as omui

    if skin is None:
        from asset_forge.maya.ui import asset_forge_repo_root
        from os.path import join

        skin = WorkbenchSkin(join(asset_forge_repo_root(), "Plugins", "AssetForge", "Resources", "Workbench"))
    widgets, core = skin.widgets, skin.core
    qt, theme = core.Qt, skin.theme
    parent = skin.wrap(int(omui.MQtUtil.mainWindow()), widgets.QWidget)
    dialog = widgets.QDialog(parent, qt.Dialog | qt.FramelessWindowHint)
    dialog.setObjectName("assetForgeTextureBinding")
    dialog.setWindowTitle("手动绑定材质槽贴图")
    dialog.setAccessibleName("手动绑定材质槽贴图")
    dialog.setModal(True)
    dialog.setAttribute(qt.WA_StyledBackground)
    skin._style(dialog, ("""
        QDialog#assetForgeTextureBinding {{
            background:{canvas};color:{text};border:1px solid {muted};font-size:13px;
        }}
        QLabel {{color:{text};background:transparent;}}
        QLabel[afSecondary="true"] {{color:{secondary};}}
        QScrollArea,QWidget#assetForgeBindingRows {{background:{canvas};border:none;}}
        QComboBox,QPushButton {{
            color:{text};background:{button};border:1px solid {muted};border-radius:2px;
            min-height:24px;padding:3px 6px;
        }}
        QComboBox:hover,QPushButton:hover {{background:{hover};}}
        QComboBox:focus,QPushButton:focus {{border-color:{accent};}}
        QComboBox::drop-down {{border:none;width:20px;}}
        QComboBox::down-arrow {{image:url('{arrow}');width:12px;height:12px;}}
        QComboBox QAbstractItemView {{
            color:{text};background:{button};border:1px solid {muted};
            selection-background-color:{hover};selection-color:{text};outline:0;
        }}
        QAbstractItemView::item:hover,QAbstractItemView::item:selected {{background:{hover};color:{text};}}
        QPushButton#assetForgeBindingApply {{background:{accent};color:{onAccent};font-weight:600;}}
        QPushButton#assetForgeBindingApply:focus {{border:2px solid {muted};}}
        QScrollBar:vertical {{background:{canvas};width:8px;margin:0;}}
        QScrollBar::handle:vertical {{background:{muted};min-height:20px;}}
        QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {{height:0;}}
        """).format(arrow=(skin.directory + "/icons/chevron-down.svg").replace("\\", "/"), **theme) + skin.tooltip_style())

    layout = widgets.QVBoxLayout(dialog)
    layout.setContentsMargins(*[skin.px(12)] * 4)
    layout.setSpacing(skin.px(8))
    title = widgets.QLabel("手动绑定材质槽贴图")
    title.setStyleSheet("font-weight:600;")
    layout.addWidget(title)
    guide = widgets.QLabel("为每个 Maya 材质槽选择外部贴图集。保留「自动匹配」时，继续使用当前匹配规则。")
    guide.setWordWrap(True)
    guide.setProperty("afSecondary", True)
    layout.addWidget(guide)

    table = widgets.QWidget()
    table.setObjectName("assetForgeBindingRows")
    grid = widgets.QGridLayout(table)
    grid.setContentsMargins(0, 0, skin.px(5), 0)
    grid.setVerticalSpacing(skin.px(5))
    grid.setHorizontalSpacing(skin.px(8))
    grid.setColumnStretch(0, 2)
    grid.setColumnStretch(1, 3)
    for column, text in enumerate(("Maya 材质槽", "外部贴图集")):
        header = widgets.QLabel(text)
        header.setStyleSheet("font-weight:600;")
        header.setMinimumHeight(skin.px(22))
        grid.addWidget(header, 0, column)
    choices_by_slot = {}
    for row, (name, candidates) in enumerate(choices, 1):
        label = widgets.QLabel(name)
        label.setTextFormat(qt.PlainText)
        label.setWordWrap(True)
        label.setMinimumWidth(0)
        label.setSizePolicy(widgets.QSizePolicy.Ignored, widgets.QSizePolicy.Preferred)
        label.setToolTip(name)
        grid.addWidget(label, row, 0)
        menu = widgets.QComboBox()
        # QSS targets an explicit Qt list view instead of the operating system's menu.
        menu.setView(widgets.QListView(menu))
        menu.setSizeAdjustPolicy(widgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        menu.setMinimumContentsLength(1)
        menu.setSizePolicy(widgets.QSizePolicy.Ignored, widgets.QSizePolicy.Fixed)
        menu.setAccessibleName(name + "的外部贴图集")
        menu.setToolTip("选择要绑定到这个材质槽的贴图集。")
        menu.addItem("自动匹配", "")
        menu.setItemData(0, "由当前匹配规则识别贴图集。", qt.ToolTipRole)
        for candidate in candidates:
            menu.addItem(candidate, candidate)
            menu.setItemData(menu.count() - 1, "绑定到 " + candidate, qt.ToolTipRole)
        if overrides.get(name) in candidates:
            menu.setCurrentIndex(menu.findData(overrides[name]))
        label.setBuddy(menu)
        grid.addWidget(menu, row, 1)
        choices_by_slot[name] = menu
    grid.setRowStretch(len(choices) + 1, 1)
    scroll = widgets.QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(qt.ScrollBarAlwaysOff)
    scroll.setWidget(table)
    layout.addWidget(scroll, 1)

    footer = widgets.QHBoxLayout()
    footer.addStretch(1)
    cancel = widgets.QPushButton("取消")
    cancel.setToolTip("放弃本次手动设置。")
    cancel.clicked.connect(dialog.reject)
    footer.addWidget(cancel)
    apply_changes = widgets.QPushButton("应用并重新检查")
    apply_changes.setObjectName("assetForgeBindingApply")
    apply_changes.setToolTip("应用对应关系，重新检查当前资产。")
    apply_changes.setDefault(True)
    apply_changes.clicked.connect(dialog.accept)
    footer.addWidget(apply_changes)
    layout.addLayout(footer)
    dialog.resize(skin.px(445), skin.px(min(530, 188 + len(choices) * 38)))
    execute = getattr(dialog, "exec", None) or dialog.exec_
    try:
        if execute() != widgets.QDialog.Accepted:
            return None
        return {name: menu.currentData() for name, menu in choices_by_slot.items() if menu.currentData()}
    finally:
        dialog.deleteLater()
