# -*- coding: utf-8 -*-
"""Local Qt WebEngine presentation for Maya's publish workbench."""
from __future__ import absolute_import, unicode_literals

import json
import os
from pathlib import Path


_FIELDS = {
    "name_prefix": "textFieldGrp", "triangle_budget": "intFieldGrp", "material_slot_budget": "intFieldGrp",
    "normal_format": "optionMenu",
    "platform": "optionMenu", "material_profile": "optionMenu",
    "target_path": "textFieldGrp", "target_engine_version": "textFieldGrp",
    "output_dir": "textFieldButtonGrp", "texture_folder": "textFieldButtonGrp",
    "texture_set_token": "textFieldGrp", "texture_prefix": "textFieldGrp",
    "asset_name_override": "textFieldGrp", "package_version_mode": "optionMenu",
    "nanite_policy": "optionMenu", "static_mesh_lod_group": "textFieldGrp",
    "static_mesh_lod_import_policy": "optionMenu", "virtual_texture_policy": "optionMenu",
    "texture_streaming_policy": "optionMenu", "texture_group": "textFieldGrp",
}
_EDITABLE_PAGES = {"rules", "publish"}
_PAGE_TEXT = {
    "publish": {
        "texture_details": ("scrollField", "texture_summary"), "asset_hint": ("text", "asset_hint"),
        "asset_details": ("scrollField", "asset_identity"), "preset_summary": ("scrollField", "settings_summary"),
    },
    "log": {
        "mcp_status": ("text", "mcp_status"), "preflight_hint": ("text", "preflight_hint"),
        "preflight": ("scrollField", "preflight"), "results": ("scrollField", "results"),
        "log": ("scrollField", "last_maya_log"),
    },
}
_DETAIL_ACTIONS = {
    "bindTextureSets": "_resolve_material_texture_sets", "repairTexturePrefix": "_rename_texture_prefix",
    "repairAssetPrefix": "_rename_prefix", "applyTransform": "_apply_transform_fix",
    "applyPreset": "_apply_current_settings", "startMcp": "_start_mcp_bridge", "showMcp": "_show_mcp_status",
    "scanOnly": "_scan", "exportDebug": "_export_debug_bundle", "analyze": "_analyze",
    "openLastDirectory": "_open_last_package",
}
_PREFLIGHT_FIELDS = {
    "name_prefix", "triangle_budget", "material_slot_budget", "normal_format", "material_profile",
    "target_path", "texture_folder", "texture_set_token",
    "nanite_policy", "static_mesh_lod_group", "static_mesh_lod_import_policy",
    "virtual_texture_policy", "texture_streaming_policy", "texture_group",
}
_EMPTY_CACHE = {"bytes": 0, "eligible_bytes": 0, "eligible_files": 0, "removed_bytes": 0,
                "removed_files": 0, "failed_files": 0, "directories": []}
_ABOUT_LINKS = {
    "openReleases": "https://github.com/Elviszhuoyu/DCC-AssetForge/releases",
    "openProjectHome": "https://github.com/Elviszhuoyu/DCC-AssetForge",
    "openAuthorHome": "https://work.zhuoyulabs.com",
}


def _license_name():
    try:
        with (Path(__file__).resolve().parents[2] / "LICENSE").open(encoding="utf-8") as stream:
            return next((line.strip() for line in stream if line.strip()), "")
    except OSError:
        return ""


def cache_state(window, clear=False):
    from asset_forge.shared.workbench_cache import manage_cache

    try:
        return manage_cache("maya", clear=clear, log_directory=window.logger.log_dir)
    except OSError:
        return dict(_EMPTY_CACHE, failed_files=1, unavailable=True)


def _field(window, name):
    kind = _FIELDS[name]
    flag = {"optionMenu": "value", "intFieldGrp": "value1"}.get(kind, "text")
    return kind, flag, getattr(window.cmds, kind), window.controls[name]


def _options(cmds, command, control):
    return [cmds.menuItem(item, query=True, label=True)
            for item in command(control, query=True, itemListLong=True) or []]


def update_field(window, page, name, value):
    if page not in _EDITABLE_PAGES or name not in _FIELDS or not isinstance(value, str):
        return
    kind, flag, command, control = _field(window, name)
    if kind == "optionMenu" and value not in _options(window.cmds, command, control):
        return
    if kind == "intFieldGrp":
        try:
            value = int(value)
        except ValueError:
            return
        if not 0 <= value <= 2147483647:
            return
    if value == command(control, query=True, **{flag: True}):
        return
    command(control, edit=True, **{flag: value})
    if name == "platform":
        window._change_rule_platform(value)
    elif name in ("texture_folder", "texture_set_token", "material_profile"):
        window._texture_matching_edited()
    elif name in _PREFLIGHT_FIELDS:
        window._review_inputs_edited()


def _host_version(cmds):
    version = str(cmds.about(version=True) or "").strip()
    if len(version) != 4 or not version.isdecimal():
        return version
    try:
        # The API number includes the update which some Maya builds omit from about(version=True).
        year, update_code = divmod(int(cmds.about(apiVersion=True)), 10000)
    except (RuntimeError, TypeError, ValueError):
        return version
    update = update_code // 100
    return "{0}.{1}".format(version, update) if year == int(version) and update else version


def detail_state(window, page, cache):
    state = {"page": page}
    if page == "preferences":
        return dict(state, toast=window.toast_enabled, hostVersion=_host_version(window.cmds),
                    licenseName=_license_name(), cache=cache)
    fields = {}
    for name in _FIELDS if page in _EDITABLE_PAGES else ():
        kind, flag, command, control = _field(window, name)
        fields[name] = {"value": command(control, query=True, **{flag: True})}
        if kind == "optionMenu":
            fields[name]["options"] = _options(window.cmds, command, control)
    text = {key: getattr(window.cmds, kind)(window.controls[control], query=True,
                                          **{("label" if kind == "text" else "text"): True})
            for key, (kind, control) in _PAGE_TEXT.get("publish" if page == "rules" else page, {}).items()}
    return dict(state, fields=fields, text=text)

def issue_key(window, index):
    return "{0}:{1}".format(window.issue_revision, index)


def view_state(window):
    cmds, controls = window.cmds, window.controls
    rows, candidates = [], []
    selected = ""
    active = window.active_issue
    for index, item in enumerate(window.issue_rows):
        key = issue_key(window, index)
        if item is active:
            selected = key
        count = len(item["components"])
        object_path = item.get("object_path", item["object"])
        reason = item.get("message", "")
        if count:
            count_text = "{0} {1}".format(count, "面" if item["kind"] == "f" else "边")
        elif item["candidates"]:
            count_text = "{0} 候选".format(len(item["candidates"]))
        else:
            count_text = "1 项"
        rows.append({"id": key, "label": item["label"], "severity": item["severity"],
                     "rule": item["rule"], "objectPath": object_path, "objectName": object_path.rsplit("|", 1)[-1],
                     "reason": reason, "detail": "\n".join(filter(None, (object_path, reason))),
                     "diagnostic": item.get("diagnostic", {}),
                     "isGeometry": bool(count and item["kind"] in ("f", "e")),
                     "countText": count_text, "canLocate": bool(count and item["kind"] in ("f", "e"))})
        if item["candidates"]:
            candidates.append({"id": key, "label": item["object"].rsplit("|", 1)[-1],
                               "options": [{"value": c, "label": c} for c in item["candidates"]],
                               "chosen": window.material_texture_set_overrides.get(item["object"], "")})
    status, status_text = window.review_status
    can_check = bool(window._review_selection())
    return {"asset": cmds.text(controls["current_asset"], query=True, label=True),
            "status": status, "statusText": status_text, "statusDetail": window.review_message, "issues": rows, "selectedId": selected,
            "feedback": active.get("location_feedback", "") if selected else "",
            "canLocate": bool(selected and active["components"] and can_check), "canRescan": bool(selected and can_check),
            "canPublish": window.review_gate is True, "canAttemptPublish": can_check,
            "checkNotice": window.check_notice, "actionButton": window.action_button,
            "hasSelection": can_check, "candidates": candidates, "selectionNote": window.selection_note,
            "checked": window.last_validation is not None, "passed": window._passed_checks(),
            "floating": cmds.workspaceControl(window.workspace_name, query=True, floating=True),
            "tools": window._tool_state(),
            "detail": (dict(detail_state(window, window.web.route, window.web.cache), section=window.web.section)
                       if getattr(window, "web", None) and window.web.route else None)}


def dispatch(window, action, payload):
    """Accept only operations that the current workbench state exposes."""
    if not isinstance(payload, dict):
        return
    if window.action_button.get("busy") and action != "close":
        return
    if action in ("selectIssue", "chooseCandidate", "diagnostic"):
        for index, row in enumerate(window.issue_rows):
            if issue_key(window, index) != payload.get("id"):
                continue
            if action == "selectIssue":
                window._row_callback(row)()
            elif action == "chooseCandidate" and payload.get("value") in row["candidates"]:
                window._binding_callback(row)(payload["value"])
            elif action == "diagnostic" and row is window.active_issue:
                window._diagnostic_action(payload.get("action", ""))
            return
    elif action == "inspect":
        window._validate()
    elif action == "publish" and window._review_selection():
        window._export()
    elif action == "switchAsset":
        window._switch_and_check()
    elif action == "selectAsset" and window.selection_note.get("canSelect"):
        window._select_review_asset()
    elif action == "rules":
        window._open_rules()
    elif action == "rescan" and window.active_issue and window._review_selection():
        window._recheck_mesh()
    elif (action in ("original", "vertices", "grow") and window.active_issue
          and window.active_issue["components"] and window._review_selection()):
        window._locate_active({"original": "source", "vertices": "vertices", "grow": "ring"}[action])
    elif action == "editDetailField":
        update_field(window, window.web.route, payload.get("name"), payload.get("value"))
    elif action == "backDetail":
        window.web.detail("")
    elif action == "toggleToast" and window.web.route == "preferences" and isinstance(payload.get("enabled"), bool):
        window._set_toast_enabled(payload["enabled"])
    elif action == "clearCache" and window.web.route == "preferences" and payload.get("confirmed") is True:
        window.web.cache = cache_state(window, clear=True)
        window._refresh_last_maya_log()
    elif action == "openCacheDirectory" and window.web.route == "preferences":
        from asset_forge.shared.workbench_cache import existing_cache_directory

        path = existing_cache_directory("maya", payload.get("id"), log_directory=window.logger.log_dir)
        url = window.skin.core.QUrl.fromLocalFile(path) if path else None
        if url is not None and window.skin.gui.QDesktopServices.openUrl(url):
            window.web.cache.pop("open_error", None)
        else:
            window.web.cache = dict(cache_state(window), open_error=True)
    elif action in _ABOUT_LINKS and window.web.route == "preferences":
        window.skin.gui.QDesktopServices.openUrl(window.skin.core.QUrl(_ABOUT_LINKS[action]))
    elif action in _DETAIL_ACTIONS and window.web.route in ("rules", "publish", "log"):
        getattr(window, _DETAIL_ACTIONS[action])()
    elif action in ("openOutputFolder", "openTextureFolder", "openPresetFolder"):
        window._open_folder({"openOutputFolder": "output", "openTextureFolder": "textures", "openPresetFolder": "preset"}[action])
    elif action == "textureSettings":
        window._open_textures()
    elif action == "chooseTextureFolder":
        window._choose_texture_folder()
    elif action == "followSceneTextures":
        window._follow_scene_textures()
    elif action == "scanTextures" and window._texture_folder():
        window._scan_texture_folder()
    elif action == "loadPreset":
        window._load_project_settings()
    elif action == "savePreset":
        window._save_project_settings()
    elif action == "chooseOutputFolder":
        window._choose_output_dir()
    elif action == "openPackage" and window.export_receipt and window.export_receipt["path"] == window.last_package_dir:
        window._open_last_package()
    elif action in ("settings", "log", "preferences"):
        window.web.detail("publish" if action == "settings" else action)
    elif action == "dock":
        window._switch_docking()
    elif action == "startDrag" and window.chrome:
        window.chrome.start_drag()
    elif action == "close":
        window._close()


def _windows_qt5_browser_slot(view, host, skin):
    # A render-to-texture child permanently switches its Qt5/Windows QWidget ancestors
    # to GL composition. Only a native child window belongs inside the Maya sidebar.
    qt = skin.core.Qt
    view.setWindowFlags(qt.Tool | qt.FramelessWindowHint)
    view.setAttribute(qt.WA_QuitOnClose, False)
    view.setAttribute(qt.WA_ShowWithoutActivating, True)
    # The container owns this foreign wrapper, never the QWidget's own QWindow.
    proxy = skin.gui.QWindow.fromWinId(int(view.winId()))
    if proxy is None:
        return None
    slot = skin.widgets.QWidget.createWindowContainer(proxy, host)
    slot.setObjectName("assetForgeBrowserSlot")
    slot.setFocusPolicy(qt.StrongFocus)
    return slot


def create(window, form, index_path):
    if not os.path.isfile(index_path):
        return None
    try:
        from PySide6 import QtCore, QtGui, QtWebChannel, QtWebEngineWidgets
        from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
    except ImportError:
        try:
            from PySide2 import QtCore, QtGui, QtWebChannel, QtWebEngineWidgets
            from PySide2.QtWebEngineWidgets import QWebEnginePage, QWebEngineSettings
        except ImportError:
            return None
    host = window.skin.widget(form)
    url = QtCore.QUrl.fromLocalFile(os.path.abspath(index_path))

    def new_view(parent):
        view = QtWebEngineWidgets.QWebEngineView(parent)
        view.setObjectName("assetForgeWebWorkbench")
        view.setContextMenuPolicy(QtCore.Qt.NoContextMenu)
        return view

    isolated = None
    slot = None
    if os.name == "nt" and QtCore.qVersion().startswith("5."):
        isolated = new_view(None)
        slot = _windows_qt5_browser_slot(isolated, host, window.skin)
        if slot is None:
            isolated.deleteLater()
            return None

    class LocalPage(QWebEnginePage):
        def acceptNavigationRequest(self, requested, kind, main_frame):
            return main_frame and requested == url

        def createWindow(self, kind):
            return None

    class Bridge(QtCore.QObject):
        stateChanged = QtCore.Signal(str)

        @QtCore.Slot(result=str)
        def getState(self):
            state = json.dumps(view_state(window), ensure_ascii=False)
            surface.ready = True
            surface.watchdog.stop()
            if surface.mode == "loading":
                surface.open_main.start(0)
            return state

        @QtCore.Slot(str, str)
        def dispatch(self, action, payload):
            try:
                data = json.loads(payload)
            except (TypeError, ValueError):
                return
            dispatch(window, action, data)
            surface.sync()

    class Surface(QtCore.QObject):
        def __init__(self):
            super(Surface, self).__init__(host)
            self.ready = False
            self.mode = "loading"
            self.route = ""
            self.cache = {}
            self.section = ""
            self.native_slot = slot
            self.view = isolated if slot is not None else new_view(host)
            if slot is not None:
                self.destroyed.connect(self.view.hide)
                self.destroyed.connect(self.view.deleteLater)
                window.skin.widgets.QApplication.instance().aboutToQuit.connect(self.view.hide)
            # The WebChannel page outlives the native render widget when a Maya tab moves.
            self.page = LocalPage(self)
            self.page.setBackgroundColor(QtGui.QColor(window.skin.theme["canvas"]))
            self.view.setPage(self.page)
            self.page.setZoomFactor(window.skin.scale)
            settings = self.page.settings()
            settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, False)
            settings.setAttribute(QWebEngineSettings.JavascriptCanOpenWindows, False)
            self.bridge = Bridge(self.page)
            self.channel = QtWebChannel.QWebChannel(self.page)
            self.channel.registerObject("workbench", self.bridge)
            self.page.setWebChannel(self.channel)
            self.update = QtCore.QTimer(self)
            self.update.setSingleShot(True)
            self.update.timeout.connect(self.send_state)
            self.open_main = QtCore.QTimer(self)
            self.open_main.setSingleShot(True)
            self.open_main.timeout.connect(self.main)
            self.watchdog = QtCore.QTimer(self)
            self.watchdog.setSingleShot(True)
            self.watchdog.timeout.connect(self.fallback)
            self.page.loadFinished.connect(self.loaded)
            self.page.renderProcessTerminated.connect(lambda *_: self.fallback())
            host.installEventFilter(self)

        @property
        def panel(self):
            return self.native_slot if self.native_slot is not None else self.view

        def fit(self):
            panel = self.panel
            panel.setGeometry(panel.parentWidget().rect())
            if self.native_slot is not None:
                self.view.resize(panel.size())

        def show_view(self):
            self.panel.show()
            self.view.show()
            self.panel.raise_()

        def hide_view(self):
            self.view.hide()
            if self.native_slot is not None:
                self.native_slot.hide()

        def rehost(self):
            # Chromium's Qt Quick render widget can retain the compositor of the old
            # top-level window. Reattach the live page after Maya commits the new host.
            if self.mode == "native":
                return
            if self.native_slot is not None:
                # QWindowContainer has reparented the isolated HWND, keeping the same page,
                # renderer and focus targets. No WebEngine object moves into a Maya QWidget.
                if self.mode in ("main", "loading"):
                    self.fit()
                    self.show_view()
                    self.sync()
                return
            old = self.view
            parent = old.parentWidget()
            view = new_view(parent)
            view.setGeometry(parent.rect())
            view.setPage(self.page)
            self.view = view
            old.hide()
            old.deleteLater()
            if self.mode in ("main", "loading"):
                view.show()
                view.raise_()
                view.update()
                self.sync()
            else:
                view.hide()

        def start(self):
            self.fit()
            self.show_view()
            self.watchdog.start(12000)
            self.view.load(url)

        def loaded(self, ok):
            if not ok:
                self.fallback()

        def fallback(self):
            self.ready = False
            self.watchdog.stop()
            self.open_main.stop()
            self.hide_view()
            window.cmds.scrollLayout(window.controls["main_scroll"], edit=True, manage=True)
            route = self.route
            self.mode = "native"
            self.route = ""
            window._detail_controls({"publish": "settings", "preferences": ""}.get(route, route))

        def sync(self):
            if self.ready and self.mode == "main" and not self.update.isActive():
                self.update.start(0)

        def send_state(self):
            if self.mode == "main":
                self.bridge.stateChanged.emit(json.dumps(view_state(window), ensure_ascii=False))

        def eventFilter(self, watched, event):
            if event.type() in (QtCore.QEvent.Resize, QtCore.QEvent.Show, QtCore.QEvent.ParentChange):
                if self.mode in ("main", "loading"):
                    self.fit()
                    self.panel.raise_()
                    self.sync()
            return False

        def detail(self, name):
            if not self.ready:
                window._detail_controls({"publish": "settings", "preferences": ""}.get(name, name))
                return
            route = "publish" if name == "textures" else name
            self.route = route
            self.section = "textures" if name == "textures" else ""
            if route == "preferences":
                self.cache = cache_state(window)
            self.sync()

        def main(self):
            if self.mode == "native":
                window._detail_controls("")
            if not self.ready:
                self.mode = "native"
                self.hide_view()
                return
            window.cmds.scrollLayout(window.controls["main_scroll"], edit=True, manage=False)
            self.mode = "main"
            self.fit()
            self.show_view()
            if window.chrome:
                window.chrome.schedule()
            self.sync()

    surface = Surface()
    return surface
