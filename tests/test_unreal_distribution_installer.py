import json
import os
import shutil
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from asset_forge.unreal import distribution_installer as installer


class TestUnrealDistributionInstaller(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        self.root = Path(workspace.name).resolve()
        self.project = self.root / "Fixture with spaces" / "小样.uproject"
        self.project.parent.mkdir()
        self.project.write_bytes(b'{"FileVersion":3,"EngineAssociation":"5.8","Plugins":[{"Name":"OtherPlugin","Enabled":false}]}\n')
        self.payload = self.root / "distribution" / "AssetForge"
        self.engine = self.root / "Selected UE 5.8.4"
        self.target = self.project.parent / "Plugins" / "AssetForge"
        self.modules = self.engine / "Engine" / "Binaries" / "Win64" / "UnrealEditor.modules"
        self._write(self.engine / "Engine" / "Build" / "Build.version",
                    {"MajorVersion": 5, "MinorVersion": 8, "PatchVersion": 4})
        self._write(self.modules, {"BuildId": installer.BUILD_ID})
        self._write(self.modules.parent / "UnrealEditor.exe")
        for relative in installer.REQUIRED_FILES:
            self._write(self.payload / relative)
        self._write(self.payload / "AssetForge.uplugin",
                    {"VersionName": installer.RELEASE_VERSION, "Version": 2,
                     "EngineVersion": "5.8.0", "Installed": True})
        self._write(self.payload / installer.MODULES_FILE,
                    {"BuildId": installer.BUILD_ID,
                     "Modules": {"AssetForgeEditor": Path(installer.MODULE_BINARY).name}})

        editor = patch.object(installer, "_editor_commands", return_value=[])
        self.editor_commands = editor.start()
        self.addCleanup(editor.stop)
        autodetect = patch.object(installer, "_discover_engines", return_value={"5.8": str(self.engine)})
        self.detect = autodetect.start()
        self.addCleanup(autodetect.stop)

    def _write(self, path, value=None):
        path.parent.mkdir(parents=True, exist_ok=True)
        if value is None:
            path.write_bytes(b"fixture payload")
        else:
            path.write_text(json.dumps(value), encoding="utf-8")

    def test_plan_autodetects_exact_engine_without_writes(self):
        original = self.project.read_bytes()
        self.editor_commands.return_value = ['"UnrealEditor.exe" "{}/Other.uproject"'.format(self.root)]
        result = installer.plan_install(self.project, self.payload)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(Path(result["engine_root"]), self.engine)
        self.assertEqual(result["build_id"], installer.BUILD_ID)
        self.assertFalse(result["requires_backup"])
        self.assertEqual(self.project.read_bytes(), original)
        self.assertFalse(self.target.parent.exists())
        self.assertFalse((self.project.parent / "Saved").exists())

    def test_manual_engine_selection_does_not_bypass_project_association_or_build_id(self):
        self.detect.return_value = {}
        result = installer.plan_install(self.project, self.payload)
        self.assertTrue(result["needs_engine_root"])
        result = installer.plan_install(self.project, self.payload, self.engine / "Engine")
        self.assertEqual(result["status"], "ready")

        self._write(self.modules, {"BuildId": "unexpected"})
        result = installer.plan_install(self.project, self.payload, self.engine)
        self.assertEqual(result["status"], "error")
        self.assertIn("构建编号", result["message"])
        self._write(self.project, {"FileVersion": 3, "EngineAssociation": "5.6"})
        result = installer.plan_install(self.project, self.payload, self.engine)
        self.assertIn("工程关联 UE 5.6", result["message"])
        self.assertFalse(self.target.parent.exists())

    def test_registered_guid_uses_the_registered_engine(self):
        identifier = "{098f85cc-14f1-46a0-a09d-87a484601644}"
        self.detect.return_value = {identifier: str(self.engine)}
        self._write(self.project, {"FileVersion": 3, "EngineAssociation": identifier.upper()})
        self.assertEqual(installer.plan_install(self.project, self.payload)["status"], "ready")
        other = self.root / "other"
        result = installer.plan_install(self.project, self.payload, other)
        self.assertIn("已关联另一处", result["message"])

    def test_payload_refuses_private_install_metadata_or_incorrect_module_map(self):
        self._write(self.payload / "Content" / "Python" / "config" / "asset_forge_install.json")
        result = installer.plan_install(self.project, self.payload)
        self.assertIn("不受支持的文件", result["message"])
        (self.payload / "Content" / "Python" / "config" / "asset_forge_install.json").unlink()
        self._write(self.payload / installer.MODULES_FILE,
                    {"BuildId": installer.BUILD_ID, "Modules": {"AssetForgeEditor": "other.dll"}})
        result = installer.plan_install(self.project, self.payload)
        self.assertIn("二进制不适用", result["message"])
        self.assertFalse(self.target.parent.exists())

    def test_plugin_compatibility_version_differs_from_exact_engine_version(self):
        descriptor_path = self.payload / "AssetForge.uplugin"
        descriptor = json.loads(descriptor_path.read_bytes())
        descriptor["EngineVersion"] = "5.8.4"
        self._write(descriptor_path, descriptor)
        self.assertEqual(installer.plan_install(self.project, self.payload)["status"], "error")

        descriptor["EngineVersion"] = "5.8.0"
        self._write(descriptor_path, descriptor)
        self.assertEqual(installer.plan_install(self.project, self.payload)["status"], "ready")

        self._write(self.engine / "Engine" / "Build" / "Build.version",
                    {"MajorVersion": 5, "MinorVersion": 8, "PatchVersion": 0})
        self.assertEqual(installer.plan_install(self.project, self.payload)["status"], "error")

    def test_detects_open_target_and_fails_closed_when_process_is_unreadable(self):
        original = self.project.read_bytes()
        for command in ['UnrealEditor.exe -project="{}" -log'.format(self.project), None]:
            self.editor_commands.return_value = [command]
            result = installer.install(self.project, self.payload)
            self.assertIn("请关闭目标工程", result["message"])
            self.assertEqual(self.project.read_bytes(), original)
            self.assertFalse(self.target.parent.exists())

    def test_rechecks_for_editor_after_staging_before_publish(self):
        self.editor_commands.side_effect = [[], ['UnrealEditor.exe "{}"'.format(self.project)]]
        result = installer.install(self.project, self.payload)
        self.assertEqual(result["status"], "error")
        self.assertFalse(self.target.exists())
        self.assertFalse(result["backup_dir"])

    def test_success_backs_up_both_targets_and_keeps_unrelated_project_settings(self):
        self._write(self.target / "prior-user-file.txt")
        original = self.project.read_bytes()
        self.assertTrue(installer.plan_install(self.project, self.payload)["requires_backup"])
        result = installer.install(self.project, self.payload)
        backup = Path(result["backup_dir"])
        self.assertEqual(result["status"], "success", result["message"])
        self.assertEqual(backup.parents[2], self.project.parent / "Saved")
        self.assertEqual((backup / self.project.name).read_bytes(), original)
        self.assertTrue((backup / "AssetForge" / "prior-user-file.txt").is_file())
        self.assertFalse((self.target / "prior-user-file.txt").exists())
        self.assertTrue((self.target / installer.MODULE_BINARY).is_file())
        self.assertEqual((self.target / installer.MODULE_BINARY).read_bytes(),
                         (self.payload / installer.MODULE_BINARY).read_bytes())
        self.assertEqual(json.loads(self.project.read_bytes())["Plugins"], [
            {"Name": "OtherPlugin", "Enabled": False},
            {"Name": "AssetForge", "Enabled": True},
        ])

    def test_existing_enabled_project_bytes_are_preserved(self):
        self._write(self.project, {"FileVersion": 3, "EngineAssociation": "5.8",
                                   "Plugins": [{"Name": "AssetForge", "Enabled": True, "TargetAllowList": ["Editor"]}]})
        original = self.project.read_bytes()
        result = installer.install(self.project, self.payload)
        self.assertEqual(result["status"], "success", result["message"])
        self.assertEqual(self.project.read_bytes(), original)

    def test_failed_descriptor_replace_restores_previous_plugin_and_exact_bytes(self):
        self._write(self.target / "prior-user-file.txt")
        original = self.project.read_bytes()
        replace = os.replace

        def fail_descriptor(source, destination):
            if destination == self.project:
                raise PermissionError("fixture: descriptor in use")
            return replace(source, destination)

        with patch.object(installer.os, "replace", side_effect=fail_descriptor):
            result = installer.install(self.project, self.payload)
        self.assertEqual(result["status"], "error")
        self.assertIn("已保留原工程和插件", result["message"])
        self.assertEqual(self.project.read_bytes(), original)
        self.assertTrue((self.target / "prior-user-file.txt").is_file())
        self.assertFalse((self.target / installer.MODULE_BINARY).exists())
        self.assertEqual((Path(result["backup_dir"]) / self.project.name).read_bytes(), original)

    def test_multi_payload_matches_exact_version_and_build_id_for_engine_install(self):
        multi = self.payload.parent / "Unreal"
        binary = multi / "5.8.4" / "AssetForge"
        shutil.copytree(self.payload, binary)
        descriptor_file = binary / "AssetForge.uplugin"
        descriptor = json.loads(descriptor_file.read_bytes())
        descriptor["FriendlyName"] = "DCC AssetForge"
        self._write(descriptor_file, descriptor)
        original = self.project.read_bytes()
        result = installer.install(None, multi, self.engine, engine_install=True)
        target = self.engine / "Engine" / "Plugins" / "Marketplace" / "AssetForge"
        self.assertEqual(result["status"], "success", result["message"])
        self.assertEqual(result["payload_mode"], "binary")
        self.assertTrue((target / installer.MODULE_BINARY).is_file())
        self.assertEqual(self.project.read_bytes(), original)
        self.assertFalse(self.target.exists())
        result = installer.uninstall(engine_root=self.engine, engine_install=True)
        self.assertEqual(result["status"], "success", result["message"])
        self.assertFalse(target.exists())
        self.assertEqual(self.project.read_bytes(), original)

    def test_build_id_mismatch_offers_project_source_and_preserves_user_preset(self):
        multi = self.payload.parent / "Unreal"
        binary = multi / "5.8.4" / "AssetForge"
        source = multi / "Source" / "AssetForge"
        shutil.copytree(self.payload, binary)
        shutil.copytree(self.payload, source)
        (source / installer.MODULE_BINARY).unlink()
        (source / installer.MODULES_FILE).unlink()
        self._write(source / installer.SOURCE_RULES)
        self._write(source / "AssetForge.uplugin", {
            "Version": 2, "VersionName": installer.RELEASE_VERSION, "FriendlyName": "DCC AssetForge",
        })
        self._write(self.modules, {"BuildId": "other-patch"})
        failed = installer.plan_install(self.project, multi)
        self.assertTrue(failed["source_available"])
        self.assertEqual(failed["status"], "error")
        engine_plan = installer.plan_install(None, multi, self.engine, source=True, engine_install=True)
        self.assertEqual(engine_plan["status"], "error")
        self.assertTrue(engine_plan["source_available"])
        preset = Path("UserPresets/Team.assetforge.json")
        self._write(self.target / preset)
        result = installer.install(self.project, multi, source=True)
        self.assertEqual(result["status"], "success", result["message"])
        self.assertEqual(result["payload_mode"], "source")
        self.assertTrue((self.target / installer.SOURCE_RULES).is_file())
        self.assertTrue((self.target / preset).is_file())
        self.assertFalse((self.target / installer.MODULE_BINARY).exists())
        result = installer.uninstall(self.project)
        self.assertEqual(result["status"], "success", result["message"])
        self.assertFalse(self.target.exists())
        self.assertTrue((Path(result["backup_dir"]) / "AssetForge" / preset).is_file())
        self.assertEqual(json.loads(self.project.read_bytes())["Plugins"], [
            {"Name": "OtherPlugin", "Enabled": False},
        ])

    def test_stock_asset_allowlist_covers_real_profiles_but_rejects_workshop_content(self):
        self.assertTrue(installer.payload_file_allowed("Content/Materials/M_AF_Environment_Master.uasset"))
        self.assertTrue(installer.payload_file_allowed("Content/Textures/T_AF_Preview_ARM_Metal.uasset"))
        self.assertFalse(installer.payload_file_allowed("Content/StaticMeshes/SM_SG552.uasset"))
        self.assertFalse(installer.payload_file_allowed("Binaries/Win64/UnrealEditor-AssetForgeEditor.pdb"))

