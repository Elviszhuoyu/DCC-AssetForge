import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from asset_forge.maya import ui, web_workbench, workbench_frame


class MayaWebWorkbenchTest(unittest.TestCase):
    def setUp(self):
        self.row = dict(rule="ambiguous_material_texture_set", kind="", label="材质贴图绑定",
                        severity="error", mesh="", object="M_CineCamera_Body_Trim", components=[],
                        candidates=["CineCamera_Body", "CineCamera_Trim"])
        self.window = SimpleNamespace(issue_revision=3, issue_rows=[self.row], active_issue=None,
                                      requested_visibility={}, review_gate=None, cmds=Mock(), check_notice={}, action_button={},
                                      _validate=Mock(), _export=Mock(), _binding_callback=Mock(), _tool_state=Mock(return_value={}),
                                      _row_callback=Mock(), _locate_active=Mock(), _recheck_mesh=Mock(),
                                      selection_note={}, last_validation=None, _passed_checks=Mock(return_value=[]))
        self.window._review_selection = lambda: self.window.cmds.ls(selection=True)

    def test_floating_workspace_reflows_a_stale_native_tab_offset(self):
        dock = Mock()
        bounds = (0, 0, 265, 486)
        dock.geometry.return_value = (0, 20, 265, 486)
        stack = dock.parentWidget.return_value
        stack.inherits.return_value = True
        stack.currentWidget.return_value = dock
        stack.contentsRect.return_value = bounds
        workbench_frame._fit_tab_page(dock)
        stack.layout.return_value.setGeometry.assert_called_once_with(bounds)

        stack.layout.return_value.setGeometry.reset_mock()
        dock.geometry.return_value = bounds
        workbench_frame._fit_tab_page(dock)
        dock.geometry.return_value = (0, 20, 265, 486)
        stack.currentWidget.return_value = Mock()
        workbench_frame._fit_tab_page(dock)
        stack.layout.return_value.setGeometry.assert_not_called()

    def test_qt5_sidebar_owns_only_the_foreign_window_wrapper(self):
        qt = SimpleNamespace(Tool=1, FramelessWindowHint=2, WA_QuitOnClose=3,
                             WA_ShowWithoutActivating=4, StrongFocus=5)
        skin = SimpleNamespace(core=SimpleNamespace(Qt=qt), gui=Mock(), widgets=Mock())
        browser, host, proxy = Mock(), Mock(), Mock()
        browser.winId.return_value = 17
        skin.gui.QWindow.fromWinId.return_value = proxy
        slot = web_workbench._windows_qt5_browser_slot(browser, host, skin)
        skin.gui.QWindow.fromWinId.assert_called_once_with(17)
        skin.widgets.QWidget.createWindowContainer.assert_called_once_with(proxy, host)
        self.assertIs(slot, skin.widgets.QWidget.createWindowContainer.return_value)
        browser.setParent.assert_not_called()
        browser.windowHandle.assert_not_called()
        skin.gui.QWindow.fromWinId.return_value = None
        skin.widgets.QWidget.createWindowContainer.reset_mock()
        self.assertIsNone(web_workbench._windows_qt5_browser_slot(browser, host, skin))
        skin.widgets.QWidget.createWindowContainer.assert_not_called()

    def test_only_current_report_rows_and_offered_candidates_can_bind(self):
        send = lambda key, value: web_workbench.dispatch(self.window, "chooseCandidate", {"id": key, "value": value})
        send("2:0", "CineCamera_Body")
        send("3:0", "unlisted")
        self.window._binding_callback.assert_not_called()
        send("3:0", "CineCamera_Trim")
        self.window._binding_callback.assert_called_once_with(self.row)
        self.window._binding_callback.return_value.assert_called_once_with("CineCamera_Trim")

    def test_selected_asset_can_attempt_preflight_with_or_without_previous_clearance(self):
        self.window.cmds.ls.return_value = []
        web_workbench.dispatch(self.window, "publish", {})
        self.window._export.assert_not_called()
        self.window.cmds.ls.return_value = ["|SM_B"]
        for gate in (None, False, True):
            self.window.review_gate = gate
            web_workbench.dispatch(self.window, "publish", {})
        self.assertEqual(self.window._export.call_count, 3)

    def test_component_actions_require_real_components(self):
        web_workbench.dispatch(self.window, "grow", {})
        self.window._locate_active.assert_not_called()
        self.window.active_issue = dict(mesh="mesh", components=[4])
        web_workbench.dispatch(self.window, "grow", {})
        self.window._locate_active.assert_called_once_with("ring")

    def test_dispatch_does_not_traverse_object_methods(self):
        web_workbench.dispatch(self.window, "_export", {})
        web_workbench.dispatch(self.window, "inspect", [])
        self.window._export.assert_not_called()
        self.window._validate.assert_not_called()
        web_workbench.dispatch(self.window, "inspect", {})
        self.window._validate.assert_called_once_with()

    def test_texture_group_uses_the_selected_directory_and_original_scanner(self):
        self.window._choose_texture_folder = Mock()
        self.window._scan_texture_folder = Mock()
        self.window._texture_folder = Mock(return_value="")
        web_workbench.dispatch(self.window, "scanTextures", {})
        self.window._scan_texture_folder.assert_not_called()
        web_workbench.dispatch(self.window, "chooseTextureFolder", {})
        self.window._choose_texture_folder.assert_called_once_with()
        self.window._texture_folder.return_value = "selected-folder"
        web_workbench.dispatch(self.window, "scanTextures", {})
        self.window._scan_texture_folder.assert_called_once_with()

    def test_detail_page_field_updates_only_whitelisted_controls_and_invalidates(self):
        self.window.web = SimpleNamespace(route="rules")
        self.window.controls = {"name_prefix": "meshNamePrefix", "platform": "targetPlatform"}
        self.window._review_inputs_edited = Mock()
        self.window._change_rule_platform = Mock()
        self.window.cmds.textFieldGrp.return_value = "SM_"
        self.window.cmds.optionMenu.side_effect = lambda _, **flags: (
            ["item1", "item2"] if flags.get("itemListLong") else "pc")
        self.window.cmds.menuItem.side_effect = lambda item, **_: {"item1": "pc", "item2": "mobile"}[item]
        send = lambda name, value: web_workbench.dispatch(self.window, "editDetailField", {"name": name, "value": value})
        send("_arbitrary_setting", "Other")
        self.window.cmds.textFieldGrp.assert_not_called()
        send("name_prefix", "PR_")
        self.window.cmds.textFieldGrp.assert_called_with("meshNamePrefix", edit=True, text="PR_")
        self.window._review_inputs_edited.assert_called_once_with()
        send("platform", "unlisted")
        self.window._change_rule_platform.assert_not_called()
        send("platform", "mobile")
        self.window.cmds.optionMenu.assert_called_with("targetPlatform", edit=True, value="mobile")
        self.window._change_rule_platform.assert_called_once_with("mobile")

    def test_preferences_display_current_maya_update_from_api_version(self):
        self.window.toast_enabled = True
        for version, api, expected in (
            ("2024", 20240200, "2024.2"), ("2025", 20250000, "2025"),
            ("2026.3", None, "2026.3"), ("2024", 20260200, "2024"),
            ("2024", RuntimeError("API number unavailable"), "2024"),
        ):
            with self.subTest(version=version, api=api):
                self.window.cmds.about.side_effect = [version, api]
                state = web_workbench.detail_state(self.window, "preferences", {})
                self.assertEqual(state["hostVersion"], expected)

    def test_preferences_load_license_and_allow_only_public_about_links(self):
        self.window.toast_enabled = True
        self.window.web = SimpleNamespace(route="preferences")
        self.window.skin = SimpleNamespace(gui=Mock(), core=SimpleNamespace(QUrl=lambda value: value))
        state = web_workbench.detail_state(self.window, "preferences", {})
        license_path = Path(__file__).resolve().parents[1] / "LICENSE"
        self.assertEqual(state["licenseName"], license_path.read_text(encoding="utf-8").splitlines()[0])

        expected = (
            ("openReleases", "https://github.com/Elviszhuoyu/DCC-AssetForge/releases"),
            ("openProjectHome", "https://github.com/Elviszhuoyu/DCC-AssetForge"),
            ("openAuthorHome", "https://work.zhuoyulabs.com"),
        )
        opener = self.window.skin.gui.QDesktopServices.openUrl
        for action, destination in expected:
            web_workbench.dispatch(self.window, action, {"url": "https://example.invalid"})
            opener.assert_called_with(destination)
        self.window.web.route = "publish"
        web_workbench.dispatch(self.window, "openAuthorHome", {})
        self.assertEqual(opener.call_count, len(expected))

    def test_preferences_cleanup_requires_explicit_confirmation(self):
        self.window.web = SimpleNamespace(route="preferences")
        self.window._set_toast_enabled = Mock()
        self.window._refresh_last_maya_log = Mock()
        with patch.object(web_workbench, "cache_state", return_value={"removed_files": 2}) as clear:
            web_workbench.dispatch(self.window, "clearCache", {})
            web_workbench.dispatch(self.window, "clearCache", {"confirmed": "true"})
            clear.assert_not_called()
            web_workbench.dispatch(self.window, "clearCache", {"confirmed": True})
            clear.assert_called_once_with(self.window, clear=True)
        self.window._refresh_last_maya_log.assert_called_once_with()
        self.assertEqual(self.window.web.cache, {"removed_files": 2})
        web_workbench.dispatch(self.window, "toggleToast", {"enabled": False})
        self.window._set_toast_enabled.assert_called_once_with(False)

    def test_shelf_updates_legacy_empty_workspace_in_place(self):
        cmds = Mock()
        cmds.workspaceControl.return_value = True
        cmds.lsUI.return_value = ["MayaWindow|nativeDock|someForm"]
        window = SimpleNamespace(cmds=cmds)
        with patch.object(ui, "_WORKSPACE_INSTANCE", None):
            result = ui.AssetForgeMayaWindow.show(window)
            self.assertIs(ui._WORKSPACE_INSTANCE, window)
        self.assertEqual(result, ui.WORKSPACE_NAME)
        register = cmds.workspaceControl.call_args_list[1]
        self.assertTrue(register.kwargs["edit"])
        self.assertIn("restore_saved_workspace", register.kwargs["uiScript"])
        cmds.workspaceControl.assert_called_with(ui.WORKSPACE_NAME, edit=True, restore=True)
        cmds.evalDeferred.assert_called_once_with(ui.restore_workspace, lowestPriority=True)
        cmds.deleteUI.assert_not_called()

    def test_shelf_preserves_live_reload_with_owned_ui_content(self):
        cmds = Mock()
        cmds.workspaceControl.return_value = True
        cmds.window.return_value = False
        cmds.lsUI.return_value = ["MayaWindow|dock|" + ui.WORKSPACE_NAME + "|formLayout1"]
        with patch.object(ui, "_WORKSPACE_INSTANCE", None):
            ui.AssetForgeMayaWindow.show(SimpleNamespace(cmds=cmds))
        cmds.deleteUI.assert_called_once_with(ui.WORKSPACE_NAME)
        edited = [entry.kwargs["uiScript"] for entry in cmds.workspaceControl.call_args_list
                  if entry.kwargs.get("edit") and "uiScript" in entry.kwargs]
        self.assertEqual(len(edited), 2)
        self.assertEqual(edited[0], edited[1])

    def _legacy_workspace_fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "workspaces" / "General.json"
        path.parent.mkdir()
        old = 'python("from asset_forge.maya import ui; ui.restore_workspace()");'
        definition = {"panels": [{"controls": [
            {"objectName": ui.WORKSPACE_NAME, "title": "资产工作台", "uiScript": old}
        ]}]}
        payload = json.dumps(definition, ensure_ascii=False).encode("gb18030")
        path.write_bytes(payload)
        cmds = Mock()
        cmds.internalVar.return_value = temporary.name
        cmds.optionVar.return_value = True
        cmds.workspaceLayoutManager.return_value = "General"
        return cmds, path, payload

    def test_legacy_layout_is_backed_up_before_maya_saves_it_once(self):
        cmds, path, payload = self._legacy_workspace_fixture()
        window = SimpleNamespace(cmds=cmds, workspace_populated=True)
        migration = ui._saved_workspace_migration(cmds)
        self.assertEqual(migration, ("General", str(path), payload))

        def native_write(**flags):
            if flags.get("query"):
                return "General"
            backups = list(path.parent.glob("*.assetforge-before-restore-*.bak"))
            self.assertEqual([backup.read_bytes() for backup in backups], [payload])
            self.assertEqual(path.read_bytes(), payload)
            path.write_text('{"controls":[]}', encoding="utf-8")

        cmds.workspaceLayoutManager.side_effect = native_write
        with patch.object(ui, "_WORKSPACE_INSTANCE", window), patch.object(ui, "restore_workspace") as restore:
            ui._schedule_workspace_restore(window, migration)
            deferred = cmds.evalDeferred.call_args.args[0]
            deferred()
            deferred()
            self.assertEqual(restore.call_count, 2)
        writes = [entry for entry in cmds.workspaceLayoutManager.call_args_list if entry.kwargs.get("save")]
        self.assertEqual(len(writes), 1)
        self.assertIsNone(ui._saved_workspace_migration(cmds))

    def test_legacy_layout_skips_native_save_after_switch_or_autosave_off(self):
        cmds, path, payload = self._legacy_workspace_fixture()
        migration = ui._saved_workspace_migration(cmds)
        window = SimpleNamespace(cmds=cmds, workspace_populated=True)
        with patch.object(ui, "_WORKSPACE_INSTANCE", window), patch.object(ui, "restore_workspace"):
            ui._schedule_workspace_restore(window, migration)
            deferred = cmds.evalDeferred.call_args.args[0]
            cmds.workspaceLayoutManager.return_value = "Maya Classic"
            deferred()
            cmds.workspaceLayoutManager.return_value = "General"
            cmds.optionVar.return_value = False
            deferred()
        self.assertIsNone(ui._saved_workspace_migration(cmds))
        self.assertEqual(list(path.parent.glob("*.bak")), [])
        self.assertEqual(path.read_bytes(), payload)
        self.assertFalse(any(entry.kwargs.get("save") for entry in cmds.workspaceLayoutManager.call_args_list))

    def test_saved_workbench_restores_when_idle_and_populates_once(self):
        cmds = Mock()
        cmds.workspaceControl.return_value = False
        window = Mock(workspace_populated=False, controls={"main_scroll": "originalScroll"})
        window._populate.side_effect = lambda _: setattr(window, "workspace_populated", True)
        recreated = Mock(workspace_populated=False, controls={"main_scroll": "recreatedScroll"})
        recreated._populate.side_effect = lambda _: setattr(recreated, "workspace_populated", True)
        with patch.object(ui, "get_cmds", return_value=cmds), patch.object(ui, "_WORKSPACE_INSTANCE", None), \
                patch.object(ui, "AssetForgeMayaWindow", side_effect=[window, recreated]) as build:
            ui.defer_workspace_restore()
            cmds.evalDeferred.assert_called_once_with(ui.restore_workspace, lowestPriority=True)
            callback = cmds.evalDeferred.call_args.args[0]
            callback()
            build.assert_not_called()
            cmds.workspaceControl.return_value = True
            cmds.scrollLayout.return_value = True
            callback()
            callback()
            build.assert_called_once_with(cmds_module=cmds)
            window._populate.assert_called_once_with(ui.WORKSPACE_NAME)
            cmds.scrollLayout.side_effect = lambda control, **_: control == "recreatedScroll"
            callback()
            callback()
            self.assertEqual(build.call_count, 2)
            recreated._populate.assert_called_once_with(ui.WORKSPACE_NAME)

    def test_locator_feedback_is_scoped_to_the_selected_component_card(self):
        self.window.controls = {"current_asset": "asset"}
        self.window.review_status = ("warning", "1 个警告")
        self.window.review_message = "local recheck completed"
        self.window.workspace_name = "workspace"
        self.window.material_texture_set_overrides = {}
        self.window.cmds = Mock()
        self.window.cmds.text.return_value = "SM_Crate"
        self.window.cmds.ls.return_value = ["|SM_Crate"]
        self.row["message"] = "材质有两个候选集。"
        state = web_workbench.view_state(self.window)
        self.assertFalse(state["canPublish"])
        self.assertTrue(state["canAttemptPublish"])
        self.assertFalse(state["issues"][0]["isGeometry"])
        self.assertEqual(state["issues"][0]["countText"], "2 候选")
        self.assertEqual(state["issues"][0]["detail"], "M_CineCamera_Body_Trim\n材质有两个候选集。")
        component = dict(self.row, mesh="|root|meshShape", object="|root|meshShape",
                         kind="e", components=[17], candidates=[], message="两个端点重合",
                         location_feedback="已选中 1 条原始边")
        self.window.issue_rows = [component]
        self.window.active_issue = component
        located = web_workbench.view_state(self.window)
        issue = located["issues"][0]
        self.assertTrue(issue["isGeometry"] and issue["canLocate"])
        self.assertEqual(issue["objectName"], "meshShape")
        self.assertEqual(issue["detail"], "|root|meshShape\n两个端点重合")
        self.assertEqual(issue["countText"], "1 边")
        self.assertEqual(located["feedback"], "已选中 1 条原始边")
        self.assertTrue(located["canLocate"])
        self.window.active_issue = None
        self.assertEqual(web_workbench.view_state(self.window)["feedback"], "")
        self.assertFalse(state["canLocate"])
        self.assertEqual([c["value"] for c in state["candidates"][0]["options"]], self.row["candidates"])
