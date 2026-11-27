import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from scripts import install_assetforge_maya as maya_install
from scripts.build_dcc_install_payload import stage
from scripts.audit_windows_assetforge_distribution import check_setup_executable


class DccReleasePayloadTest(unittest.TestCase):

    def test_public_setup_rejects_legacy_launcher_or_32bit_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            launcher = Path(directory) / "DCC-AssetForge-Setup.exe"
            sample = bytearray(2048)
            sample[:2] = b"MZ"
            sample[60] = 128
            sample[128:132] = b"PE\0\0"
            sample[132:134] = b"\x4c\x01"
            launcher.write_bytes(sample)
            with self.assertRaisesRegex(ValueError, "x64"):
                check_setup_executable(launcher)
            sample[132:134] = b"\x64\x86"
            sample[152:154] = b"\x0b\x02"
            launcher.write_bytes(sample)
            with self.assertRaisesRegex(ValueError, "WPF"):
                check_setup_executable(launcher)

    def test_stage_contains_portable_runtime_and_licenses_for_both_hosts(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory).resolve()
            package = stage(output)
            self.assertEqual(package["version"], "0.2.0")
            self.assertTrue(Path(package["maya"]).is_file())

            maya_root = output / "Payload" / "Maya"
            version, files = maya_install._payload_paths(maya_root)
            names = {path.relative_to(maya_root).as_posix() for path in files}
            self.assertEqual(version, "0.2.0")
            self.assertIn("Plugins/AssetForge/Resources/Workbench/web/THIRD-PARTY.txt", names)
            self.assertIn("Plugins/AssetForge/Resources/Workbench/brand/af_shelf.png", names)
            self.assertNotIn("integrations/maya_mcp_runtime/AGENTS.md", names)
            self.assertFalse(any("/docs/" in name for name in names))

            with ZipFile(package["blender"]) as archive:
                zipped = set(archive.namelist())
                self.assertIsNone(archive.testzip())
                self.assertIn("LICENSE", zipped)
                self.assertIn("blender_manifest.toml", zipped)
                self.assertIn("_asset_forge_bootstrap.py", zipped)
                self.assertIn("runtime/asset_forge/__init__.py", zipped)
                self.assertIn("runtime/config/material_profiles.json", zipped)
                manifest = archive.read("blender_manifest.toml").decode("utf-8").splitlines()
                tagline = next(line.split('"')[1] for line in manifest if line.startswith("tagline ="))
                self.assertTrue(tagline[-1].isalnum())

            manifest_file = maya_root / maya_install.DISTRIBUTION_MANIFEST
            payload = json.loads(manifest_file.read_text(encoding="utf-8"))
            payload["files"]["../outside.py"] = "0" * 64
            manifest_file.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ValueError):
                maya_install._payload_paths(maya_root)

    def test_maya_shelf_uses_native_pref_dir_over_third_party_search_list(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory).resolve()
            prefs = app / "2024" / "zh_CN" / "prefs"

            class MayaPaths:
                def internalVar(self, userPrefDir=False, userShelfDir=False):
                    if userPrefDir:
                        return str(prefs)
                    if userShelfDir:
                        return "C:/SystemPlugin/shelves;" + str(prefs / "shelves")
                    raise AssertionError("Expected Maya preference directory lookup")

            shelf = maya_install._user_shelf_file(MayaPaths(), app)
            self.assertEqual(shelf, prefs / "shelves" / "shelf_AssetForge.mel")
            with self.assertRaises(RuntimeError):
                maya_install._user_shelf_file(MayaPaths(), app / "other-profile")


if __name__ == "__main__":
    unittest.main()
