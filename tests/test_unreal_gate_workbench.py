"""Regression guards for staged confirmation in the native UE workbench."""

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from asset_forge.unreal import editor_menu, gate_handoff, gate_workbench
from asset_forge.unreal.acceptance_runner import UnrealPackageAcceptanceFlow
from asset_forge.unreal.manifest_reader import UnrealManifestReader


class GateWorkbenchTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.package = self.make_package("A")
        self.unreal = SimpleNamespace(
            Paths=SimpleNamespace(get_project_file_path=lambda: str(self.root / "A.uproject")),
            EditorAssetLibrary=Mock(),
        )
        self.unreal.EditorAssetLibrary.does_directory_exist.return_value = True
        self.unreal.EditorAssetLibrary.list_assets.return_value = ["/Game/Props/Existing.Existing"]
        self.flow = Mock()
        self.flow.run.side_effect = self.check_report
        self.flow.run_checked_import.return_value = {
            "status": "warning", "gate_passed": True, "run_import": True,
            "import": {"status": "success", "imported_assets": ["/Game/Props/A.A"]},
        }
        self.gate = gate_workbench.GateWorkbench(self.flow)

    def make_package(self, name):
        package = self.root / name
        package.mkdir()
        fbx = package / "A.fbx"
        texture = package / "T_A.png"
        profiles = package / "profiles.json"
        fbx.write_bytes(b"mesh")
        texture.write_bytes(b"skin")
        profiles.write_bytes(b"{}")
        manifest = {
            "asset_name": name, "fbx_path": str(fbx), "target_path": "/Game/Props", "mesh_count": 2,
            "textures": [{"package_path": str(texture), "copied": True}],
            "material_profiles_snapshot_path": "profiles.json",
        }
        (package / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return package

    def check_report(self, package, import_options, command_args):
        manifest_path = Path(package) / "manifest.json"
        manifest = json.loads(manifest_path.read_bytes())
        blocked = not Path(manifest["fbx_path"]).is_file()
        content = {key: {"enabled": import_options.get(key, True)}
                   for key in ("import_mesh", "import_textures", "import_materials")}
        acceptance = {"asset_name": manifest["asset_name"], "target_path": manifest["target_path"],
                      "manifest_validation": {"manifest": manifest}}
        acceptance["checks"] = [
            {"id": "package", "label": "导出资源", "status": "error", "messages": ["缺少 FBX 文件。"]}
        ] if blocked else [
            {"id": "engine_version_preflight", "label": "UE 版本", "status": "warning",
             "messages": ["包体没有声明 UE 目标版本。", "包体没有声明 UE 目标版本。"]}
        ]
        return {
            "status": "error" if blocked else "warning", "gate_passed": not blocked, "can_accept": not blocked,
            "report_path": str(Path(package) / "last_flow.json"), "source_manifest_path": str(manifest_path),
            "gate_import_options_override": import_options, "package_acceptance": acceptance,
            "dry_run": {
                "import_policy_summary": {"content_import_policy": content},
                "texture_import_plan": {"target_dir": "/Game/Props/Textures", "textures": [{"existing_texture_strategy": "reuse"}]},
                "material_binding_plan": {"target_dir": "/Game/Props/Materials", "materials": [{}]},
            },
            "timings_ms": {"package_validation": 15, "dry_run": 3},
        }

    def execute(self, action, path=None, options=None, token="", unreal=None):
        return self.gate.execute(action, str(path or self.package), options, token, unreal or self.unreal)

    def prepare_token(self, **kwargs):
        return self.execute("prepare", **kwargs)["confirmation"]["token"]

    def test_warm_prepare_uses_cached_preflight_and_fresh_target_query(self):
        checked = self.execute("check", options={"import_textures": False})
        self.assertFalse(checked["cache_hit"])
        self.assertIn("full_preflight", checked["timings_ms"])
        self.assertEqual(len(checked["operator_warnings"]), 1)
        self.unreal.EditorAssetLibrary.list_assets.assert_not_called()

        with patch.object(gate_workbench, "_binary_fingerprint", side_effect=AssertionError("rehashed warm input")):
            ready = self.execute("prepare", options={"import_textures": False})
        self.assertTrue(ready["cache_hit"])
        self.assertNotIn("full_preflight", ready["timings_ms"])
        self.assertIn("target_conflicts", ready["timings_ms"])
        self.flow.run.assert_called_once()
        self.flow.run_checked_import.assert_not_called()
        self.unreal.EditorAssetLibrary.list_assets.assert_called_once_with("/Game/Props", True, False)
        self.assertEqual(ready["report_path"], checked["report_path"])
        confirmation = ready["confirmation"]
        self.assertEqual((confirmation["mesh_count"], confirmation["texture_count"], confirmation["material_count"]), (2, 0, 1))
        self.assertEqual((confirmation["existing_count"], confirmation["error_count"], confirmation["warning_count"]), (1, 0, 1))
        self.assertEqual(confirmation["policy_summary"], "网格：同名覆盖 · 贴图：本次跳过 · 材质实例：同名复用")
        self.unreal.EditorAssetLibrary.list_assets.return_value = []
        ready_again = self.execute("prepare", options={"import_textures": False})
        self.flow.run.assert_called_once()
        self.assertEqual(ready_again["confirmation"]["existing_count"], 0)

    def test_check_stamp_invalidates_on_options_manifest_profile_and_binary_changes(self):
        self.execute("check", options={"combine_meshes": False})
        changed = self.execute("prepare", options={"combine_meshes": True})
        self.assertFalse(changed["cache_hit"])
        self.assertIn("full_preflight", changed["timings_ms"])
        for file in ("manifest.json", "profiles.json", "A.fbx", "T_A.png"):
            with self.subTest(file=file):
                path = self.package / file
                with path.open("ab") as stream:
                    stream.write(b" ")
                changed = self.execute("prepare", options={"combine_meshes": True})
                self.assertFalse(changed["cache_hit"])
        self.assertEqual(self.flow.run.call_count, 6)

    def test_missing_fbx_blocks_check_and_confirmation_without_import(self):
        (self.package / "A.fbx").unlink()
        report = self.execute("check")
        self.assertFalse(report["gate_passed"])
        self.assertFalse(report["can_import"])
        self.assertTrue(report["operator_errors"])
        ready = self.execute("prepare")
        self.assertTrue(ready["cache_hit"])
        self.assertNotIn("confirmation", ready)
        self.unreal.EditorAssetLibrary.list_assets.assert_not_called()
        self.flow.run_checked_import.assert_not_called()

    def test_confirmation_only_applies_once_and_only_to_its_package_project_and_options(self):
        token = self.prepare_token(options={"combine_meshes": True})
        another = self.make_package("B")
        self.assertFalse(self.execute("apply", path=another, token=token, options={"combine_meshes": True})["gate_passed"])
        other_project = SimpleNamespace(Paths=SimpleNamespace(get_project_file_path=lambda: str(self.root / "B.uproject")))
        self.assertFalse(self.execute("apply", token=token, unreal=other_project, options={"combine_meshes": True})["gate_passed"])
        self.assertFalse(self.execute("apply", token=token, options={"combine_meshes": False})["gate_passed"])
        self.flow.run_checked_import.assert_not_called()
        token = self.prepare_token(options={"combine_meshes": True})
        result = self.execute("apply", token=token, options={"combine_meshes": True})
        self.assertTrue(result["import_succeeded"])
        self.assertTrue(result["cache_hit"])
        self.assertIn("confirm_revalidation", result["timings_ms"])
        self.assertIn("write_and_verify", result["timings_ms"])
        self.flow.run_checked_import.assert_called_once()
        self.assertTrue(self.flow.run_checked_import.call_args.kwargs["project_file"].endswith("a.uproject")
                        or self.flow.run_checked_import.call_args.kwargs["project_file"].endswith("A.uproject"))
        self.assertFalse(self.execute("apply", token=token, options={"combine_meshes": True})["gate_passed"])
        self.flow.run_checked_import.assert_called_once()

    def test_apply_rejects_digest_change_even_if_fast_file_identity_is_preserved(self):
        with patch.object(gate_workbench, "_stat_identity", return_value=(4, 2, 2, 1, 0)):
            token = self.prepare_token()
            (self.package / "A.fbx").write_bytes(b"edit")
            result = self.execute("apply", token=token)
        self.assertFalse(result["gate_passed"])
        self.assertFalse(result["can_accept"])
        self.assertEqual(result["decision"], "blocked")
        self.assertIn("内容已变化", result["message"])
        self.flow.run_checked_import.assert_not_called()

    def test_apply_rejects_changed_target_registry(self):
        token = self.prepare_token()
        self.unreal.EditorAssetLibrary.list_assets.return_value = ["/Game/Props/New.New"]
        result = self.execute("apply", token=token)
        self.assertFalse(result["can_import"])
        self.assertIn("目标路径", result["message"])
        self.flow.run_checked_import.assert_not_called()

    def test_native_editor_entry_logs_timings_without_modal(self):
        with patch.object(editor_menu, "_NATIVE_GATE", self.gate), \
             patch.object(editor_menu, "_notify_user", side_effect=AssertionError("Modal called")), \
             patch.object(editor_menu, "_log_operation") as log:
            first = editor_menu.workbench_check_package(self.package, unreal_module=self.unreal)
            ready = editor_menu.workbench_prepare_package(self.package, unreal_module=self.unreal)
            imported = editor_menu.workbench_apply_package(self.package, confirmation_token=ready["confirmation"]["token"],
                                                           unreal_module=self.unreal)
        self.assertFalse(first["import_succeeded"])
        self.assertTrue(imported["import_succeeded"])
        self.assertEqual(log.call_count, 3)
        self.assertIn("write_and_verify", log.call_args.kwargs["outputs"]["timings_ms"])

    def test_operator_warnings_include_specific_missing_plugin_assets_and_shader_work(self):
        payload = {"checks": [
            {"id": "plugin_content", "label": "UE 插件内容", "status": "warning",
             "messages": ["缺少插件资产"] * 3},
            {"id": "material_assets", "label": "默认材质资产", "status": "warning"},
            {"id": "material_graph_evidence", "label": "材质证据", "status": "warning"},
        ], "plugin_content_validation": {"missing_assets": ["/AssetForge/T_A", "/AssetForge/T_B", "/AssetForge/T_C"]},
            "material_asset_validation": {"missing_assets": ["/AssetForge/M_Default"], "missing_count": 1},
            "material_graph_evidence_report": {"checks": [{"id": "slot_binding", "status": "warning"}]}}
        warnings = gate_workbench._operator_messages({"package_acceptance": payload,
                   "warnings": [{"source": "plugin_content", "message": "缺少插件资产"}]}, "warnings")
        self.assertEqual(len(warnings), 3)
        self.assertIn("3 项", warnings[0])
        self.assertIn("T_A、T_B", warnings[0])
        self.assertIn("M_Default", warnings[1])
        self.assertIn("网格材质槽", warnings[2])

    def test_only_identical_missing_preview_inventories_share_one_operator_warning(self):
        common = ["/AssetForge/Textures/T_AF_Preview_A", "/AssetForge/Materials/MI_AF_Props_Preview"]
        acceptance = {
            "checks": [{"id": kind, "status": "warning"} for kind in ("plugin_content", "material_assets")],
            "plugin_content_validation": {"missing_assets": common, "missing_count": 2},
            "material_asset_validation": {"missing_assets": list(reversed(common)), "missing_count": 2},
        }
        flow = {"package_acceptance": acceptance, "warnings": [
            {"source": kind, "message": "缺少预览贴图"} for kind in ("plugin_content", "material_assets")]}
        warnings = gate_workbench._operator_messages(flow, "warnings")
        self.assertEqual(len(warnings), 1)
        self.assertIn("UE 插件预览与示例资源", warnings[0])
        self.assertIn("缺少 2 项", warnings[0])
        self.assertEqual(len(flow["warnings"]), 2)
        for other in ([common[0]], [common[0], "/AssetForge/Materials/M_Master"]):
            acceptance["material_asset_validation"] = {"missing_assets": other, "missing_count": len(other)}
            self.assertEqual(len(gate_workbench._operator_messages(flow, "warnings")), 2)

    def test_live_legacy_and_standalone_notices_share_chinese_formatter(self):
        checks = [
            {"id": "material_graph_evidence", "label": "Material Graph Evidence", "status": "warning",
             "messages": ["Material Graph Evidence is incomplete."]},
            {"id": "release_dependency_audit", "label": "Release Dependency Audit", "status": "warning",
             "messages": ["Release Dependency Audit: AssetForge dependency."]},
        ]
        raw = self.check_report(self.package, {}, ())
        raw["package_acceptance"]["checks"] = checks
        raw["package_acceptance"]["material_graph_evidence_report"] = {
            "checks": [{"id": "slot_binding", "status": "warning"}],
        }
        raw["warnings"] = [
            {"source": "static_mesh_import_policy",
             "message": "build_reversed_index_buffer 策略已记录为 disable，当前阶段按 report-only 处理。"},
        ]
        report_path = self.package / "last_flow.json"
        report_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        original_bytes = report_path.read_bytes()
        self.flow.run.side_effect = None
        self.flow.run.return_value = raw
        live = self.execute("check")["operator_warnings"]
        with patch.object(editor_menu, "_NATIVE_GATE", None):
            legacy = editor_menu.workbench_read_reports(self.package, report_path=report_path, unreal_module=self.unreal)
        self.assertEqual(legacy["operator_warnings"], live)
        self.assertEqual(legacy["operator_errors"], [])
        self.assertEqual(legacy["handoff_receipt"], {})
        legacy_visible = "\n".join(live)
        for wanted in ("材质图验证", "网格材质槽", "交付依赖", "反向索引缓冲区设为关闭", "仅记录"):
            self.assertIn(wanted, legacy_visible)
        for internal in ("Material Graph Evidence", "Release Dependency Audit", "build_reversed_index_buffer",
                         "disable", "report-only"):
            self.assertNotIn(internal, legacy_visible)
            self.assertIn(internal.encode(), original_bytes)
        self.assertEqual(report_path.read_bytes(), original_bytes)
        self.assertEqual(gate_workbench._operator_messages(raw["package_acceptance"], "warnings"), live[:2])

    def test_named_required_slot_removes_only_duplicate_coverage_summary(self):
        warning = "材质实例 MI_QiangTuo 的 ARM 槽缺少包内交付贴图。"
        checks = [
            {"id": "material_profile", "status": "warning", "messages": ["缺少必需贴图：packed_arm"]},
            {"id": "texture_quality", "status": "warning",
             "messages": ["缺少必需贴图数量：packed_arm", "有额外贴图需要核对。"]},
        ]
        validation = {"checks": [
            {"id": "required_texture_parameter_missing", "status": "warning",
             "material_name": "QiangTuo", "parameter": "ARM", "usage": "packed_arm", "message": warning},
        ]}
        report = {"checks": checks, "material_texture_binding_validation": validation}

        lines = gate_workbench._operator_messages(report, "warnings")
        self.assertEqual(lines, ["必需贴图槽：" + warning, "贴图质量：有额外贴图需要核对。"])
        historical_lines = gate_workbench._operator_messages({"checks": checks}, "warnings")
        self.assertIn("ARM/ORM 打包贴图", "\n".join(historical_lines))
        self.assertNotIn("packed_arm", "\n".join(historical_lines))

    def confirmed_import_report(self):
        manifest_path = self.package / "manifest.json"
        prepared = UnrealManifestReader().load(manifest_path, require_fbx_exists=False)["manifest"]
        target = prepared["target_path"]
        return {
            "stage": "package_acceptance_flow", "status": "warning", "gate_passed": True, "run_import": True,
            "workbench_project_file": self.unreal.Paths.get_project_file_path(),
            "package_dir": str(self.package), "source_manifest_path": str(manifest_path),
            "package_acceptance": {"target_path": target, "manifest_validation": {"manifest": prepared}},
            "import": {"status": "success", "target_path": target,
                       "imported_assets": [target + "/A.A", target + "/T_B.T_B", "/Game/Other/Foreign.Foreign"],
                       "review_policy": {"material_profile": "pbr_metal_rough"}},
            "post_import_validation": {"status": "pass", "can_accept": True},
        }

    def setup_handoff_registry(self):
        self.registry = Mock()
        self.registry.get_assets_by_package_name.side_effect = lambda path, _: {
            "/Game/Props/A": [SimpleNamespace(asset_name="A", asset_class_path=SimpleNamespace(asset_name="StaticMesh"))],
            "/Game/Props/T_B": [SimpleNamespace(asset_name="T_B", asset_class_path=SimpleNamespace(asset_name="Texture2D"))],
        }.get(path, [])
        self.unreal.AssetRegistryHelpers = SimpleNamespace(get_asset_registry=lambda: self.registry)
        self.flow._default_report_path.return_value = str(self.package / "last_flow.json")
        # Simulate only the editor's project identity and per-project storage in this offline test.
        override = patch.object(gate_handoff, "handoff_path",
                                side_effect=lambda package, project: self.root / (Path(project).stem + ".json") if project else None)
        override.start()
        self.addCleanup(override.stop)
        self.addCleanup(self.gate.checked.clear)

    def test_written_handoff_survives_new_check_and_new_workbench(self):
        self.setup_handoff_registry()
        manifest_path = self.package / "manifest.json"
        manifest = json.loads(manifest_path.read_bytes())
        manifest["asset_budgets"] = {"triangles": 250000, "material_slots": 8}
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        import_report = self.confirmed_import_report()
        import_report["import"].update(imported_textures=["/Game/Props/Textures/T_B.T_B", "/Game/Props/Textures/T_B"],
                                       created_material_instances=["/Game/Props/Materials/MI_A"])
        self.flow.run_checked_import.return_value = import_report
        with patch.object(gate_workbench, "handoff_path", gate_handoff.handoff_path):
            token = self.prepare_token()
            imported = self.execute("apply", token=token)
            receipt = imported["handoff_receipt"]
            self.assertTrue(imported["import_succeeded"])
            self.assertEqual(receipt["meshes"], ["/Game/Props/A.A"])
            self.assertEqual(receipt["policy"], {"material_profile": "pbr_metal_rough"})
            self.assertEqual(receipt["asset_budgets"], {"triangles": 250000, "material_slots": 8})
            self.assertEqual(receipt["result_counts"], {"mesh_count": 1, "texture_count": 1, "material_count": 1})
            self.assertTrue(receipt["receipt"])
            self.assertEqual(receipt, json.loads(gate_handoff.handoff_path(
                self.package, self.unreal.Paths.get_project_file_path()).read_bytes()))

            (self.package / "last_flow.json").write_text("{}", encoding="utf-8")
            checked = self.execute("check")
            self.assertEqual(checked["handoff_receipt"], receipt)
            self.assertFalse(checked["import_succeeded"])
            self.registry.get_assets_by_package_name.reset_mock()
            self.assertNotIn("handoff_receipt", self.execute("prepare"))
            self.registry.get_assets_by_package_name.assert_not_called()

        reopened = gate_workbench.GateWorkbench(self.flow)
        report = reopened.read_reports(self.package, unreal_module=self.unreal)
        self.assertEqual(report["handoff_receipt"], receipt)
        other_project = SimpleNamespace(Paths=SimpleNamespace(get_project_file_path=lambda: str(self.root / "B.uproject")))
        self.assertEqual(reopened.read_reports(self.package, unreal_module=other_project)["handoff_receipt"], {})
        self.registry.get_assets_by_package_name.side_effect = lambda *_: []
        self.assertEqual(reopened.read_reports(self.package, unreal_module=self.unreal)["handoff_receipt"], {})
        self.registry.get_assets_by_package_name.side_effect = AssertionError("stale receipt should not query assets")
        (self.package / "manifest.json").write_text("{}", encoding="utf-8")
        self.assertEqual(reopened.read_reports(self.package, unreal_module=self.unreal)["handoff_receipt"], {})

    def test_legacy_handoff_migrates_only_from_verified_current_project_import(self):
        self.setup_handoff_registry()
        report_path = self.package / "last_flow.json"
        report = self.confirmed_import_report()
        for change in ({"workbench_project_file": str(self.root / "Unrelated.uproject")},
                       {"run_import": False}, {"post_import_validation": {"can_accept": False}}):
            with self.subTest(change=change):
                report_path.write_text(json.dumps(dict(report, **change)), encoding="utf-8")
                self.assertEqual(self.gate.read_reports(self.package, unreal_module=self.unreal)["handoff_receipt"], {})
        report_path.write_text(json.dumps(report), encoding="utf-8")
        other_path = self.root / "outside.json"
        other_path.write_text(json.dumps(report), encoding="utf-8")
        self.assertEqual(self.gate.read_reports(self.package, report_path=other_path,
                                              unreal_module=self.unreal)["handoff_receipt"], {})
        receipt = self.gate.read_reports(self.package, report_path=report_path,
                                        unreal_module=self.unreal)["handoff_receipt"]
        self.assertEqual(receipt["meshes"], ["/Game/Props/A.A"])
        self.assertEqual(self.gate.read_reports(self.package, unreal_module=self.unreal)["handoff_receipt"], receipt)
        gate_handoff.invalidate_handoff(self.package, self.unreal.Paths.get_project_file_path())
        self.assertEqual(self.gate.read_reports(self.package, unreal_module=self.unreal)["handoff_receipt"], {})

    def test_checked_write_runner_does_not_repeat_package_or_plan_checks(self):
        pipeline = Mock()
        pipeline.import_from_manifest.return_value = {
            "status": "success", "imported_assets": ["/Game/Props/A.A"],
            "post_import_validation": {"status": "pass", "can_accept": True},
        }
        validator = Mock()
        flow = UnrealPackageAcceptanceFlow(validator, pipeline)
        manifest_path = str(self.package / "manifest.json")
        check = {
            "gate_passed": True, "gate_import_options_override": {}, "source_manifest_path": manifest_path,
            "package_acceptance": {"summary": {"can_accept": True}, "manifest_path": manifest_path, "asset_name": "A"},
            "dry_run": {"status": "skipped", "summary": {"can_accept": True}},
        }
        report = flow.run_checked_import(str(self.package), check, {}, project_file="A.uproject")
        self.assertTrue(report["gate_passed"])
        self.assertEqual(report["workbench_project_file"], "A.uproject")
        self.assertEqual(json.loads(Path(report["report_path"]).read_bytes())["workbench_project_file"], "A.uproject")
        validator.validate.assert_not_called()
        pipeline.dry_run_manifest.assert_not_called()
        pipeline.import_from_manifest.assert_called_once_with(manifest_path)
