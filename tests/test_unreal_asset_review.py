import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from asset_forge.unreal.review_diagnostics import ACTIONS, REVIEW_RULES, diagnostic
from asset_forge.shared.material_profile_schema import get_material_profile

from asset_forge.unreal.asset_review import apply_fixes, scan_assets


class EditorObject:
    def __init__(self, path, kind, **properties):
        self.path = path
        self.kind = kind
        self.properties = properties

    def get_class(self):
        return SimpleNamespace(get_name=lambda: self.kind)

    def get_path_name(self):
        return self.path + "." + self.path.rsplit("/", 1)[-1]

    def get_editor_property(self, field):
        return self.properties[field]

    def set_editor_property(self, field, value):
        self.properties[field] = value


class AssetReviewTest(unittest.TestCase):
    def setUp(self):
        self.mesh = EditorObject("/Game/Props/SM_Body", "StaticMesh")
        self.material = EditorObject("/Game/Props/MI_Body", "MaterialInstanceConstant")
        self.parent = EditorObject("/Game/Studio/M_Opaque", "Material")
        self.texture = EditorObject("/Game/Props/T_Surface", "Texture2D", srgb=True, compression_settings="TC_MASKS")
        slot = EditorObject("", "", material_slot_name="M_Body", material_interface=self.material)
        self.mesh.properties["static_materials"] = [slot]
        self.mesh.get_num_triangles = lambda lod: 12
        self.mesh.get_num_lods = lambda: 1
        self.material.get_base_material = lambda: self.parent
        self.objects = {asset.path: asset for asset in [self.mesh, self.material, self.parent, self.texture]}
        self.links = {self.texture.path: [self.material.path], self.material.path: [self.mesh.path]}
        self.saved = Mock(return_value=True)
        self.dirty = []
        self.tags = {"Dimensions": "4096x2048"}
        self.registry = SimpleNamespace(
            get_referencers=lambda p, options: self.links.get(p, []),
            get_assets_by_package_name=lambda p, disk: [
                SimpleNamespace(asset_class_path=SimpleNamespace(asset_name=self.objects[p].kind))] if p in self.objects else [],
            is_search_all_assets=lambda: True, is_loading_assets=lambda: False)
        self.ue = SimpleNamespace(
            EditorAssetLibrary=SimpleNamespace(load_asset=self.objects.get, get_tag_values=lambda p: self.tags,
                                               save_loaded_asset=self.saved),
            AssetRegistryHelpers=SimpleNamespace(get_asset_registry=lambda: self.registry),
            AssetRegistryDependencyOptions=lambda **kwargs: kwargs,
            EditorLoadingAndSavingUtils=SimpleNamespace(get_dirty_content_packages=lambda: self.dirty,
                                                         get_dirty_map_packages=lambda: []),
            TextureCompressionSettings=SimpleNamespace(TC_DEFAULT="TC_DEFAULT", TC_MASKS="TC_MASKS"),
            MaterialEditingLibrary=SimpleNamespace(
                get_texture_parameter_names=lambda material: ["ARM"],
                get_material_default_texture_parameter_value=lambda parent, parameter: None,
                get_material_instance_texture_parameter_value=lambda material, parameter: self.texture,
                get_used_textures=lambda parent: []),
            StaticMeshEditorSubsystem=object(),
            get_editor_subsystem=lambda _: SimpleNamespace(get_simple_collision_count=lambda m: 0))
        self.policy = {"max_triangles": 20, "parameter_roles": {"ARM": "packed_arm"}}

    def review(self):
        return scan_assets([self.mesh.get_path_name(), self.mesh.path], self.policy, self.ue)

    def test_every_review_rule_has_an_artist_diagnostic_and_action(self):
        for rule, (_, enabled, template, _, _) in REVIEW_RULES.items():
            self.assertTrue(enabled)
            self.assertIn("{actual}", template)
            self.assertIn("{expected}", template)
            for severity in ("blocked", "warning", "pass", "needs_review"):
                with self.subTest(rule=rule, severity=severity):
                    view = diagnostic(rule, "实测测试值", "期望测试值", severity)
                    self.assertEqual(view["severity"], severity)
                    self.assertIn("实测测试值", view["summary"])
                    if rule != "texture.source_size":
                        self.assertIn("期望测试值", view["summary"])
                    self.assertTrue(all(view[field] for field in ("title", "export_impact", "fix_guidance")))
                    self.assertIn(view["action_kind"], ACTIONS)

    def test_painter_profile_recognizes_the_actual_pack_map_parameter(self):
        profile = get_material_profile("Props_Opaque_PainterUE_ARM")
        self.material.get_base_material = lambda: EditorObject(profile["master_material"], "Material")
        base_color = EditorObject("/Game/Props/T_BaseColor", "Texture2D", srgb=True, compression_settings="TC_DEFAULT")
        normal = EditorObject("/Game/Props/T_Normal", "Texture2D", srgb=False, compression_settings="TC_NORMALMAP")
        actual = {"Base Color": base_color, "Normal Map": normal, "Pack Map": self.texture}
        self.objects.update({asset.path: asset for asset in (base_color, normal)})
        self.ue.MaterialEditingLibrary.get_texture_parameter_names = lambda material: list(actual)
        self.ue.MaterialEditingLibrary.get_material_instance_texture_parameter_value = lambda material, name: actual[name]
        self.texture.set_editor_property("srgb", False)
        imported = scan_assets([self.mesh.path], {"material_profile": profile["name"],
                                                 "material_profile_snapshot": profile}, self.ue)
        stock = scan_assets([self.mesh.path], unreal_module=self.ue)
        self.assertEqual(stock["assets"][0]["issues"][0]["rule_id"], "texture.role")
        self.assertIn("没有匹配", stock["assets"][0]["issues"][0]["diagnostic"]["summary"])
        row = imported["assets"][0]
        self.assertEqual(row["status"], "pass")
        self.assertEqual(row["issues"], [])
        self.assertEqual(imported["policy"]["material_profile_snapshot"], profile)
        observed_passes = {check["rule_id"] for check in row["passed"]}
        self.assertTrue({"mesh.lod0_triangles", "mesh.slot_material", "texture.srgb",
                         "texture.compression", "texture.role"}.issubset(observed_passes))
        self.assertFalse(observed_passes & {"mesh.lod_count", "mesh.simple_collision"})
        self.assertEqual(sum(check["rule_id"] == "material.required_texture" for check in row["passed"]), 3)
        self.saved.assert_not_called()

    def test_required_default_is_warning_and_only_registered_optional_default_is_ignored(self):
        from asset_forge.unreal.material_package_schema import DEFAULT_TEXTURE_PATHS

        profile = get_material_profile("Props_Opaque_PainterUE_ARM")
        self.material.get_base_material = lambda: EditorObject(profile["master_material"], "Material")
        base_color = EditorObject("/Game/Props/T_BaseColor", "Texture2D", srgb=True, compression_settings="TC_DEFAULT")
        normal = EditorObject("/Game/Props/T_Normal", "Texture2D", srgb=False, compression_settings="TC_NORMALMAP")
        default_arm = EditorObject(DEFAULT_TEXTURE_PATHS["packed_arm"], "Texture2D")
        default_opacity = EditorObject(DEFAULT_TEXTURE_PATHS["opacity_mask"], "Texture2D")
        unknown = EditorObject("/Game/Props/T_AF_Default_OpacityMask", "Texture2D", srgb=False, compression_settings="TC_MASKS")
        roleless = {"TintLUT": unknown}
        actual = {"Base Color": base_color, "Normal Map": normal, "Pack Map": default_arm,
                  "Opacity Map": default_opacity, **roleless}
        self.objects.update({obj.path: obj for obj in actual.values()})
        editing = self.ue.MaterialEditingLibrary
        editing.get_texture_parameter_names = lambda material: list(actual)
        editing.get_material_default_texture_parameter_value = lambda _, name: (
            actual[name] if name in ("Pack Map", "Opacity Map") else None
        )
        editing.get_material_instance_texture_parameter_value = lambda _, name: actual[name]
        editing.get_used_textures = lambda _: [default_arm, default_opacity, unknown]

        scan = scan_assets([self.mesh.path], {"material_profile": profile["name"]}, self.ue)
        row = scan["assets"][0]
        self.assertEqual(row["status"], "needs_review")
        required = [issue for issue in row["issues"] if issue["rule_id"] == "material.required_texture"]
        self.assertEqual([(issue["object_path"], issue["slot"], issue["severity"]) for issue in required],
                         [(self.material.path, "ARM", "warning")])
        self.assertIn("MI_Body 的 ARM 槽仍使用母材质默认贴图", required[0]["diagnostic"]["summary"])
        self.assertEqual(required[0]["diagnostic"]["action_kind"], "open_material")
        self.assertNotIn(default_arm.path, row["facts"]["texture_facts"])
        self.assertNotIn(default_opacity.path, row["facts"]["texture_facts"])
        self.assertTrue(any(issue["rule_id"] == "texture.role" and issue["object_path"] == unknown.path
                            for issue in row["issues"]))
        self.assertEqual(sum(check["rule_id"] == "material.required_texture" for check in row["passed"]), 2)
        self.saved.assert_not_called()

    def test_selected_mesh_proposes_old_new_and_actual_impact_and_rechecks_only_approved(self):
        report = self.review()
        self.assertEqual(len(report["assets"]), 1)
        row = report["assets"][0]
        self.assertEqual(row["status"], "blocked")
        self.assertTrue(row["fully_fixable"])
        self.assertEqual(row["facts"]["lod0_triangles"], 12)
        self.assertEqual(row["facts"]["texture_facts"][self.texture.path]["source_size"], [4096, 2048])
        self.assertEqual([i["rule_id"] for i in row["issues"]], ["texture.srgb"])
        self.assertEqual(row["issues"][0]["diagnostic"]["action_kind"], "preview_fix")
        self.assertEqual(row["issues"][0]["diagnostic"]["severity"], "blocked")
        self.assertNotIn("texture.srgb", {check["rule_id"] for check in row["passed"]})
        plan = report["fix_plan"][0]
        self.assertTrue(plan["can_apply"])
        self.assertEqual(plan["referencers"], sorted([self.material.path, self.mesh.path]))
        self.assertEqual(plan["mesh_owners"], [self.mesh.path])
        self.assertTrue(plan["old"]["srgb"])
        self.assertFalse(plan["new"]["srgb"])
        self.assertEqual(apply_fixes(report, [], self.ue)["changed_count"], 0)
        fixed = apply_fixes(report, [self.texture.get_path_name()], self.ue)
        self.assertEqual(fixed["changed_count"], 1)
        self.saved.assert_called_once_with(self.texture, False)
        self.assertEqual(fixed["review"]["assets"][0]["status"], "pass")
        self.assertNotEqual(row["revision"], fixed["review"]["assets"][0]["revision"])
        self.assertEqual(fixed["review"]["fix_plan"], [])
        self.assertEqual(apply_fixes(report, [self.texture.path], self.ue)["changed_count"], 0)
        self.assertEqual(self.saved.call_count, 1)

    def test_changed_reference_or_old_setting_cancels_previously_approved_write(self):
        preview = self.review()
        other = EditorObject("/Game/Elsewhere/SM_Other", "StaticMesh")
        self.objects[other.path] = other
        self.links[self.material.path].append(other.path)
        refused = apply_fixes(preview, [self.texture.path], self.ue)
        self.assertEqual(refused["changed_count"], 0)
        self.assertFalse(refused["review"]["fix_plan"][0]["can_apply"])
        self.links[self.material.path].remove(other.path)
        self.texture.set_editor_property("compression_settings", "TC_DEFAULT")
        self.assertEqual(apply_fixes(preview, [self.texture.path], self.ue)["changed_count"], 0)
        self.saved.assert_not_called()

    def test_any_unknown_reference_or_dirty_package_requires_manual_review(self):
        for kind in ("unknown_ref", "unresolved_ref", "dirty", "registry_incomplete"):
            with self.subTest(kind=kind):
                self.links[self.material.path] = [self.mesh.path]
                self.dirty.clear()
                self.registry.is_loading_assets = lambda: False
                if kind == "unknown_ref":
                    self.links[self.material.path].append("/Game/Unknown")
                if kind == "unresolved_ref":
                    self.links[self.material.path] = []
                if kind == "dirty":
                    self.dirty.append(SimpleNamespace(get_name=lambda: "/Game/Unrelated/Unsaved"))
                if kind == "registry_incomplete":
                    self.registry.is_loading_assets = lambda: True
                report = self.review()
                self.assertFalse(report["fix_plan"][0]["can_apply"])
                self.assertTrue(report["assets"][0]["incomplete"])
                self.assertEqual(apply_fixes(report, [self.texture.path], self.ue)["changed_count"], 0)
        self.saved.assert_not_called()

    def test_readable_budget_slots_dimensions_collision_and_unknown_bindings_survive_together(self):
        self.tags.clear()
        self.policy.update(max_triangles=5, min_lods=2, require_simple_collision=True, max_material_slots=1)
        self.mesh.properties["static_materials"].append(EditorObject("", "", material_slot_name="M_Trim",
                                                                      material_interface=None))
        row = self.review()["assets"][0]
        self.assertEqual(row["status"], "blocked")
        self.assertTrue(row["incomplete"])
        self.assertFalse(row["fully_fixable"])
        issues = {i["rule_id"]: i for i in row["issues"]}
        self.assertEqual(issues["mesh.lod0_triangles"]["actual"], 12)
        self.assertEqual(issues["mesh.simple_collision"]["actual"], 0)
        self.assertEqual(issues["mesh.slot_material"]["slot"], "M_Trim")
        self.assertEqual(issues["texture.source_size"]["severity"], "unknown")
        self.assertIn("mesh.lod_count", issues)
        self.assertIn("mesh.material_slots", issues)

    def test_untrusted_and_conflicting_roles_are_manual_even_for_a_normal_looking_name(self):
        self.policy.pop("parameter_roles")
        report = self.review()
        self.assertEqual(report["assets"][0]["status"], "needs_review")
        self.assertEqual(report["fix_plan"], [])
        self.policy.update(parameter_roles={"ARM": "packed_arm"}, texture_roles={self.texture.path: "normal"})
        report = self.review()
        self.assertEqual(report["fix_plan"], [])
        self.assertEqual(report["issues"][0]["actual"], ["normal", "packed_arm"])

    def test_selected_texture_with_explicit_role_and_no_references(self):
        self.links.clear()
        policy = {"texture_roles": {self.texture.get_path_name(): "packed_arm"}}
        review = scan_assets([self.texture.path], policy, self.ue)
        self.assertEqual(review["fix_plan"][0]["mesh_owners"], [])
        self.assertTrue(review["fix_plan"][0]["can_apply"])
        self.assertEqual(apply_fixes(review, [self.texture.path], self.ue)["changed_count"], 1)
        self.assertEqual(self.saved.call_count, 1)

    def test_standalone_texture_reads_declared_material_role_but_external_mesh_prevents_writes(self):
        report = scan_assets([self.texture.path], self.policy, self.ue)
        self.assertEqual(report["assets"][0]["facts"]["role"], "packed_arm")
        self.assertEqual(report["fix_plan"][0]["mesh_owners"], [self.mesh.path])
        self.assertFalse(report["fix_plan"][0]["can_apply"])
        self.assertFalse(report["assets"][0]["fully_fixable"])
        self.assertEqual(apply_fixes(report, [self.texture.path], self.ue)["changed_count"], 0)

    def test_all_mesh_users_selected_and_same_role_are_safe(self):
        other = EditorObject("/Game/Elsewhere/SM_Other", "StaticMesh", **self.mesh.properties)
        other.get_num_triangles = self.mesh.get_num_triangles
        other.get_num_lods = self.mesh.get_num_lods
        self.objects[other.path] = other
        self.links[self.material.path].append(other.path)
        report = scan_assets([self.mesh.path, other.path], self.policy, self.ue)
        self.assertTrue(all(row["fully_fixable"] for row in report["assets"]))
        self.assertEqual(report["fix_plan"][0]["mesh_owners"], sorted([self.mesh.path, other.path]))
        self.assertEqual(apply_fixes(report, [self.texture.path], self.ue)["changed_count"], 1)
        self.saved.assert_called_once()

    def test_commandlet_waits_for_index_before_loading_the_first_mesh(self):
        searched = []
        self.registry.is_search_all_assets = lambda: bool(searched)
        self.registry.search_all_assets = lambda synchronous: searched.append(synchronous)
        self.ue.EditorAssetLibrary.load_asset = lambda path: self.objects[path] if searched else None
        self.assertEqual(self.review()["assets"][0]["asset_type"], "StaticMesh")
        self.assertEqual(searched, [True])

    def test_stock_world_grid_and_project_default_material_are_rejected_at_the_slot(self):
        for path in ("/Engine/EngineMaterials/WorldGridMaterial", "/Game/Studio/M_Default"):
            with self.subTest(path=path):
                self.policy["default_materials"] = ["/Game/Studio/M_Default"]
                self.mesh.properties["static_materials"][0].properties["material_interface"] = EditorObject(path, "Material")
                row = self.review()["assets"][0]
                self.assertEqual(row["status"], "blocked")
                self.assertEqual([issue["rule_id"] for issue in row["issues"]], ["mesh.slot_material"])

    def test_save_failure_restores_the_original_state(self):
        self.saved.return_value = False
        report = self.review()
        result = apply_fixes(report, [self.texture.path], self.ue)
        self.assertEqual(result["changed_count"], 0)
        self.assertEqual(result["changes"][0]["status"], "failed")
        self.assertTrue(self.texture.get_editor_property("srgb"))
        self.assertEqual(result["review"]["assets"][0]["status"], "blocked")


if __name__ == "__main__":
    unittest.main()

