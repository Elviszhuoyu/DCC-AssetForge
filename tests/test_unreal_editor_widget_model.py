# -*- coding: utf-8 -*-

from __future__ import absolute_import

import json
import os
import shutil
import tempfile
import unittest

from asset_forge.unreal.editor_widget_model import build_gate_panel_state, build_package_summary, discover_package_history, preview_package_gate


class UnrealEditorWidgetModelTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_discovers_latest_and_history_from_maya_log_and_export_root(self):
        old_package = self._write_package("SM_Old", mtime=10)
        new_package = self._write_package("SM_New", mtime=20)
        log_path = os.path.join(self.temp_dir, "latest_maya.log")
        with open(log_path, "w", encoding="utf-8") as stream:
            stream.write(json.dumps({"operation": "export_success", "outputs": {"package_dir": old_package}}) + "\n")
            stream.write(json.dumps({"operation": "export_success", "outputs": {"package_dir": new_package}}) + "\n")

        history = discover_package_history(self.temp_dir, log_path, "__missing_unreal__", limit=10)

        self.assertEqual(history["status"], "ready")
        self.assertEqual(history["latest_package_dir"], new_package.replace("\\", "/"))
        self.assertEqual(history["package_count"], 2)
        self.assertEqual(history["packages"][0]["asset_name"], "SM_New")

    def test_scans_multiple_export_roots_for_manifest_packages(self):
        root_a = os.path.join(self.temp_dir, "RootA")
        root_b = os.path.join(self.temp_dir, "RootB")
        os.makedirs(root_a)
        os.makedirs(root_b)
        package_a = self._write_package("SM_A", mtime=10, root=root_a)
        package_b = self._write_package("SM_B", mtime=30, root=root_b)

        history = discover_package_history([root_a, root_b], "__missing_maya__", "__missing_unreal__", limit=10)

        self.assertEqual(history["status"], "ready")
        self.assertEqual(history["latest_package_dir"], package_b.replace("\\", "/"))
        self.assertEqual(history["package_count"], 2)
        self.assertEqual(history["packages"][0]["source_dcc_label"], "Maya")
        self.assertEqual(history["packages"][0]["schema_version"], "0.2")
        self.assertEqual(history["packages"][1]["package_dir"], package_a.replace("\\", "/"))

    def test_empty_history_returns_chinese_empty_state(self):
        history = discover_package_history(os.path.join(self.temp_dir, "Missing"), "__missing_maya__", "__missing_unreal__", limit=10)

        self.assertEqual(history["status"], "empty")
        self.assertEqual(history["package_count"], 0)
        self.assertEqual(history["status_label"], "暂无可审包体")
        self.assertIn("还没有发现", history["empty_title"])

    def test_build_package_summary_exposes_counts_and_gate(self):
        package_dir = self._write_package("SM_Crate", mtime=10)
        report = {
            "status": "warning",
            "summary": {
                "can_accept": True,
                "warning_count": 1,
                "error_count": 0,
                "warnings": [{"message": "Check texture group in UE."}],
                "errors": [],
                "warning_checks": ["texture_quality"],
                "blocking_checks": [],
                "next_action": "Review warnings, then import.",
            },
            "import_strategy_summary": {
                "existing_mesh_strategy": "overwrite",
                "existing_texture_strategy": "reuse",
                "existing_material_strategy": "reuse",
            },
        }

        summary = build_package_summary(package_dir, report)

        self.assertEqual(summary["asset_count"], 1)
        self.assertEqual(summary["mesh_status"], "missing_source")
        self.assertEqual(summary["texture_count"], 2)
        self.assertEqual(summary["texture_status"], "ready")
        self.assertEqual(summary["material_count"], 1)
        self.assertEqual(summary["material_status"], "ready")
        self.assertEqual(summary["profile_status"], "ready")
        self.assertTrue(summary["can_accept"])
        self.assertEqual(summary["gate_status"], "warning")
        self.assertEqual(summary["risk_status"], "需复核")
        self.assertIn("警告项", summary["risk_message"])
        self.assertIn("Check texture group in UE.", summary["warnings"])
        self.assertEqual(summary["overwrite_strategy"]["existing_texture_strategy"], "reuse")

    def test_build_package_summary_prefers_manifest_mesh_check_count(self):
        package_dir = self._write_package("SM_Multi", mtime=10, mesh_count=5)

        summary = build_package_summary(package_dir)

        self.assertEqual(summary["asset_count"], 5)

    def test_build_package_summary_reads_last_import_report(self):
        package_dir = self._write_package("SM_Crate", mtime=10)
        report_path = os.path.join(package_dir, "SM_Crate_import_report.json")
        with open(report_path, "w", encoding="utf-8") as stream:
            json.dump({"stage": "unreal_import", "status": "success", "asset_name": "SM_Crate"}, stream)

        summary = build_package_summary(package_dir)

        self.assertEqual(summary["last_import_status"], "导入成功")
        self.assertEqual(summary["last_import_report_path"], report_path.replace("\\", "/"))

    def test_build_package_summary_exposes_recent_gate_and_import_reports(self):
        package_dir = self._write_package("SM_Crate", mtime=10)
        import_report_path = os.path.join(package_dir, "SM_Crate_import_report.json")
        gate_report_path = os.path.join(package_dir, "package_acceptance_flow_report.json")
        with open(import_report_path, "w", encoding="utf-8") as stream:
            json.dump({"stage": "unreal_import", "status": "success", "timestamp": "2026-05-30T10:00:00"}, stream)
        with open(gate_report_path, "w", encoding="utf-8") as stream:
            json.dump({"stage": "ue_gate", "status": "warning", "timestamp": "2026-05-30T11:00:00"}, stream)
        os.utime(import_report_path, (20, 20))
        os.utime(gate_report_path, (30, 30))

        summary = build_package_summary(package_dir)

        self.assertEqual(summary["report_path"], gate_report_path.replace("\\", "/"))
        self.assertEqual(summary["latest_report_path"], gate_report_path.replace("\\", "/"))
        self.assertTrue(summary["can_open_report"])
        self.assertEqual([item["kind"] for item in summary["recent_reports"]], ["gate_preview", "import"])
        self.assertEqual(summary["recent_reports"][0]["status"], "需复核")

    def test_unreal_log_history_attaches_recent_import_status(self):
        package_dir = self._write_package("SM_Crate", mtime=10)
        report_path = os.path.join(package_dir, "package_import_report.json")
        with open(report_path, "w", encoding="utf-8") as stream:
            json.dump({"stage": "unreal_import", "status": "failed", "asset_name": "SM_Crate"}, stream)
        log_path = os.path.join(self.temp_dir, "latest_unreal.log")
        with open(log_path, "w", encoding="utf-8") as stream:
            stream.write(
                json.dumps(
                    {
                        "timestamp": "2026-05-30T10:00:00",
                        "operation": "unreal_import",
                        "status": "failed",
                        "outputs": {"package_dir": package_dir},
                        "report_path": report_path,
                    }
                )
                + "\n"
            )

        history = discover_package_history("", "__missing_maya__", log_path, limit=10)

        self.assertEqual(history["package_count"], 1)
        self.assertEqual(history["packages"][0]["last_import_status"], "导入失败")
        self.assertEqual(history["packages"][0]["last_import_report_path"], report_path.replace("\\", "/"))

    def test_preview_package_gate_uses_acceptance_validator(self):
        package_dir = self._write_package("SM_Crate", mtime=10)

        summary = preview_package_gate(package_dir, acceptance_validator=FakeAcceptanceValidator())

        self.assertFalse(summary["can_accept"])
        self.assertEqual(summary["error_count"], 1)
        self.assertIn("Missing parent material.", summary["errors"])

    def test_gate_panel_state_exposes_visible_status_sections(self):
        package_dir = self._write_package("SM_Crate", mtime=10)

        state = build_gate_panel_state(package_dir, acceptance_validator=FakePassAcceptanceValidator())

        self.assertEqual(state["status"], "ready")
        self.assertTrue(state["can_import"])
        section_ids = [item["id"] for item in state["sections"]]
        self.assertEqual(section_ids, ["mesh", "texture", "material", "profile", "gate"])
        self.assertEqual(state["selected_package"]["gate_status"], "pass")
        self.assertEqual(state["title"], "Asset Forge 导入门禁工作台")
        self.assertEqual(state["selected_package"]["risk_status"], "可导入")

    def test_gate_panel_state_accepts_export_root_list_as_first_argument(self):
        root_a = os.path.join(self.temp_dir, "RootA")
        root_b = os.path.join(self.temp_dir, "RootB")
        os.makedirs(root_a)
        os.makedirs(root_b)
        self._write_package("SM_A", mtime=10, root=root_a)
        package_b = self._write_package("SM_B", mtime=30, root=root_b)

        state = build_gate_panel_state(
            export_root=[root_a, root_b],
            latest_maya_log_path="__missing_maya__",
            latest_unreal_log_path="__missing_unreal__",
            report_path=False,
        )

        self.assertEqual(state["status"], "ready")
        self.assertEqual(state["latest_package_dir"], package_b.replace("\\", "/"))
        self.assertEqual(state["selected_package_dir"], package_b.replace("\\", "/"))
        self.assertEqual(state["history"]["package_count"], 2)

    def _write_package(self, asset_name, mtime, root=None, mesh_count=None):
        package_dir = os.path.join(root or self.temp_dir, asset_name)
        os.makedirs(package_dir)
        manifest_path = os.path.join(package_dir, asset_name + "_manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as stream:
            manifest = {
                    "asset_forge_schema_version": "0.2",
                    "schema_version": "0.2",
                    "asset_name": asset_name,
                    "source_dcc": "maya",
                    "export_time": "2026-05-30T09:00:00",
                    "fbx_path": os.path.join(package_dir, asset_name + ".fbx"),
                    "target_path": "/Game/Props/" + asset_name,
                    "material_profile": "Props_Opaque_PainterUE_ARM",
                    "textures": [
                        {"usage": "base_color", "package_path": os.path.join(package_dir, "Textures", "T_" + asset_name + "_BaseColor.png")},
                        {"usage": "normal", "package_path": os.path.join(package_dir, "Textures", "T_" + asset_name + "_Normal.png")},
                    ],
                    "materials": [{"name": "M_" + asset_name, "textures": [{"usage": "base_color"}]}],
                }
            if mesh_count is not None:
                manifest["checks"] = {"mesh_exists": {"status": "pass", "value": mesh_count}}
            json.dump(manifest, stream)
        os.utime(manifest_path, (mtime, mtime))
        return package_dir


class FakeAcceptanceValidator(object):
    def validate(self, package_dir, report_path=None):
        return {
            "status": "error",
            "summary": {
                "can_accept": False,
                "warning_count": 0,
                "error_count": 1,
                "warnings": [],
                "errors": [{"message": "Missing parent material."}],
                "blocking_checks": ["parent_materials"],
                "warning_checks": [],
                "next_action": "Fix parent materials.",
            },
            "report_path": report_path or "",
        }


class FakePassAcceptanceValidator(object):
    def validate(self, package_dir, report_path=None):
        return {
            "status": "pass",
            "summary": {
                "can_accept": True,
                "warning_count": 0,
                "error_count": 0,
                "warnings": [],
                "errors": [],
                "blocking_checks": [],
                "warning_checks": [],
                "next_action": "Import.",
            },
            "checks": [{"id": "material_profile_reference", "status": "pass"}],
            "report_path": report_path or "",
        }


if __name__ == "__main__":
    unittest.main()
