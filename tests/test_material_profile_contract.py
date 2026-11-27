from __future__ import absolute_import

import copy
import os
import shutil
import tempfile
import unittest

from asset_forge.shared.material_profile_contract import validate_material_profile_contract
from asset_forge.shared.material_profile_schema import get_default_material_profile
from asset_forge.shared.manifest_schema import read_manifest, write_manifest
from asset_forge.shared.sample_static_prop_package import create_offline_static_prop_package
from asset_forge.unreal.package_acceptance import validate_asset_forge_package


class MaterialProfileContractTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def _slot_variant_package(self):
        from asset_forge.shared.material_profile_schema import write_material_profiles
        package = create_offline_static_prop_package(self.temp_dir)
        manifest = package["manifest"]
        packed = copy.deepcopy(manifest["textures"][0])
        source = packed["path"]
        target = source.replace("_BaseColor.png", "_ORM.png")
        shutil.copyfile(source, target)
        packed.update(node="offline_arm", usage="packed_arm", parameter="ARM", compression="masks", srgb=False)
        for name in ("path", "source_path", "package_path"):
            packed[name] = target
        manifest["textures"].append(packed)
        manifest["materials"] = [{"name": n, "textures": manifest["textures"]} for n in ("M_Frame", "M_Cover")]
        manifest["material_slots"] = [{"name": m["name"], "index": i} for i, m in enumerate(manifest["materials"])]
        profile = get_default_material_profile("Props_Opaque_PBR")
        profile.update(name="Studio_Prop", allow_external_master_material=True,
                       material_variants={"coating": "/Game/Studio/M_Coating"},
                       material_slot_variants=[{"material": "M_Cover", "variant": "coating"}])
        manifest["material_profile"] = profile["name"]
        def validate():
            write_material_profiles(manifest["material_profiles_snapshot_path"], {"profiles": [profile]})
            write_manifest(package["manifest_path"], manifest)
            return validate_asset_forge_package(package["package_dir"])
        return profile, manifest, validate

    def test_slot_variant_from_package_snapshot_preserves_two_parents_with_shared_three_maps(self):
        profile, manifest, validate = self._slot_variant_package()
        report = validate()
        self.assertTrue(report["manifest_validation"]["can_import"], report["manifest_validation"]["issues"])
        plan = report["material_binding_plan"]
        first, cover = plan["materials"]
        self.assertEqual(first["texture_parameters"], cover["texture_parameters"])
        self.assertEqual(set(cover["texture_parameters"]), {"BaseColor", "Normal", "ARM"})
        self.assertEqual((first["parent_material"], cover["parent_material"]),
                         (profile["master_material"], "/Game/Studio/M_Coating"))
        self.assertEqual(cover["variant_source"], "source_material")
        self.assertEqual(plan["unique_material_instance_count"], 2)
        self.assertTrue(report["material_profile_contract_validation"]["can_accept"])
        self.assertTrue(report["gate_passed"], report["summary"]["blocking_checks"])

        manifest["materials"][1]["name"] = "M_Rim"
        manifest["material_slots"][1]["name"] = "M_Rim"
        shared = validate()
        self.assertTrue(shared["gate_passed"], shared["summary"]["blocking_checks"])
        self.assertTrue(all(m["parent_material"] == profile["master_material"] for m in shared["material_binding_plan"]["materials"]))

    def test_slot_variant_errors_block_package_gate_before_import(self):
        profile, manifest, validate = self._slot_variant_package()
        entry = profile["material_slot_variants"][0]
        for update, error in [
                ({"material_slot_variants": [dict(entry, variant="missing")]}, "Undeclared"),
                ({"material_slot_variants": [entry, dict(entry, variant="second")]}, "Duplicate"),
                ({"allow_external_master_material": False}, "External parent"),
                ({"allow_external_master_material": "false"}, "External parent"),
                ({"material_variants": {"coating": "/Game/../Other/M"}}, "Invalid parent")]:
            with self.subTest(update=update):
                previous = dict(profile)
                profile.update(update)
                report = validate()
                self.assertFalse(report["gate_passed"])
                self.assertFalse(report["manifest_validation"]["can_import"])
                self.assertIn(error, report["material_binding_plan"]["slot_variant_error"])
                profile.clear()
                profile.update(previous)
        for colliding in ("M_Cover", "MI_M_Cover"):
            with self.subTest(colliding=colliding):
                manifest["materials"][0]["name"] = colliding
                report = validate()
                self.assertFalse(report["gate_passed"])
                self.assertIn("Ambiguous", report["material_binding_plan"]["slot_variant_error"])

    def test_slot_variant_error_stops_preview_import_bootstrap_and_batch_even_without_strict_mode(self):
        from unittest.mock import Mock
        from asset_forge.unreal.package_acceptance import validate_all_asset_forge_packages
        from asset_forge.unreal.acceptance_runner import UnrealBatchPackageAcceptanceFlow, UnrealPackageAcceptanceFlow
        from asset_forge.unreal.pipeline import UnrealStaticMeshImportPipeline

        profile, manifest, validate = self._slot_variant_package()
        manifest["material_slots"].append({"name": "M_Cover", "index": 2})
        invalid = validate()
        self.assertIn("Ambiguous", invalid["mandatory_blockers"][0])
        validation_batch = validate_all_asset_forge_packages(self.temp_dir)
        self.assertFalse(validation_batch["gate_passed"])
        self.assertEqual(validation_batch["mandatory_blockers"], invalid["mandatory_blockers"])
        path = invalid["manifest_path"]
        importer = Mock()
        pipeline = UnrealStaticMeshImportPipeline(importer=importer)
        self.assertEqual(pipeline.dry_run_manifest(path)["status"], "failed")
        self.assertEqual(pipeline.import_from_manifest(path)["status"], "failed")
        importer.import_static_mesh.assert_not_called()
        flow = UnrealPackageAcceptanceFlow(import_pipeline=Mock())
        flow._run_auto_material_bootstrap = Mock()
        batch = UnrealBatchPackageAcceptanceFlow(flow).run(self.temp_dir, run_import=True, auto_bootstrap_material_assets=True)
        self.assertFalse(batch["gate_passed"])
        self.assertEqual(batch["mandatory_blockers"], invalid["mandatory_blockers"])
        self.assertFalse(batch["reports"][0]["gate_passed"])
        flow._run_auto_material_bootstrap.assert_not_called()
        flow.import_pipeline.import_from_manifest.assert_not_called()

    def test_opaque_pbr_checks_required_maps_per_material(self):
        profile = get_default_material_profile("Props_Opaque_PBR")
        plan = {"materials": [
            {"target_asset_path": "/Game/Test/MI_Body", "slots": {"packed_arm": "Body_ORM"}},
            {"target_asset_path": "/Game/Test/MI_Trim", "slots": {"normal": "Trim_Normal"}},
        ]}
        checks = validate_material_profile_contract(profile, plan)["checks"]
        missing = [(row["path"], row["message"]) for row in checks if row["id"] == "required_slot_texture"]
        self.assertEqual(len(missing), 4)
        self.assertTrue(any(path.endswith("MI_Trim") and "ARM" in msg for path, msg in missing))

    def test_packaged_profile_selects_project_parent_and_feature_branch(self):
        from asset_forge.shared.material_profile_schema import write_material_profiles
        from asset_forge.unreal.manifest_reader import UnrealManifestReader
        from asset_forge.unreal.material_binding_planner import UnrealMaterialBindingPlanner
        package = create_offline_static_prop_package(self.temp_dir)
        manifest = read_manifest(package["manifest_path"])
        profile = get_default_material_profile("Props_Opaque_PBR")
        profile.update(name="Studio", allow_external_master_material=True, master_material="/Game/Studio/M_Standard",
                       material_variants={"emissive": "/Game/Studio/M_Emissive"})
        snapshot = os.path.join(package["package_dir"], "studio_profiles.json")
        write_material_profiles(snapshot, {"profiles": [profile]})
        manifest.update(material_profile="Studio", material_profiles_snapshot_path=snapshot)
        write_manifest(package["manifest_path"], manifest)
        prepared = UnrealManifestReader().load(package["manifest_path"])
        self.assertTrue(prepared["can_import"], prepared["issues"])
        active = prepared["manifest"]
        active["materials"] = [{"name": "Trim", "textures": []}, {"name": "Display", "textures": [{"usage": "emissive"}]}]
        parents = UnrealMaterialBindingPlanner().plan(active, {})["materials"]
        self.assertEqual([row["parent_material"] for row in parents], ["/Game/Studio/M_Standard", "/Game/Studio/M_Emissive"])

    def test_declared_missing_snapshot_cannot_fall_back_to_installed_parent(self):
        from asset_forge.unreal.manifest_reader import UnrealManifestReader
        package = create_offline_static_prop_package(self.temp_dir)
        manifest = read_manifest(package["manifest_path"])
        manifest["material_profiles_snapshot_path"] = "absent_profiles.json"
        write_manifest(package["manifest_path"], manifest)
        result = UnrealManifestReader().load(package["manifest_path"])
        self.assertFalse(result["can_import"])
        self.assertTrue(any("snapshot is missing" in item for item in result["issues"]))

    def test_external_variant_uses_same_permission_as_default_parent(self):
        profile = get_default_material_profile("Props_Opaque_PBR")
        plan = {"materials": [{"parent_material": "/Game/Studio/M_Emission"}]}
        checks = validate_material_profile_contract(profile, plan)["checks"]
        self.assertTrue(any(c["id"] == "master_material_path" and c["status"] == "error" for c in checks))

    def test_legal_profile_contract_passes_with_material_plan(self):
        profile = get_default_material_profile("Props_Opaque_PainterUE_ARM")
        profile["material_network_status"] = "verified_pbr"
        plan = {
            "materials": [
                {
                    "target_asset_path": "/Game/Props/Materials/M_Crate",
                    "slots": {"base_color": "/Game/T_BaseColor"},
                    "texture_parameters": {"BaseColor": "/Game/T_BaseColor"},
                    "scalar_parameters": dict(profile["scalar_parameters"]),
                    "vector_parameters": dict(profile["vector_parameters"]),
                }
            ]
        }

        report = validate_material_profile_contract(profile, plan)

        self.assertEqual(report["status"], "pass")

    def test_missing_texture_parameter_warns(self):
        profile = copy.deepcopy(get_default_material_profile("Props_Opaque_PainterUE_ARM"))
        profile["texture_rules"][0]["parameter"] = ""

        report = validate_material_profile_contract(profile, {"materials": []})

        self.assertEqual(report["status"], "warning")
        self.assertTrue(any("缺少材质参数映射" in item["message"] for item in report["warnings"]))

    def test_bad_master_material_path_errors(self):
        profile = copy.deepcopy(get_default_material_profile("Props_Opaque_PainterUE_ARM"))
        profile["master_material"] = "/Game/AssetForge/Materials/M_Bad"

        report = validate_material_profile_contract(profile, {"materials": []})

        self.assertEqual(report["status"], "error")
        self.assertTrue(any("/AssetForge" in item["message"] for item in report["errors"]))

    def test_package_acceptance_includes_material_profile_contract(self):
        package = create_offline_static_prop_package(self.temp_dir)
        manifest = read_manifest(package["manifest_path"])
        manifest["material_profile"] = {
            "name": "Bad_Profile",
            "master_material": "/Game/AssetForge/M_Bad",
            "material_instance_dir": "{target_path}/Materials",
            "texture_dir": "{target_path}/Textures",
            "texture_rules": [],
            "scalar_parameters": {},
        }
        write_manifest(package["manifest_path"], manifest)

        report = validate_asset_forge_package(package["package_dir"])

        self.assertEqual(report["material_profile_contract_validation"]["status"], "error")
        self.assertIn("material_profile_contract", report["summary"]["blocking_checks"])

    def test_package_acceptance_warning_summary_excludes_pass_contract_messages(self):
        package = create_offline_static_prop_package(self.temp_dir)

        report = validate_asset_forge_package(package["package_dir"])

        warning_messages = [
            item["message"]
            for item in report["summary"]["warnings"]
            if item.get("source") == "material_profile_contract"
        ]
        self.assertTrue(warning_messages)
        self.assertFalse(any("base_color->BaseColor" in message for message in warning_messages))


if __name__ == "__main__":
    unittest.main()
