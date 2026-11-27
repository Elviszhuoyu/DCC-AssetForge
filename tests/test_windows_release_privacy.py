import hashlib
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

from scripts.audit_windows_assetforge_distribution import ReleaseAudit


class WindowsReleasePrivacyTest(unittest.TestCase):
    def test_scans_text_and_nested_binary_even_with_an_intact_checksum(self):
        private = r"Y:\localbuild\source\plugin.cpp"
        data = BytesIO()
        with ZipFile(data, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr("plugin.uasset", private.encode("utf-16-le"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            (root / "payload.zip").write_bytes(data.getvalue())
            (root / "manifest.txt").write_text("ReleaseTestUser", encoding="utf-8")
            checksums = [f"{hashlib.sha256(file.read_bytes()).hexdigest()}  {file.name}\n"
                         for file in root.iterdir()]
            (root / "SHA256SUMS.txt").write_text("".join(checksums), encoding="utf-8")
            with patch.dict("os.environ", {"USERNAME": "ReleaseTestUser"}):
                report = ReleaseAudit(("Y:/localbuild",)).scan(root)
            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["sha256_verified_files"], 2)
            self.assertEqual(report["entries"]["embedded_zip"], 1)
            self.assertEqual(report["privacy_findings"],
                             {"known_machine_root": 1, "windows_absolute_path": 1, "local_username": 1})


    def test_public_identity_never_exempts_absolute_paths_or_pdb_files(self):
        public = (
            "卓雨 (Elviszhuoyu)\n© 2026 Elviszhuoyu\n"
            "https://github.com/Elviszhuoyu/DCC-AssetForge/releases\n"
            "https://work.zhuoyulabs.com"
        )
        with patch.dict("os.environ", {"USERNAME": "Elviszhuoyu"}):
            audit = ReleaseAudit(("R:/Users/Elviszhuoyu",))
        for encoding in ("utf-8", "utf-16-le", "utf-16-be"):
            audit._scan_member("about.txt", public.encode(encoding), "extracted_file")
        self.assertFalse(audit.hits)

        leaked = public + "\nR:/Users/Elviszhuoyu/Home"
        audit._scan_member("report.pdb", leaked.encode("utf-16-le"), "embedded_zip")
        self.assertEqual(audit.hits, {
            "known_machine_root": 1, "local_username": 1, "windows_absolute_path": 1, "pdb_file": 1,
        })

        lookalike = "https://github.com/Elviszhuoyu/DCC-AssetForge-private"
        audit._scan_member("about.txt", lookalike.encode("utf-8"), "extracted_file")
        self.assertEqual(audit.hits["local_username"], 2)


    def test_default_config_gate_checks_packaged_and_nested_presets(self):
        data = BytesIO()
        with ZipFile(data, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr(
                "runtime/config/project_settings.example.json",
                b'{"ue_target_path": "/Game/Props"}',
            )
            archive.writestr("team.assetforge.json", b'{"ue_target_path": "/Game/AssetForgeQA"}')
        audit = ReleaseAudit(())
        audit._scan_member("Payload/Blender/extension.zip", data.getvalue(), "extracted_file")
        self.assertEqual(audit.hits, {"development_config": 1})
        self.assertTrue(audit.samples[0]["member"].endswith("!team.assetforge.json"))

    def test_public_release_rejects_even_an_empty_legacy_runtime_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Payload/InstallerRuntime").mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, "standalone"):
                ReleaseAudit(()).scan(root)
