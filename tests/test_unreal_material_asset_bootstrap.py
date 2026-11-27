from __future__ import absolute_import

from pathlib import Path
import unittest

from asset_forge.unreal.material_asset_bootstrap import UnrealMaterialAssetBootstrap, bootstrap_default_material_assets
from asset_forge.unreal.material_library import PARAMETER_GROUPS, PARAMETER_SORT_PRIORITIES


class UnrealMaterialAssetBootstrapTest(unittest.TestCase):
    def test_plan_includes_default_material_assets(self):
        plan = UnrealMaterialAssetBootstrap(unreal_module=FakeUnreal()).plan()

        self.assertEqual(plan["content_mount"], "/AssetForge")
        self.assertEqual(plan["asset_count"], 36)
        self.assertEqual(plan["material_network_status"], "generated_pbr")
        self.assertIn("/AssetForge/Materials", plan["directories"])
        self.assertIn("/AssetForge/Textures", plan["directories"])
        self.assertIn("/AssetForge/Showcase", plan["directories"])
        self.assertEqual(plan["showcase_report"]["status"], "pass")
        self.assertEqual(plan["showcase_plan"]["level_path"], "/AssetForge/Showcase/LV_AF_Material_Showcase")
        self.assertEqual(plan["assets"][0]["factory"], "TextureFactory")
        self.assertEqual(plan["assets"][0]["asset_class"], "Texture2D")
        self.assertIn("BaseColor", plan["material_network_plans"][0]["texture_parameters"])
        self.assertTrue(any(item["material_property"] == "roughness" for item in plan["material_network_plans"][0]["connections"]))
        self.assertTrue(any(item["parameter"] == "BaseColor" and item["output"] == "A" and item["material_property"] == "opacity_mask" for item in plan["material_network_plans"][0]["connections"]))
        self.assertTrue(any(item["parameter"] == "OpacityMask" and item["output"] == "R" and item["channel_semantic"] == "separate_opacity_mask" for item in plan["material_network_plans"][0]["connections"]))
        self.assertFalse(any(item["material_path"].endswith("_VT") for item in plan["material_network_plans"]))
        self.assertTrue(all(item.get("default_asset_path") for item in plan["material_network_plans"][0]["nodes"]))
        self.assertEqual(self._node(plan, "ARM")["sampler_type"], "masks")
        self.assertEqual(self._node(plan, "Normal")["default_asset_path"], "/AssetForge/Textures/T_AF_Default_Normal")
        self.assertEqual(self._node(plan, "ARM")["default_asset_path"], "/AssetForge/Textures/T_AF_Default_ARM")
        self.assertEqual(self._node(plan, "OpacityMask")["default_asset_path"], "/AssetForge/Textures/T_AF_Default_OpacityMask")
        self.assertTrue(any(item["path"] == "/AssetForge/Textures/T_AF_Preview_Emissive_Panels" for item in plan["assets"]))

    def test_bootstrap_creates_missing_assets_and_sets_blend_modes(self):
        fake_unreal = FakeUnreal()

        report = UnrealMaterialAssetBootstrap(unreal_module=fake_unreal).bootstrap()

        self.assertEqual(report["status"], "success")
        self.assertIn("/AssetForge/Materials/M_AF_Props_Master", report["created_assets"])
        self.assertIn("/AssetForge/Materials/M_AF_Props_Opaque_Master", report["created_assets"])
        self.assertIn("/AssetForge/Textures/T_AF_Default_ARM", report["created_assets"])
        self.assertIn("/AssetForge/Textures/T_AF_Default_OpacityMask", report["created_assets"])
        self.assertIn("/AssetForge/Textures/T_AF_Preview_Emissive_Panels", report["created_assets"])
        self.assertIn("/AssetForge/Textures/T_AF_Preview_ARM_Metal", report["created_assets"])
        self.assertNotIn("/AssetForge/Materials/M_AF_Props_Opaque", report["created_assets"])
        self.assertNotIn("/AssetForge/ParameterCollections/MPC_AF_Global", report["created_assets"])
        self.assertNotIn("/AssetForge/MaterialFunctions/MF_AF_UnpackARM", report["created_assets"])
        self.assertIn("/AssetForge/Materials", fake_unreal.EditorAssetLibrary.directories)
        self.assertIn("/AssetForge/Showcase", fake_unreal.EditorAssetLibrary.directories)
        self.assertEqual(report["showcase_report"]["status"], "skipped")
        self.assertGreaterEqual(report["showcase_report"]["entry_count"], 0)
        props = fake_unreal.AssetToolsHelpers.asset_tools.assets["/AssetForge/Materials/M_AF_Props_Master"]
        opaque_props = fake_unreal.AssetToolsHelpers.asset_tools.assets["/AssetForge/Materials/M_AF_Props_Opaque_Master"]
        character = fake_unreal.AssetToolsHelpers.asset_tools.assets["/AssetForge/Materials/M_AF_Character_Master"]
        self.assertEqual(props.blend_mode, "masked")
        self.assertEqual(props.opacity_mask_clip_value, 0.333)
        self.assertEqual(opaque_props.blend_mode, "opaque")
        self.assertEqual(character.blend_mode, "opaque")
        self.assertEqual(report["material_network_reports"][0]["status"], "success")
        self.assertIn("BaseColor", [item["parameter"] for item in report["material_network_reports"][0]["created_nodes"]])
        self.assertIn("NormalStrength", [item["parameter"] for item in report["material_network_reports"][0]["created_nodes"]])
        self.assertIn("UVTiling", [item["parameter"] for item in report["material_network_reports"][0]["created_nodes"]])
        self.assertIn("Specular", [item["parameter"] for item in report["material_network_reports"][0]["created_nodes"]])
        self.assertTrue(all(item.sampler_type for item in fake_unreal.MaterialEditingLibrary.expressions if hasattr(item, "sampler_type")))
        self.assertTrue(all(getattr(item, "texture", None) for item in fake_unreal.MaterialEditingLibrary.expressions if hasattr(item, "sampler_type")))
        self.assertTrue(any(getattr(item, "parameter_name", "") == "UseEmissive" for item in fake_unreal.MaterialEditingLibrary.expressions))
        self.assertTrue(any(getattr(item, "parameter_name", "") == "UseOpacityMask" for item in fake_unreal.MaterialEditingLibrary.expressions))
        self.assertTrue(any(getattr(item, "parameter_name", "") == "UseSeparateOpacityMask" for item in fake_unreal.MaterialEditingLibrary.expressions))
        comment_nodes = [item for item in fake_unreal.MaterialEditingLibrary.expressions if isinstance(item, FakeCommentExpression)]
        self.assertTrue(comment_nodes)
        self.assertTrue(all(getattr(item, "text", "") or getattr(item, "Text", "") for item in comment_nodes))
        self.assertTrue(all(getattr(item, "desc", "") or getattr(item, "Desc", "") for item in comment_nodes))
        self.assertTrue(all(14 <= (getattr(item, "font_size", 0) or getattr(item, "FontSize", 0)) <= 20 for item in comment_nodes))
        self.assertTrue(all(getattr(item, "comment_color", None) or getattr(item, "CommentColor", None) for item in comment_nodes))
        self.assertTrue(all((getattr(item, "size_x", 0) or getattr(item, "SizeX", 0)) >= 820 for item in comment_nodes))
        self.assertTrue(all((getattr(item, "size_y", 0) or getattr(item, "SizeY", 0)) >= 240 for item in comment_nodes))
        self.assertFalse(any(getattr(item, "bCommentBubbleVisible", False) or getattr(item, "comment_bubble_visible", False) for item in comment_nodes))
        self.assertFalse(any(getattr(item, "bCommentBubbleVisible_InDetailsPanel", False) for item in comment_nodes))
        self.assertFalse(any(getattr(item, "bColorCommentBubble", False) for item in comment_nodes))
        self.assertTrue(all(getattr(item, "group_mode", False) or getattr(item, "bGroupMode", False) for item in comment_nodes))
        self.assertFalse(any(hasattr(item, "comment_text") for item in comment_nodes))
        expression_descriptions = {
            getattr(item, "parameter_name", ""): getattr(item, "desc", "") or getattr(item, "description", "")
            for item in fake_unreal.MaterialEditingLibrary.expressions
            if getattr(item, "parameter_name", "")
        }
        self.assertIn("基础色", expression_descriptions["BaseColor"])
        self.assertIn("法线", expression_descriptions["Normal"])
        self.assertIn("ARM", expression_descriptions["ARM"])
        self.assertIn("镂空", expression_descriptions["UseOpacityMask"])
        self.assertIn("独立遮罩", expression_descriptions["UseSeparateOpacityMask"])
        self.assertIn("自发光", expression_descriptions["UseEmissive"])
        parameter_groups = {
            getattr(item, "parameter_name", ""): getattr(item, "group", "") or getattr(item, "Group", "")
            for item in fake_unreal.MaterialEditingLibrary.expressions
            if getattr(item, "parameter_name", "")
        }
        parameter_sort_priorities = {
            getattr(item, "parameter_name", ""): getattr(item, "sort_priority", None)
            for item in fake_unreal.MaterialEditingLibrary.expressions
            if getattr(item, "parameter_name", "")
        }
        self.assertIn("BaseColor", parameter_groups["BaseColor"])
        self.assertIn("Normal", parameter_groups["Normal"])
        self.assertIn("PBR", parameter_groups["ARM"])
        self.assertIn("Opacity", parameter_groups["UseOpacityMask"])
        self.assertLess(parameter_sort_priorities["BaseColor"], parameter_sort_priorities["Normal"])
        self.assertLess(parameter_sort_priorities["Normal"], parameter_sort_priorities["ARM"])
        self.assertLess(parameter_sort_priorities["ARM"], parameter_sort_priorities["UseOpacityMask"])
        comment_text = "\n".join(getattr(item, "text", "") or getattr(item, "Text", "") for item in comment_nodes)
        for text in ("UV", "ARM", "基础色", "法线", "瑕疵", "自发光", "镂空遮罩"):
            self.assertIn(text, comment_text)
        comment_reports = [item for item in report["material_network_reports"][0]["created_nodes"] if item.get("node_type") == "MaterialExpressionComment"]
        self.assertTrue(comment_reports)
        self.assertTrue(all(item.get("comment_color") for item in comment_reports))
        self.assertTrue(all(14 <= item.get("font_size", 0) <= 20 for item in comment_reports))
        self.assertFalse(any(item.get("comment_bubble_visible") for item in comment_reports))
        self.assertTrue(all(item.get("group_mode") for item in comment_reports))
        self.assertTrue(all(item.get("written_properties", {}).get("text") in ("text", "Text") for item in comment_reports))
        self.assertTrue(all(item.get("written_properties", {}).get("size_x") in ("size_x", "SizeX") for item in comment_reports))
        self.assertTrue(all(item.get("written_properties", {}).get("comment_color") in ("comment_color", "CommentColor") for item in comment_reports))
        self.assertTrue(all(item.get("written_properties", {}).get("group_mode") in ("group_mode", "bGroupMode") for item in comment_reports))
        self.assertTrue(all(item.get("readback", {}).get("text") == item.get("comment_text") for item in comment_reports))
        self.assertTrue(all(item.get("readback", {}).get("size_x", 0) >= 820 for item in comment_reports))
        comment_ids = [item.get("comment_id") for item in comment_reports]
        for comment_id in ("AF_01_UV", "AF_02_BaseColor", "AF_03_Normal", "AF_04_PBR", "AF_05_Imperfection", "AF_06_Emissive", "AF_07_Opacity"):
            self.assertIn(comment_id, comment_ids)
        by_comment_id = dict((item.get("comment_id"), item) for item in comment_reports)
        self.assertIn("BaseColor", by_comment_id["AF_02_BaseColor"]["covered_parameters"])
        self.assertIn("Normal", by_comment_id["AF_03_Normal"]["covered_parameters"])
        self.assertIn("ARM", by_comment_id["AF_04_PBR"]["covered_parameters"])
        self.assertIn("Opacity", by_comment_id["AF_07_Opacity"]["covered_parameters"])
        self.assertIn("UseOpacityMask", by_comment_id["AF_07_Opacity"]["covered_parameters"])
        self.assertEqual(by_comment_id["AF_02_BaseColor"]["parameter_groups"]["BaseColor"], "02 基础色 / BaseColor")
        self.assertEqual(by_comment_id["AF_03_Normal"]["parameter_groups"]["Normal"], "03 法线 / Normal")
        self.assertIn("07 镂空 / Opacity Mask", by_comment_id["AF_07_Opacity"]["covered_parameter_groups"])
        self.assertTrue(all(item.get("bounds", {}).get("width", 0) >= 820 for item in comment_reports if item.get("comment_id")))
        self.assertTrue(all(item.get("bounds", {}).get("height", 0) >= 240 for item in comment_reports if item.get("comment_id")))
        self.assertFalse(self._comment_blocks_overlap([item["bounds"] for item in comment_reports]))
        layout = report["material_network_reports"][0]["comment_layout_validation"]
        self.assertEqual(layout["status"], "pass")
        self.assertFalse(layout["blocks_overlap"])
        self.assertEqual(layout["issues"], [])
        self.assertEqual(set(comment_ids), set(item["id"] for item in layout["blocks"]))
        self.assertTrue(all(14 <= item["font_size"] <= 20 for item in layout["blocks"]))
        self.assertFalse(self._comment_blocks_overlap([item["bounds"] for item in layout["blocks"]]))
        layout_by_id = dict((item["id"], item) for item in layout["blocks"])
        self.assertIn("BaseColor", layout_by_id["AF_02_BaseColor"]["covered_parameters_present"])
        self.assertIn("Normal", layout_by_id["AF_03_Normal"]["covered_parameters_present"])
        self.assertIn("ARM", layout_by_id["AF_04_PBR"]["covered_parameters_present"])
        self.assertIn("UseOpacityMask", layout_by_id["AF_07_Opacity"]["covered_parameters_present"])
        self.assertEqual(layout_by_id["AF_02_BaseColor"]["parameter_groups"]["BaseColor"], "02 基础色 / BaseColor")
        self.assertEqual(layout_by_id["AF_07_Opacity"]["readback"]["text"], "AF 07 镂空遮罩")
        for switch_name in ("UseEmissive", "UseOpacityMask", "UseSeparateOpacityMask"):
            self.assertTrue(any(getattr(item, "parameter_name", "") == switch_name for item in fake_unreal.MaterialEditingLibrary.expressions))
            self.assertIn((switch_name, "", "", "Alpha"), fake_unreal.MaterialEditingLibrary.connections)
        self.assertTrue(any(item.get("node_type") == "LinearInterpolate" for item in report["material_network_reports"][0]["created_nodes"]))
        self.assertTrue(any(getattr(item, "parameter_name", "") == "UseEmissiveOffValue" for item in fake_unreal.MaterialEditingLibrary.expressions))
        self.assertTrue(any(getattr(item, "parameter_name", "") == "UseOpacityMaskOffValue" for item in fake_unreal.MaterialEditingLibrary.expressions))
        tint_nodes = [item for item in fake_unreal.MaterialEditingLibrary.expressions if getattr(item, "parameter_name", "") == "BaseColorTint"]
        self.assertTrue(tint_nodes)
        self.assertTrue(all(isinstance(item.default_value, fake_unreal.LinearColor) for item in tint_nodes))
        self.assertFalse(fake_unreal.MaterialEditingLibrary.function_expressions)
        self.assertTrue(any(item[2] == "specular" for item in fake_unreal.MaterialEditingLibrary.connections if len(item) == 3))
        self.assertTrue(any(item[2] == "subsurface_color" for item in fake_unreal.MaterialEditingLibrary.connections if len(item) == 3))
        self.assertTrue(any(getattr(item, "parameter_name", "") == "SubsurfaceTint" for item in fake_unreal.MaterialEditingLibrary.expressions))
        self.assertTrue(
            all(
                item["expression_class"] == "MaterialExpressionTextureSampleParameter2D"
                for item in report["material_network_reports"][1]["created_nodes"]
                if item.get("parameter") in ("BaseColor", "Normal", "ARM")
            )
        )
        self.assertIn("/AssetForge/Materials/M_AF_Props_Master", fake_unreal.EditorAssetLibrary.saved)
        preset = fake_unreal.AssetToolsHelpers.asset_tools.assets["/AssetForge/MaterialInstances/MI_AF_Props_DirtyWear"]
        self.assertEqual(preset.parent.asset_name, "M_AF_Props_Master")
        self.assertIn(("MI_AF_Props_DirtyWear", "ImperfectionIntensity", 0.75), fake_unreal.MaterialEditingLibrary.scalar_calls)
        self.assertIn(("MI_AF_Props_Emissive", "Emissive", "/AssetForge/Textures/T_AF_Preview_Emissive_Panels"), fake_unreal.MaterialEditingLibrary.texture_calls)
        self.assertIn(("MI_AF_Props_MetalPanel", "ARM", "/AssetForge/Textures/T_AF_Preview_ARM_Metal"), fake_unreal.MaterialEditingLibrary.texture_calls)
        self.assertIn(("MI_AF_Character_SkinPreview", "BaseColor", "/AssetForge/Textures/T_AF_Preview_BaseColor_SkinWarm"), fake_unreal.MaterialEditingLibrary.texture_calls)
        self.assertIn(("MI_AF_Props_Masked_SeparateMask", "UseSeparateOpacityMask", True), fake_unreal.MaterialEditingLibrary.static_switch_calls)
        self.assertNotIn(("MI_AF_HardSurface_WorldAligned", "UseWorldAligned", True), fake_unreal.MaterialEditingLibrary.static_switch_calls)
        self.assertNotIn(("MI_AF_HardSurface_POM", "UsePOM", True), fake_unreal.MaterialEditingLibrary.static_switch_calls)

    def test_material_parameter_groups_cover_sort_priority_parameters(self):
        missing = [name for name in PARAMETER_SORT_PRIORITIES if name not in PARAMETER_GROUPS]

        self.assertEqual(missing, [])

    def test_comment_size_property_falls_back_when_editor_setter_does_not_persist(self):
        bootstrapper = UnrealMaterialAssetBootstrap(unreal_module=FakeUnreal())
        expression = FakeStaleSizeCommentExpression()
        report = {"issues": []}
        written_properties = {}

        ok = bootstrapper._set_comment_property(
            expression,
            ("SizeX", "size_x"),
            920,
            report,
            "AF 01 UV 坐标",
            written_properties=written_properties,
            key="size_x",
        )

        self.assertTrue(ok)
        self.assertEqual(expression.SizeX, 920)
        self.assertEqual(written_properties["size_x"], "SizeX")
        self.assertEqual(report["issues"], [])

    def test_native_comment_repair_refreshes_report_readback(self):
        fake_unreal = FakeUnreal()
        fake_unreal.MaterialExpressionComment = FakeStaleSizeCommentExpression
        fake_unreal.AssetForgeMaterialCommentLibrary = FakeCommentRepairLibrary

        report = UnrealMaterialAssetBootstrap(unreal_module=fake_unreal).bootstrap()

        network = report["material_network_reports"][0]
        self.assertEqual(network["native_comment_repair"]["status"], "success")
        comments = [item for item in network["created_nodes"] if item.get("node_type") == "MaterialExpressionComment"]
        self.assertTrue(comments)
        self.assertTrue(all(item.get("readback", {}).get("size_x", 0) >= 900 for item in comments))
        self.assertTrue(all(item.get("bounds", {}).get("width", 0) >= 900 for item in comments))

    def _comment_blocks_overlap(self, bounds):
        for index, left in enumerate(bounds):
            for right in bounds[index + 1 :]:
                if (
                    left["x"] < right["x"] + right["width"]
                    and left["x"] + left["width"] > right["x"]
                    and left["y"] < right["y"] + right["height"]
                    and left["y"] + left["height"] > right["y"]
                ):
                    return True
        return False

    def test_bootstrap_recreates_existing_material_assets(self):
        fake_unreal = FakeUnreal(existing_assets=["/AssetForge/Materials/M_AF_Props_Master"])

        report = UnrealMaterialAssetBootstrap(unreal_module=fake_unreal).bootstrap()

        self.assertIn("/AssetForge/Materials/M_AF_Props_Master", report["existing_assets"])
        self.assertNotIn("/AssetForge/Materials/M_AF_Props_Master", report["created_assets"])
        self.assertNotIn("/AssetForge/Materials/M_AF_Props_Master", fake_unreal.EditorAssetLibrary.deleted)
        self.assertIn("/AssetForge/Materials/M_AF_Props_Master", report["updated_assets"])

    def test_import_bootstrap_can_reuse_existing_plugin_assets_without_saving(self):
        plan_probe = UnrealMaterialAssetBootstrap(unreal_module=FakeUnreal())
        existing_assets = [item["path"] for item in plan_probe.plan()["assets"]]
        fake_unreal = FakeUnreal(existing_assets=existing_assets)

        report = UnrealMaterialAssetBootstrap(unreal_module=fake_unreal).bootstrap(repair_existing_assets=False)

        self.assertEqual(report["status"], "success")
        self.assertFalse(report["repair_existing_assets"])
        self.assertEqual(report["created_assets"], [])
        self.assertEqual(report["updated_assets"], [])
        self.assertEqual(report["configured_textures"], [])
        self.assertEqual(report["material_network_reports"], [])
        self.assertEqual(fake_unreal.EditorAssetLibrary.saved, [])

    def test_repeated_bootstrap_does_not_keep_stale_graph_nodes(self):
        fake_unreal = FakeUnreal()
        bootstrapper = UnrealMaterialAssetBootstrap(unreal_module=fake_unreal)

        first_report = bootstrapper.bootstrap()
        first_count = len(fake_unreal.MaterialEditingLibrary.expressions)
        second_report = bootstrapper.bootstrap()
        second_count = len(fake_unreal.MaterialEditingLibrary.expressions)

        self.assertEqual(first_report["status"], "success")
        self.assertEqual(second_report["status"], "success")
        self.assertEqual(second_count, first_count)
        self.assertTrue(second_report["material_network_reports"][0]["deleted_expression_count"] > 0)

    def test_reset_uses_object_iterator_when_expression_property_is_empty(self):
        fake_unreal = FakeUnreal()
        material = FakeAsset()
        material.path_name = "/AssetForge/Materials/M_AF_Props_Master.M_AF_Props_Master"
        stale_expression = FakeExpression()
        stale_expression.class_name = "MaterialExpressionMultiply"
        stale_expression.outer = material
        fake_unreal.iterated_objects = [stale_expression]

        report = {"api_usage": {}, "issues": [], "deleted_expression_count": 0}
        UnrealMaterialAssetBootstrap(unreal_module=fake_unreal)._reset_generated_material_network(
            material,
            fake_unreal.MaterialEditingLibrary,
            report,
        )

        self.assertEqual(report["deleted_expression_count"], 1)
        self.assertNotIn(stale_expression, fake_unreal.MaterialEditingLibrary.expressions)

    def test_bootstrap_reports_legacy_props_assets_without_default_cleanup(self):
        fake_unreal = FakeUnreal(
            existing_assets=[
                "/AssetForge/Materials/M_AF_Props_Opaque",
                "/AssetForge/Materials/M_AF_Props_Translucent_VT",
                "/AssetForge/Materials/M_AF_HardSurface_POM",
                "/AssetForge/Materials/M_AF_Glass_Translucent",
            ]
        )

        report = UnrealMaterialAssetBootstrap(unreal_module=fake_unreal).bootstrap()

        self.assertFalse(report["obsolete_asset_cleanup_enabled"])
        self.assertIn("/AssetForge/Materials/M_AF_Props_Opaque", report["obsolete_assets_planned_for_cleanup"])
        self.assertEqual(report["deleted_obsolete_assets"], [])
        self.assertNotIn("/AssetForge/Materials/M_AF_Props_Opaque", fake_unreal.EditorAssetLibrary.deleted)

    def test_bootstrap_cleans_legacy_props_assets_only_when_explicitly_enabled(self):
        fake_unreal = FakeUnreal(
            existing_assets=[
                "/AssetForge/Materials/M_AF_Props_Opaque",
                "/AssetForge/Materials/M_AF_Props_Translucent_VT",
                "/AssetForge/Materials/M_AF_HardSurface_POM",
                "/AssetForge/Materials/M_AF_Glass_Translucent",
            ]
        )

        report = UnrealMaterialAssetBootstrap(unreal_module=fake_unreal).bootstrap(cleanup_obsolete_assets=True)

        self.assertTrue(report["obsolete_asset_cleanup_enabled"])
        self.assertNotIn("/AssetForge/Materials/M_AF_Props_Opaque", report["existing_assets"])
        self.assertNotIn("/AssetForge/Materials/M_AF_Props_Opaque", report["created_assets"])
        self.assertIn("/AssetForge/Materials/M_AF_Props_Opaque", report["obsolete_assets_planned_for_cleanup"])
        self.assertIn("/AssetForge/Materials/M_AF_Props_Translucent_VT", report["deleted_obsolete_assets"])
        self.assertIn("/AssetForge/Materials/M_AF_Props_Opaque", fake_unreal.EditorAssetLibrary.deleted)
        self.assertIn("/AssetForge/Materials/M_AF_HardSurface_POM", fake_unreal.EditorAssetLibrary.deleted)
        self.assertIn("/AssetForge/Materials/M_AF_Glass_Translucent", fake_unreal.EditorAssetLibrary.deleted)
        self.assertNotIn("/AssetForge/Materials/M_AF_HardSurface_POM", report["created_assets"])
        self.assertNotIn("/AssetForge/Materials/M_AF_Glass_Translucent", report["created_assets"])

    def test_inspect_assets_reports_existing_and_missing_counts(self):
        fake_unreal = FakeUnreal(existing_assets=["/AssetForge/Materials/M_AF_Props_Master"])

        report = UnrealMaterialAssetBootstrap(unreal_module=fake_unreal).inspect_assets()

        self.assertEqual(report["status"], "warning")
        self.assertEqual(report["planned_count"], 36)
        self.assertEqual(report["existing_count"], 1)
        self.assertEqual(report["missing_count"], 35)
        self.assertIn("/AssetForge/Materials/M_AF_Props_Opaque_Master", report["missing_assets"])
        self.assertIn("/AssetForge/Materials/M_AF_Props_Master", report["existing_assets"])
        self.assertIn("/AssetForge/Materials/M_AF_Environment_Master", report["missing_assets"])

    def test_dry_run_does_not_create_assets(self):
        fake_unreal = FakeUnreal()

        report = UnrealMaterialAssetBootstrap(unreal_module=fake_unreal).bootstrap(dry_run=True)

        self.assertEqual(report["status"], "skipped")
        self.assertEqual(report["asset_validation"]["missing_count"], 36)
        self.assertTrue(report["material_network_reports"])
        self.assertEqual(report["material_network_reports"][0]["status"], "dry_run")
        self.assertIn("BaseColor", [item["parameter"] for item in report["material_network_reports"][0]["nodes"]])
        self.assertTrue(any(item["material_property"] == "roughness" for item in report["material_network_reports"][0]["connections"]))
        self.assertEqual(fake_unreal.AssetToolsHelpers.asset_tools.assets, {})

    def test_dry_run_reports_legacy_cleanup_without_deleting_assets(self):
        fake_unreal = FakeUnreal(existing_assets=["/AssetForge/Materials/M_AF_Props_Opaque"])

        report = UnrealMaterialAssetBootstrap(unreal_module=fake_unreal).bootstrap(dry_run=True)

        self.assertEqual(report["obsolete_assets_planned_for_cleanup"], ["/AssetForge/Materials/M_AF_Props_Opaque"])
        self.assertEqual(report["deleted_obsolete_assets"], [])
        self.assertNotIn("/AssetForge/Materials/M_AF_Props_Opaque", fake_unreal.EditorAssetLibrary.deleted)

    def test_default_dry_run_keeps_network_plan_without_unreal(self):
        report = bootstrap_default_material_assets(dry_run=True)

        self.assertEqual(report["status"], "skipped")
        self.assertTrue(report["material_network_reports"])
        first = report["material_network_reports"][0]
        self.assertEqual(first["status"], "dry_run")
        self.assertIn("BaseColor", [item["parameter"] for item in first["nodes"]])
        self.assertIn("Normal", [item["parameter"] for item in first["nodes"]])
        self.assertTrue(any(item["parameter"] in ("ARM", "ORM") for item in first["nodes"]))
        self.assertTrue(any(item["material_property"] == "ambient_occlusion" for item in first["connections"]))
        self.assertTrue(any(item["material_property"] == "roughness" for item in first["connections"]))
        self.assertTrue(any(item["material_property"] == "metallic" for item in first["connections"]))
        self.assertEqual(first["created_nodes"], [])
        self.assertEqual(first["connected"], [])
        self.assertIn("当前不在 Unreal Python 环境", report["issues"][0])
        self.assertIn("MaterialEditingLibrary.create_material_expression", first["api_usage"]["create_node"])

    def test_material_bootstrap_source_has_no_common_mojibake_markers(self):
        source = Path("asset_forge/unreal/material_asset_bootstrap.py").read_text(encoding="utf-8")
        for marker in mojibake_markers():
            self.assertNotIn(marker, source)
        self.assertIn("UE Python bootstrap 将创建参数化 PBR 母材质网络", source)

    def test_vt_material_plan_is_not_generated_until_sampler_defaults_are_verified(self):
        report = bootstrap_default_material_assets(dry_run=True)

        self.assertFalse(any(item["material_path"].endswith("_VT") for item in report["material_network_reports"]))

    def test_parent_material_validation_reports_missing_parent_as_error(self):
        fake_unreal = FakeUnreal(existing_assets=[])
        plan = {
            "materials": [
                {
                    "parent_material": "/AssetForge/Materials/M_AF_Props_Opaque",
                    "target_asset_path": "/Game/Props/Materials/M_Crate",
                }
            ]
        }

        report = UnrealMaterialAssetBootstrap(unreal_module=fake_unreal).validate_parent_materials(plan)

        self.assertEqual(report["status"], "error")
        self.assertFalse(report["can_create_material_instances"])
        self.assertEqual(report["missing_parent_materials"], ["/AssetForge/Materials/M_AF_Props_Opaque"])
        self.assertIn("缺少母材质", report["checks"][0]["message"])


    def _node(self, plan, parameter):
        for node in plan["material_network_plans"][0]["nodes"]:
            if node.get("parameter") == parameter:
                return node
        raise AssertionError("missing node: {0}".format(parameter))


class FakeAsset(object):
    pass


def mojibake_markers():
    return [
        chr(0x704F),
        chr(0x8930),
        chr(0x59E3) + chr(0x5D86) + chr(0x6F57),
        chr(0x3F) * 4,
        chr(0x5A34) + chr(0x5B2D) + chr(0x762F),
        chr(0x59DD) + chr(0xFF45) + chr(0x7D21),
    ]


class FakeExpressionInput(object):
    def __init__(self):
        self.expression = None
        self.output_index = 0
        self.input_name = ""

    def set_editor_property(self, name, value):
        setattr(self, name, value)


class FakeExpression(object):
    def __init__(self):
        self.A = FakeExpressionInput()
        self.B = FakeExpressionInput()
        self.input = FakeExpressionInput()
        self.Input = FakeExpressionInput()

    def set_editor_property(self, name, value):
        setattr(self, name, value)

    def get_editor_property(self, name):
        return getattr(self, name)

    def get_class(self):
        return self

    def get_name(self):
        return getattr(self, "class_name", self.__class__.__name__)

    def get_outer(self):
        return getattr(self, "outer", None)


class FakeCommentExpression(FakeExpression):
    valid_editor_properties = set(
        [
            "Text",
            "text",
            "Desc",
            "desc",
            "SizeX",
            "size_x",
            "SizeY",
            "size_y",
            "FontSize",
            "font_size",
            "CommentColor",
            "comment_color",
            "MaterialExpressionEditorX",
            "material_expression_editor_x",
            "MaterialExpressionEditorY",
            "material_expression_editor_y",
            "bCommentBubbleVisible",
            "comment_bubble_visible",
            "bCommentBubbleVisible_InDetailsPanel",
            "comment_bubble_visible_in_details_panel",
            "bColorCommentBubble",
            "color_comment_bubble",
            "bGroupMode",
            "group_mode",
        ]
    )

    def set_editor_property(self, name, value):
        if name not in self.valid_editor_properties:
            raise AttributeError(name)
        setattr(self, name, value)

    def get_editor_property(self, name):
        if name not in self.valid_editor_properties:
            raise AttributeError(name)
        return getattr(self, name)


class FakeStaleSizeCommentExpression(FakeCommentExpression):
    def set_editor_property(self, name, value):
        if name in ("SizeX", "SizeY"):
            self.stale_editor_size = value
            return
        super(FakeStaleSizeCommentExpression, self).set_editor_property(name, value)

    def get_editor_property(self, name):
        if name in ("SizeX", "SizeY"):
            return 0
        return super(FakeStaleSizeCommentExpression, self).get_editor_property(name)


class FakeCommentRepairLibrary(object):
    @staticmethod
    def repair_asset_forge_comment_blocks(material_asset):
        repaired = 0
        for expression in getattr(material_asset, "expressions", []):
            if not isinstance(expression, FakeCommentExpression):
                continue
            if not (getattr(expression, "text", "") or getattr(expression, "Text", "")).startswith("AF "):
                continue
            expression.SizeX = 920
            expression.SizeY = 280
            expression.size_x = 920
            expression.size_y = 280
            repaired += 1
        return repaired


class FakeAssetTools(object):
    def __init__(self):
        self.assets = {}

    def create_asset(self, asset_name, package_path, asset_class, factory):
        asset = FakeAsset()
        asset.asset_name = asset_name
        asset.package_path = package_path
        asset.asset_class = asset_class
        asset.factory = factory
        asset.asset_path = package_path + "/" + asset_name
        self.assets[asset.asset_path] = asset
        return asset


class FakeAssetToolsHelpers(object):
    asset_tools = FakeAssetTools()

    @classmethod
    def get_asset_tools(cls):
        return cls.asset_tools


class FakeUnreal(object):
    AssetToolsHelpers = FakeAssetToolsHelpers
    Material = "Material"
    MaterialFunction = "MaterialFunction"
    MaterialInstanceConstant = "MaterialInstanceConstant"
    MaterialParameterCollection = "MaterialParameterCollection"
    Texture2D = "Texture2D"
    MaterialExpressionTextureSampleParameter2D = FakeExpression
    MaterialExpressionFunctionInput = FakeExpression
    MaterialExpressionFunctionOutput = FakeExpression
    MaterialExpressionMultiply = FakeExpression
    MaterialExpressionScalarParameter = FakeExpression
    MaterialExpressionVectorParameter = FakeExpression
    MaterialExpressionStaticSwitchParameter = FakeExpression
    MaterialExpressionLinearInterpolate = FakeExpression
    MaterialExpressionTextureCoordinate = FakeExpression
    MaterialExpressionComponentMask = FakeExpression
    MaterialExpressionAppendVector = FakeExpression
    MaterialExpressionMax = FakeExpression
    MaterialExpressionNormalize = FakeExpression
    MaterialExpressionComment = FakeCommentExpression
    MaterialExpressionFlattenNormal = FakeExpression
    MaterialExpressionOneMinus = FakeExpression
    MaterialExpressionConstant = FakeExpression
    MaterialExpressionMultiply = FakeExpression
    MaterialExpressionScalarParameter = FakeExpression
    MaterialExpressionVectorParameter = FakeExpression
    MaterialExpressionFlattenNormal = FakeExpression
    MaterialExpressionOneMinus = FakeExpression

    class MaterialFactoryNew(object):
        pass

    class LinearColor(object):
        def __init__(self, r, g, b, a):
            self.r = r
            self.g = g
            self.b = b
            self.a = a

    class MaterialFunctionFactoryNew(object):
        pass

    class MaterialInstanceConstantFactoryNew(object):
        pass

    class MaterialParameterCollectionFactoryNew(object):
        pass

    class TextureFactory(object):
        pass

    class TextureCompressionSettings(object):
        TC_DEFAULT = "default"
        TC_NORMALMAP = "normal"
        TC_MASKS = "masks"
        TC_GRAYSCALE = "grayscale"

    class FunctionInputType(object):
        FUNCTION_INPUT_SCALAR = "scalar"
        FUNCTION_INPUT_VECTOR2 = "vector2"
        FUNCTION_INPUT_VECTOR3 = "vector3"
        FUNCTION_INPUT_VECTOR4 = "vector4"

    class BlendMode(object):
        BLEND_OPAQUE = "opaque"
        BLEND_MASKED = "masked"
        BLEND_TRANSLUCENT = "translucent"
        BLEND_ADDITIVE = "additive"

    class MaterialDomain(object):
        MD_SURFACE = "surface"
        MD_DEFERRED_DECAL = "deferred_decal"

    class MaterialProperty(object):
        MP_BASE_COLOR = "base_color"
        MP_NORMAL = "normal"
        MP_AMBIENT_OCCLUSION = "ambient_occlusion"
        MP_ROUGHNESS = "roughness"
        MP_METALLIC = "metallic"
        MP_SPECULAR = "specular"
        MP_EMISSIVE_COLOR = "emissive_color"
        MP_OPACITY_MASK = "opacity_mask"
        MP_OPACITY = "opacity"
        MP_SUBSURFACE_COLOR = "subsurface_color"

    class MaterialSamplerType(object):
        SAMPLERTYPE_COLOR = "color"
        SAMPLERTYPE_NORMAL = "normal"
        SAMPLERTYPE_MASKS = "masks"
        SAMPLERTYPE_LINEAR_COLOR = "linear_color"
        SAMPLERTYPE_VIRTUAL_COLOR = "virtual_color"
        SAMPLERTYPE_VIRTUAL_NORMAL = "virtual_normal"
        SAMPLERTYPE_VIRTUAL_MASKS = "virtual_masks"

    class MaterialEditingLibrary(object):
        expressions = []
        function_expressions = []
        connections = []
        scalar_calls = []
        vector_calls = []
        static_switch_calls = []
        texture_calls = []

        @classmethod
        def create_material_expression(cls, material_asset, expression_class, x, y):
            expression = expression_class()
            expression.x = x
            expression.y = y
            cls.expressions.append(expression)
            material_asset.expressions = getattr(material_asset, "expressions", []) + [expression]
            return expression

        @classmethod
        def create_material_expression_in_function(cls, function_asset, expression_class, x, y):
            expression = expression_class()
            expression.x = x
            expression.y = y
            cls.function_expressions.append(expression)
            function_asset.expressions = getattr(function_asset, "expressions", []) + [expression]
            return expression

        @classmethod
        def connect_material_property(cls, expression, output_name, material_property):
            cls.connections.append((getattr(expression, "parameter_name", ""), output_name, material_property))

        @classmethod
        def connect_material_expressions(cls, left, left_output, right, right_input):
            cls.connections.append((getattr(left, "parameter_name", ""), left_output, getattr(right, "parameter_name", ""), right_input))

        @classmethod
        def connect_material_expressions(cls, source_expression, source_output_name, target_expression, target_input_name):
            cls.connections.append(
                (
                    getattr(source_expression, "parameter_name", ""),
                    source_output_name,
                    getattr(target_expression, "parameter_name", getattr(target_expression, "output_name", "")),
                    target_input_name,
                )
            )

        @classmethod
        def delete_all_material_expressions(cls, material_asset):
            material_asset.expressions = []

        @classmethod
        def delete_material_expression(cls, material_asset, expression):
            cls.expressions = [item for item in cls.expressions if item is not expression]
            material_asset.expressions = [item for item in getattr(material_asset, "expressions", []) if item is not expression]

        @classmethod
        def delete_all_material_expressions_in_function(cls, function_asset):
            function_asset.expressions = []

        @staticmethod
        def recompile_material(material_asset):
            material_asset.recompiled = True

        @classmethod
        def set_material_instance_scalar_parameter_value(cls, material_instance, name, value):
            cls.scalar_calls.append((material_instance.asset_name, name, value))
            return True

        @classmethod
        def set_material_instance_vector_parameter_value(cls, material_instance, name, value):
            cls.vector_calls.append((material_instance.asset_name, name, value))
            return True

        @classmethod
        def set_material_instance_static_switch_parameter_value(cls, material_instance, name, value):
            cls.static_switch_calls.append((material_instance.asset_name, name, value))
            return True

        @classmethod
        def set_material_instance_texture_parameter_value(cls, material_instance, name, value):
            cls.texture_calls.append((material_instance.asset_name, name, getattr(value, "asset_path", "")))
            return True

        @staticmethod
        def update_material_instance(material_instance):
            material_instance.updated = True

    class EditorAssetLibrary(object):
        existing_assets = set()
        directories = []
        saved = []

        @classmethod
        def does_asset_exist(cls, asset_path):
            return asset_path in cls.existing_assets

        @classmethod
        def make_directory(cls, directory):
            cls.directories.append(directory)

        @classmethod
        def save_asset(cls, asset_path):
            cls.saved.append(asset_path)

        @classmethod
        def load_asset(cls, asset_path):
            if str(asset_path).startswith("/Engine/"):
                asset = FakeAsset()
                asset.asset_path = asset_path
                return asset
            if asset_path not in cls.existing_assets:
                return None
            asset = FakeAsset()
            asset.asset_path = asset_path
            return asset

        @classmethod
        def delete_asset(cls, asset_path):
            if asset_path not in cls.existing_assets:
                return False
            cls.existing_assets.remove(asset_path)
            cls.deleted.append(asset_path)
            return True

    def __init__(self, existing_assets=None):
        self.iterated_objects = []
        self.AssetToolsHelpers.asset_tools = FakeAssetTools()
        self.EditorAssetLibrary.existing_assets = set(existing_assets or [])
        self.EditorAssetLibrary.directories = []
        self.EditorAssetLibrary.saved = []
        self.EditorAssetLibrary.deleted = []
        self.MaterialEditingLibrary.expressions = []
        self.MaterialEditingLibrary.function_expressions = []
        self.MaterialEditingLibrary.connections = []
        self.MaterialEditingLibrary.scalar_calls = []
        self.MaterialEditingLibrary.vector_calls = []
        self.MaterialEditingLibrary.static_switch_calls = []
        self.MaterialEditingLibrary.texture_calls = []

        def object_iterator():
            return iter(self.iterated_objects)

        self.ObjectIterator = object_iterator


if __name__ == "__main__":
    unittest.main()
