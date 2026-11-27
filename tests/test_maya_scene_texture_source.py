import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock

from asset_forge.maya.material_scanner import MayaMaterialScanner, valid_texture_count
from asset_forge.maya.pipeline import MayaStaticPropPipeline
from asset_forge.maya.project_settings import apply_rule_settings, load_project_settings, normalize_project_settings, save_project_settings


class MayaSceneTextureSourceTest(unittest.TestCase):
    def test_existing_scene_connections_count_unique_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image = root / "linked.png"
            image.touch()
            alias = root / "subdir" / ".." / image.name
            alias.parent.parent.mkdir()
            self.assertEqual(valid_texture_count(
                [{"path": str(image)}, {"path": str(alias)}, {"path": str(root / "missing.png")}, {}]
            ), 1)

    def test_scene_relative_path_uses_the_current_maya_workspace(self):
        cmds = Mock()
        cmds.getAttr.return_value = "sourceimages/linked.png"
        cmds.workspace.return_value = "E:/Mayaproject/sourceimages/linked.png"
        scanner = MayaMaterialScanner(cmds)
        self.assertEqual(scanner._file_texture_path("file1"), cmds.workspace.return_value)
        cmds.workspace.assert_called_once_with(expandName="sourceimages/linked.png")

    def _touch(self, name, usage, folder=None):
        path = (folder or self.root) / (name + ".png")
        path.touch()
        return {"path": str(path), "usage": usage, "source_type": "maya_file_node"}

    def _scan(self, materials):
        return {
            "asset_root": "|SM_Asset", "asset_name": "SM_Asset", "mesh_count": 1,
            "triangles": 220000, "material_slots": len(materials), "frozen_transform": True,
            "has_uv0": True, "has_lightmap_uv": True, "material_assignment": {},
            "materials": [{"name": "M_Asset_" + name, "textures": textures} for name, textures in materials.items()],
            "textures": [texture for textures in materials.values() for texture in textures],
        }

    def _fixture_pipeline(self, scan):
        adapter = Mock()
        adapter.scan_assets.return_value = scan
        exporter = Mock()
        exporter.export_asset.side_effect = lambda _root, path, **_kwargs: Path(path).write_bytes(b"fbx")
        return MayaStaticPropPipeline(adapter=adapter, exporter=exporter)

    def test_scene_only_infers_unique_same_set_from_real_linked_maps(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.root = Path(temporary)
            base = self._touch("T_Asset_A_Base_Color", "base_color")
            normal = self._touch("T_Asset_A_Normal", "normal")
            packed = self._touch("T_Asset_A_Occlusion_Roughness_Metallic", "packed_arm")
            self._touch("T_Asset_AB_ORM", "packed_arm")
            self._touch("T_Asset_B_ORM", "packed_arm")
            scan = self._scan({"A": [base, normal]})
            pipeline = self._fixture_pipeline(scan)
            result = pipeline.preflight_assets(["|SM_Asset"])
            self.assertEqual((result["scan"]["scene_texture_count"], result["scan"]["scene_inferred_texture_count"]), (2, 1))
            match = result["scan"]["textures"][-1]
            self.assertEqual(Path(match["path"]), Path(packed["path"]))
            self.assertEqual(match["selected_texture_set"], "T_Asset_A")
            self.assertEqual(match["source_type"], "maya_same_directory_packed")
            self.assertEqual(match["channels"], {"r": "ao", "g": "roughness", "b": "metallic"})
            self.assertFalse(any(row["id"] == "missing_packed_texture" for row in result["validation"]["checks"]))
            self.assertEqual(len(scan["materials"][0]["textures"]), 2)

    def test_no_guess_across_sets_directories_or_multiple_packed_matches(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.root = Path(temporary)
            other = self.root / "Other"
            other.mkdir()
            base = self._touch("T_Asset_A_BaseColor", "base_color")
            cross_set_normal = self._touch("T_Asset_Ax_Normal", "normal")
            cross_dir_normal = self._touch("T_Asset_A_Normal", "normal", other)
            normal = self._touch("T_Asset_A_Normal", "normal")
            self._touch("T_Asset_A_ORM", "packed_arm")
            self._touch("T_Asset_A_ARM", "packed_arm")
            for linked_normal in (cross_set_normal, cross_dir_normal, normal):
                with self.subTest(path=linked_normal["path"]):
                    pipeline = self._fixture_pipeline(self._scan({"A": [base, linked_normal]}))
                    result = pipeline.preflight_assets(["|SM_Asset"])
                    self.assertEqual(result["scan"]["scene_inferred_texture_count"], 0)
                    warning = next(row for row in result["validation"]["checks"] if row["id"] == "missing_packed_texture")
                    self.assertEqual((warning["object"], warning["status"]), ("M_Asset_A", "warning"))
                    self.assertIn("默认占位图", warning["diagnostic"]["export_impact"])
                    self.assertIn("分开的粗糙度与金属度", warning["diagnostic"]["fix_guidance"])
                    self.assertEqual(warning["diagnostic"]["actions"],
                                     [{"id": "choose_textures", "label": "选择外部贴图目录"}])
                    self.assertTrue(result["validation"]["can_export"])

    def test_only_missing_slot_warns_and_explicit_directory_overrides_scene(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.root = Path(temporary)
            external = self.root / "Override"
            external.mkdir()
            materials = {}
            for slot in ("A", "B"):
                materials[slot] = [self._touch("T_Asset_" + slot + "_BaseColor", "base_color"),
                                   self._touch("T_Asset_" + slot + "_Normal", "normal")]
                self._touch("T_Asset_" + slot + "_BaseColor", "base_color", external)
                self._touch("T_Asset_" + slot + "_Normal", "normal", external)
                self._touch("T_Asset_" + slot + "_ORM", "packed_arm", external)
            self._touch("T_Asset_A_ORM", "packed_arm")
            pipeline = self._fixture_pipeline(self._scan(materials))
            scene = pipeline.preflight_assets(["|SM_Asset"])
            self.assertEqual([row["object"] for row in scene["validation"]["checks"]
                              if row["id"] == "missing_packed_texture"], ["M_Asset_B"])
            overridden = pipeline.preflight_assets(["|SM_Asset"], texture_folder=str(external))
            self.assertEqual(overridden["scan"]["texture_selection_policy"]["reason"], "explicit_texture_folder")
            self.assertTrue(all(Path(row["path"]).parent == external for row in overridden["scan"]["textures"]))
            self.assertFalse(any(row["id"] == "missing_packed_texture" for row in overridden["validation"]["checks"]))

    def test_separate_maps_are_detected_only_in_the_anchored_material_set(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.root = Path(temporary)
            materials = {}
            for slot in ("A", "B"):
                materials[slot] = [self._touch("T_Asset_" + slot + "_BaseColor", "base_color"),
                                   self._touch("T_Asset_" + slot + "_Normal", "normal")]
                self._touch("T_Asset_" + slot + "_Roughness", "roughness")
            self._touch("T_Asset_A_Metalness", "metallic")
            self._touch("T_Asset_Bpart_Metallic", "metallic")
            output = self._fixture_pipeline(self._scan(materials)).preflight_assets(["|SM_Asset"])
            self.assertEqual(output["scan"]["scene_separate_texture_materials"], ["M_Asset_A"])
            checks = {row["object"]: row for row in output["validation"]["checks"]
                      if row["id"] == "missing_packed_texture"}
            self.assertEqual(len(checks), 2)
            self.assertTrue(checks["M_Asset_A"]["separate_texture_maps"])
            self.assertIn("已在这套贴图中找到", checks["M_Asset_A"]["diagnostic"]["fix_guidance"])
            self.assertFalse(checks["M_Asset_B"]["separate_texture_maps"])
            self.assertNotIn("已在这套贴图中找到", checks["M_Asset_B"]["diagnostic"]["fix_guidance"])

    def test_budget_and_normal_format_pass_through_preset_and_export(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.root = Path(temporary)
            base = self._touch("T_Asset_A_BaseColor", "base_color")
            normal = self._touch("T_Asset_A_Normal", "normal")
            self._touch("T_Asset_A_ORM", "packed_arm")
            pipeline = self._fixture_pipeline(self._scan({"A": [base, normal]}))
            settings_path = self.root / "artist_preset.json"
            save_project_settings(str(settings_path), {"triangle_budget": 250000, "material_slot_budget": 8, "normal_format": "opengl"})
            settings = load_project_settings(str(settings_path))
            self.assertEqual((settings["material_slot_budget"], settings["normal_format"]), (8, "opengl"))
            rules = apply_rule_settings(pipeline.rules, "pc", "SM_", settings["triangle_budget"], settings["material_slot_budget"])
            preflight = pipeline.preflight_assets(["|SM_Asset"], rules=rules)
            entry = next(item for item in preflight["scan"]["textures"] if item["usage"] == "normal")
            self.assertEqual(entry["normal_format"], "directx")
            self.assertNotIn("normal_format", normal)
            result = pipeline.export_assets(["|SM_Asset"], str(self.root / "Exports"), target_platform="pc", rules=rules,
                                            project_preset=settings, texture_import_policy={"normal_format": settings["normal_format"]})
            manifest = result["manifest"]
            self.assertEqual(manifest["asset_budgets"], {"triangles": 250000, "material_slots": 8})
            self.assertEqual(manifest["texture_import_policy"]["normal_format"], "opengl")
            self.assertEqual([row["normal_format"] for row in manifest["textures"] if row["usage"] == "normal"], ["opengl"])
            self.assertEqual(normalize_project_settings({"target_platform": "mobile"})["material_slot_budget"], 2)
            self.assertEqual(normalize_project_settings({})["normal_format"], "directx")
            normal["normal_format"] = "directx"
            result = pipeline.preflight_assets(["|SM_Asset"], texture_import_policy={"normal_format": "opengl"})
            entry = next(item for item in result["scan"]["textures"] if item["usage"] == "normal")
            self.assertEqual(entry["normal_format"], "directx")
