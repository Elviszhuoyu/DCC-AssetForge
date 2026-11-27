import os
from datetime import date, timedelta
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from asset_forge.maya.web_workbench import dispatch
from asset_forge.shared.workbench_cache import existing_cache_directory, manage_cache


class WorkbenchCacheTest(unittest.TestCase):
    def test_preview_and_clear_only_disposable_files_of_the_current_host(self):
        with tempfile.TemporaryDirectory() as temporary:
            reports = Path(temporary) / "AssetForgeReports"
            logs = reports / "logs"
            maya_cache = reports / "workbench_cache" / "maya"
            unreal_cache = reports / "workbench_cache" / "unreal"
            for directory in (logs, maya_cache, unreal_cache):
                directory.mkdir(parents=True)
            today = date.today()
            old = today - timedelta(days=2)
            old_stamp = old.strftime("%Y%m%d")

            def write(path, content=b"old"):
                path.write_bytes(content)
                if content == b"old":
                    os.utime(path, (946684800, 946684800))
                return path

            removable = [write(logs / ("asset_forge_maya_" + old_stamp + ".jsonl")),
                         write(maya_cache / "workbench_validation.json")]
            retained = [
                write(logs / ("asset_forge_maya_" + today.strftime("%Y%m%d") + ".jsonl")),
                write(logs / "latest_maya.log"),
                write(logs / ("asset_forge_unreal_" + old_stamp + ".jsonl")),
                write(reports / "project_preset.json"),
                write(logs / "source.ma"),
                write(maya_cache / "workbench_mesh.uasset"),
                write(maya_cache / "workbench_texture.png"),
                write(maya_cache / "client_export.json"),
                write(maya_cache / "workbench_open_session.json", b"new"),
                write(unreal_cache / "workbench_validation.json"),
            ]
            preview = manage_cache("maya", log_directory=logs)
            self.assertEqual(preview["bytes"], 15)
            self.assertEqual(preview["eligible_files"], 2)
            self.assertEqual(preview["eligible_bytes"], 6)
            directories = preview["directories"]
            self.assertEqual([item["id"] for item in directories], ["logs", "reports"])
            self.assertEqual([Path(item["path"]) for item in directories], [logs, maya_cache])
            self.assertEqual([item["bytes"] for item in directories], [9, 6])
            self.assertEqual([item["eligible_bytes"] for item in directories], [3, 3])
            self.assertTrue(all(item["exists"] for item in directories))
            self.assertTrue(all(path.is_file() for path in removable + retained))
            result = manage_cache("maya", clear=True, log_directory=logs)
            self.assertEqual(result["removed_files"], 2)
            self.assertEqual(result["removed_bytes"], 6)
            self.assertEqual(result["failed_files"], 0)
            self.assertEqual(result["eligible_files"], 0)
            self.assertEqual(result["eligible_bytes"], 0)
            self.assertEqual(result["bytes"], 9)
            self.assertEqual([item["bytes"] for item in result["directories"]], [6, 3])
            self.assertEqual([item["eligible_files"] for item in result["directories"]], [0, 0])
            self.assertTrue(all(not path.exists() for path in removable))
            self.assertTrue(all(path.is_file() for path in retained))

    def test_maya_open_resolves_only_existing_cache_ids_and_does_not_create_folders(self):
        with tempfile.TemporaryDirectory() as temporary:
            logs = Path(temporary) / "AssetForgeReports" / "logs"
            logs.mkdir(parents=True)
            report_cache = logs.parent / "workbench_cache" / "maya"
            directories = manage_cache("maya", log_directory=logs)["directories"]
            self.assertEqual(directories[1]["status"], "missing")
            self.assertFalse(directories[1]["exists"])
            self.assertFalse(report_cache.exists())
            self.assertIsNone(existing_cache_directory("maya", str(logs), log_directory=logs))

            desktop = Mock()
            qurl = Mock()
            qurl.fromLocalFile.side_effect = lambda path: path
            window = SimpleNamespace(action_button={}, logger=SimpleNamespace(log_dir=logs),
                                     web=SimpleNamespace(route="preferences", cache={}),
                                     skin=SimpleNamespace(core=SimpleNamespace(QUrl=qurl),
                                                          gui=SimpleNamespace(QDesktopServices=desktop)))
            dispatch(window, "openCacheDirectory", {"id": "../"})
            dispatch(window, "openCacheDirectory", {"id": "reports"})
            desktop.openUrl.assert_not_called()
            self.assertFalse(report_cache.exists())
            dispatch(window, "openCacheDirectory", {"id": "logs"})
            desktop.openUrl.assert_called_once_with(str(logs))
            self.assertNotIn("open_error", window.web.cache)

            report_cache.mkdir(parents=True)
            dispatch(window, "openCacheDirectory", {"id": "reports"})
            desktop.openUrl.assert_called_with(str(report_cache))
            self.assertEqual(desktop.openUrl.call_count, 2)

    def test_hardlinks_to_other_data_are_not_candidates(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            logs = root / "AssetForgeReports" / "logs"
            logs.mkdir(parents=True)
            source = root / "model.ma"
            source.write_bytes(b"source")
            os.utime(source, (946684800, 946684800))
            link = logs / "asset_forge_maya_20000101.jsonl"
            try:
                os.link(source, link)
            except OSError as exc:
                self.skipTest(str(exc))
            self.assertEqual(manage_cache("maya", clear=True, log_directory=logs)["removed_files"], 0)
            self.assertEqual(source.read_bytes(), b"source")
            self.assertTrue(link.is_file())
