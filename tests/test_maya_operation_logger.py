from __future__ import absolute_import

import json
import os
import shutil
import tempfile
import unittest

from asset_forge.maya.operation_logger import MayaOperationLogger, latest_log_path, latest_log_summary, logs_dir, read_latest_log_tail, repo_root


class MayaOperationLoggerTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_logger_writes_latest_log_and_structured_json_line(self):
        logger = MayaOperationLogger(root=self.temp_dir)

        entry = logger.log("scan_texture_folder", "success", inputs={"texture_set": "a1"}, outputs={"matched_count": 3})

        self.assertTrue(os.path.exists(latest_log_path(self.temp_dir)))
        with open(latest_log_path(self.temp_dir), "r", encoding="utf-8") as stream:
            line = stream.readlines()[-1]
        data = json.loads(line)
        self.assertEqual(data["operation"], "scan_texture_folder")
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["inputs"]["texture_set"], "a1")
        self.assertTrue(entry["log_path"].endswith("latest_maya.log"))

    def test_default_log_root_is_project_reports_logs(self):
        self.assertEqual(os.path.normcase(logs_dir()), os.path.normcase(os.path.join(repo_root(), "AssetForgeReports", "logs")))

    def test_temp_log_root_does_not_write_default_latest(self):
        default_latest = latest_log_path()
        before_exists = os.path.exists(default_latest)
        before_mtime = os.path.getmtime(default_latest) if before_exists else None

        MayaOperationLogger(root=self.temp_dir).log("unit_test", "success")

        self.assertTrue(os.path.exists(latest_log_path(self.temp_dir)))
        self.assertEqual(os.path.exists(default_latest), before_exists)
        if before_exists:
            self.assertEqual(os.path.getmtime(default_latest), before_mtime)

    def test_unicode_path_remains_utf8_in_latest_log(self):
        logger = MayaOperationLogger(root=self.temp_dir)
        path = "X:/Examples/DCCAssetForge/测试/Test01"

        logger.log("scan_model", "success", inputs={"export_root": path}, outputs={"note": "正式 Maya 日志路径生成验证"})

        with open(latest_log_path(self.temp_dir), "r", encoding="utf-8") as stream:
            raw = stream.read()
        self.assertIn("测试", raw)
        self.assertIn("正式 Maya 日志路径生成验证", raw)
        self.assertNotIn(_mojibake_from_text("测试"), raw)
        data = json.loads(raw.splitlines()[-1])
        self.assertEqual(data["inputs"]["export_root"], path)

    def test_mojibake_path_is_repaired_before_write(self):
        logger = MayaOperationLogger(root=self.temp_dir)

        mojibake = "E:/" + _mojibake_from_text("测试") + "/Test01"
        logger.log("scan_model", "success", inputs={"export_root": mojibake})

        with open(latest_log_path(self.temp_dir), "r", encoding="utf-8") as stream:
            raw = stream.read()
        self.assertIn("测试", raw)
        self.assertNotIn(_mojibake_from_text("测试"), raw)

    def test_latest_tail_reads_recent_entries_without_large_log_wall(self):
        logger = MayaOperationLogger(root=self.temp_dir)
        logger.log("scan_model", "success", outputs={"asset_name": "SM_A"})
        logger.log("preflight", "warning", outputs={"asset_name": "SM_B"})

        entries = read_latest_log_tail(self.temp_dir, 1)
        summary = latest_log_summary(self.temp_dir, 1)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["operation"], "preflight")
        self.assertEqual(summary[0]["operation"], "preflight")
        self.assertIn("asset=SM_B", summary[0]["details"])

    def test_latest_log_mirror_is_capped_to_recent_entries(self):
        logger = MayaOperationLogger(root=self.temp_dir)

        for index in range(205):
            logger.log("scan_model", "success", outputs={"asset_name": "SM_{0:03d}".format(index)})

        with open(latest_log_path(self.temp_dir), "r", encoding="utf-8") as stream:
            lines = [line for line in stream.readlines() if line.strip()]
        first = json.loads(lines[0])
        last = json.loads(lines[-1])

        self.assertEqual(len(lines), 200)
        self.assertEqual(first["outputs"]["asset_name"], "SM_005")
        self.assertEqual(last["outputs"]["asset_name"], "SM_204")


def _mojibake_from_text(text):
    return text.encode("utf-8").decode("gbk", "ignore")


if __name__ == "__main__":
    unittest.main()
