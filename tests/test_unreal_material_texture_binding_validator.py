from asset_forge.shared.report_schema import summarize_pipeline
from asset_forge.unreal.material_texture_binding_validator import validate_material_texture_bindings


def test_errors_when_material_instance_would_fall_back_to_default_textures():
    report = validate_material_texture_bindings(
        {
            "profile": "Props_Opaque_PainterUE_ARM",
            "materials": [
                {
                    "material_name": "B_a1",
                    "target_asset_path": "/Game/Props/Materials/MI_B_a1",
                    "texture_parameters": {},
                    "slots": {},
                }
            ],
        },
        texture_import_plan={"textures": []},
        material_parameter_report={"texture_parameters": []},
        imported_textures=[],
    )

    assert report["status"] == "error"
    assert report["can_accept"] is False
    assert any(item["id"] == "material_required_textures_missing" for item in report["errors"])
    assert any(item["id"] == "required_texture_parameter_missing" and item["parameter"] == "BaseColor" for item in report["errors"])
    assert any(item["id"] == "required_texture_parameter_missing" and item["parameter"] == "Normal" for item in report["errors"])


def test_errors_when_planned_texture_was_not_imported():
    report = validate_material_texture_bindings(
        {
            "profile": "Props_Opaque_PainterUE_ARM",
            "materials": [
                {
                    "material_name": "B_b1",
                    "target_asset_path": "/Game/Props/Materials/MI_B_b1",
                    "texture_parameters": {
                        "BaseColor": "/Game/Props/Textures/T_B_b1_BaseColor",
                        "Normal": "/Game/Props/Textures/T_B_b1_Normal",
                    },
                    "slots": {
                        "base_color": "/Game/Props/Textures/T_B_b1_BaseColor",
                        "normal": "/Game/Props/Textures/T_B_b1_Normal",
                    },
                }
            ],
        },
        texture_import_plan={
            "textures": [
                {"target_asset_path": "/Game/Props/Textures/T_B_b1_BaseColor"},
                {"target_asset_path": "/Game/Props/Textures/T_B_b1_Normal"},
            ]
        },
        material_parameter_report={
            "texture_parameters": [
                {
                    "material_instance_path": "/Game/Props/Materials/MI_B_b1",
                    "name": "BaseColor",
                    "applied": True,
                    "texture_asset_path": "/Game/Props/Textures/T_B_b1_BaseColor",
                },
                {
                    "material_instance_path": "/Game/Props/Materials/MI_B_b1",
                    "name": "Normal",
                    "applied": False,
                    "texture_asset_path": "/Game/Props/Textures/T_B_b1_Normal",
                },
            ]
        },
        imported_textures=["/Game/Props/Textures/T_B_b1_BaseColor"],
    )

    assert report["status"] == "error"
    assert report["can_accept"] is False
    assert any(item["id"] == "texture_asset_exists" and item["parameter"] == "Normal" for item in report["errors"])
    assert any(item["id"] == "material_instance_texture_parameter_applied" and item["parameter"] == "Normal" for item in report["errors"])


def test_pipeline_summary_includes_material_texture_binding_errors():
    summary = summarize_pipeline(
        import_report={
            "status": "success",
            "material_texture_binding_validation": {
                "status": "error",
                "checks": [
                    {
                        "id": "required_texture_parameter_missing",
                        "status": "error",
                        "message": "材质 B_a1 缺少必需贴图 base_color->BaseColor，导入后会使用默认贴图。",
                    }
                ],
                "warnings": [],
                "errors": [{"id": "required_texture_parameter_missing"}],
            },
        }
    )

    assert summary["material_texture_binding_status"] == "error"
    assert summary["material_texture_binding_error_count"] == 1
    assert any(item["source"] == "material_texture_binding" for item in summary["errors"])


import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from asset_forge.unreal.pipeline import UnrealStaticMeshImportPipeline


class StrictPostImportTextureTests(unittest.TestCase):
    def setUp(self):
        self.mi = "/Game/Materials/MI_Body"
        self.paths = {p: "/Game/Textures/T_Body_" + p for p in ("BaseColor", "Normal", "ARM")}
        self.material = {"material_name": "Body", "target_asset_path": self.mi, "texture_parameters": dict(self.paths)}
        self.report = {
            "status": "success",
            "material_binding_plan": {"profile": "Props_Opaque_PBR", "materials": [self.material]},
            "texture_import_plan": {"textures": [{"target_asset_path": path} for path in self.paths.values()]},
            "imported_textures": list(self.paths.values()),
            "material_parameter_report": {"texture_parameters": []},
            "material_instance_policy_report": {"actions": [{"asset_path": self.mi, "action": "skipped"}]},
        }
        self.manifest = {"material_profile": "Props_Opaque_PBR"}
        self.objects = {key: value + "." + value.rsplit("/", 1)[-1] for key, value in self.paths.items()}
        self.unreal = SimpleNamespace(load_asset=Mock(return_value=object()), MaterialEditingLibrary=Mock())
        self.unreal.MaterialEditingLibrary.get_material_instance_texture_parameter_value.side_effect = self.texture
        self.pipeline = UnrealStaticMeshImportPipeline(material_instance_creator=SimpleNamespace(unreal=self.unreal))

    def texture(self, instance, name):
        if name not in self.objects:
            return None
        return SimpleNamespace(get_path_name=lambda: self.objects[name])

    def validate(self, after=True):
        self.pipeline._attach_material_texture_binding_validation(self.report, self.manifest, after_import=after)
        return self.report["material_texture_binding_validation"]

    def test_existing_skipped_or_shared_instance_without_setter_rows_is_verified(self):
        alias = dict(self.material, material_name="Trim")
        self.report["material_binding_plan"]["materials"].append(alias)
        result = self.validate()
        self.assertTrue(result["can_accept"])
        self.assertEqual(self.report["status"], "success")
        self.assertEqual(6, len([c for c in result["checks"] if c["id"]=="material_instance_texture_readback"]))
        self.unreal.load_asset.assert_called_once_with(self.mi)

    def test_reported_setter_success_cannot_hide_a_missing_or_swapped_actual_texture(self):
        self.report["material_parameter_report"]["texture_parameters"] = [
            {"material_instance_path": self.mi, "name": name, "applied": True, "texture_asset_path": path}
            for name, path in self.paths.items()]
        del self.objects["Normal"]
        self.objects["ARM"] = self.objects["ARM"].replace("T_Body_ARM.", "T_Trim_ARM.")
        result = self.validate()
        self.assertEqual(self.report["status"], "failed")
        self.assertTrue(result["blocks_acceptance"])
        mismatches = {r["parameter"]:r for r in result["errors"]}
        self.assertEqual(set(mismatches), {"Normal", "ARM"})
        self.assertEqual(mismatches["ARM"]["actual_path"], self.objects["ARM"])

    def test_missing_mi_or_unavailable_readback_fails_closed(self):
        self.unreal.load_asset.return_value = None
        self.assertFalse(self.validate()["can_accept"])
        self.unreal.MaterialEditingLibrary.get_material_instance_texture_parameter_value.assert_not_called()

    def test_empty_strict_material_plan_cannot_pass_actual_import(self):
        self.report["material_binding_plan"]["materials"] = []
        self.assertFalse(self.validate()["can_accept"])
        self.assertEqual(self.report["status"], "failed")

    def test_plan_only_and_disabled_material_import_skip_runtime_but_painter_is_read_after_import(self):
        self.assertTrue(self.validate(after=False)["can_accept"])
        self.report["resolved_preset"] = {"import_materials":False}
        self.report["material_binding_plan"]["materials"] = []
        self.assertEqual(self.validate()["status"], "skipped")
        self.unreal.load_asset.assert_not_called()
        self.report["resolved_preset"] = {}
        self.report["material_binding_plan"]["materials"] = [self.material]
        self.manifest["material_profile"] = "Props_Opaque_PainterUE_ARM"
        self.validate()
        self.assertEqual(self.report["status"], "success")
        self.unreal.load_asset.assert_called_once_with(self.mi)

    def test_legacy_painter_default_arm_is_a_named_warning_before_and_after_import(self):
        from asset_forge.shared.material_profile_schema import get_material_profile
        from asset_forge.unreal.gate_operator_messages import operator_messages
        from asset_forge.unreal.material_package_schema import DEFAULT_TEXTURE_PATHS
        from asset_forge.unreal.material_graph_evidence import build_material_graph_evidence_report

        profile = get_material_profile("Props_Opaque_PainterUE_ARM")
        self.manifest["resolved_material_profile"] = profile
        default_arm = DEFAULT_TEXTURE_PATHS["packed_arm"]
        self.objects["ARM"] = default_arm + "." + default_arm.rsplit("/", 1)[-1]
        self.material["texture_parameters"]["ARM"] = default_arm
        stages = []
        for after in (False, True):
            with self.subTest(after=after):
                result = self.validate(after)
                self.assertTrue(result["can_accept"])
                self.assertEqual(result["status"], "warning")
                warning, = result["warnings"]
                stages.append({"material_texture_binding_validation": result})
                self.assertEqual(warning["id"], "required_texture_parameter_missing")
                self.assertEqual(warning["material_instance_path"], self.mi)
                self.assertEqual(warning["parameter"], "ARM")
                self.assertIn("MI_Body 的 ARM 槽", warning["message"])
                graph = build_material_graph_evidence_report(self.report["material_binding_plan"],
                                                             material_texture_binding_validation=result)
                self.assertIn(warning, graph["warnings"])
                self.assertFalse(any(check["status"] == "pass" and check.get("material_instance_path") == self.mi
                                     and check.get("parameter") == "ARM" for check in graph["checks"]))
        self.assertIn("当前继承母材质默认贴图", warning["message"])
        flow = {"package_acceptance": stages[0], "dry_run": stages[0], "import": stages[1],
                "warnings": [{"source": "material_texture_binding", **stage["material_texture_binding_validation"]["warnings"][0]}
                             for stage in stages]}
        self.assertEqual(operator_messages(flow, "warnings"), ["必需贴图槽：" + warning["message"]])
