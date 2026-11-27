import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from asset_forge.unreal import review_annotations
from asset_forge.unreal.review_workbench import ReviewWorkbench


class ReviewAnnotationsTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.batch = self.root / "batch1"
        self.first = self.batch / "r0001"
        self.first.mkdir(parents=True)
        self.rows = [{"asset_path": p, "status": "pass", "asset_type": "StaticMesh", "facts": {}, "issues": []}
                     for p in ("/Game/Meshes/B", "/Game/Meshes/C")]
        self.b = self.rows[0]["asset_path"]
        self.report = {"review_id": self.batch.name, "revision": 1, "created_at_utc": "2026-10-01",
                       "assets": self.rows, "scanned_paths": [r["asset_path"] for r in self.rows], "policy": {}}
        (self.first / "review.json").write_text(json.dumps(self.report))
        (self.first / "index.html").write_text("first")
        self.ui = self.open()

    def open(self):
        ui = ReviewWorkbench(None, self.root)
        ui._set_report(self.report, self.b)
        return ui

    def act(self, action, **args):
        self.ui.act(action, json.dumps(args))

    def test_multiple_labels_groups_and_collapsed_state_survive_reopen_and_partial_rescan(self):
        before = (self.first / "review.json").read_bytes()
        self.assertFalse((self.batch / "workbench.json").exists())
        self.act("create_group", name="核心道具")
        group = self.ui.view()["groups"][0]["id"]
        self.act("move_asset", path=self.b, group=group)
        self.act("rename_group", group=group, name="外包待修")
        self.act("toggle_group", group=group, collapsed=True)
        for name, color in (("S级", "#0099bb"), ("道具", "#ACAAFF")):
            self.act("create_tag", path=self.b, color=color, name=name)
        self.ui = self.open()
        view = self.ui.view()
        self.assertEqual(view["groups"], [{"id": group, "name": "外包待修", "collapsed": True}])
        self.assertEqual(view["assets"][0]["group"], group)
        self.assertEqual(view["assets"][0]["tags"], [t["id"] for t in view["tags"]])
        tag = view["tags"][0]["id"]
        self.act("update_tag", tag=tag, color="#de8f20", name="优先")
        self.act("set_tag", path=self.b, tag=tag, assigned=False)
        self.act("set_tag", path=self.b, tag=tag, assigned=True)
        self.act("set_tag", path=self.b, tag=tag, assigned=True)
        self.act("move_asset", path=self.b, group="")
        self.report = dict(self.report, revision=2, created_at_utc="2026-10-03", scanned_paths=[self.rows[1]["asset_path"]])
        view = self.open().view()
        self.assertEqual(view["updated_at"], "2026-10-01")
        self.assertEqual(view["assets"][0]["group"], "")
        self.assertEqual(view["assets"][0]["tags"].count(tag), 1)
        self.assertEqual(view["tags"][0]["color"], "#DE8F20")
        self.assertEqual((self.first / "review.json").read_bytes(), before)

    def test_simultaneous_editors_merge_unrelated_changes_and_failed_edits_are_atomic(self):
        second = self.open()
        self.act("create_group", name="核心")
        second.act("create_tag", json.dumps({"name": "优先", "color": "#aa0000", "path": self.b}))
        self.assertEqual(len(second.view()["groups"]), 1)
        sidecar = self.batch / "workbench.json"
        before = sidecar.read_bytes()
        with review_annotations._exclusive(self.batch), self.assertRaisesRegex(ValueError, "另一个编辑器"):
            self.act("create_group", name="其他")
        self.assertEqual(sidecar.read_bytes(), before)
        for action, payload in [("create_group", {"name": "核心"}),
                                ("create_tag", {"name": "错误", "color": "white"}),
                                ("set_tag", {"path": "/Game/Missing", "tag": "id"}),
                                ("move_asset", {"path": self.b, "group": "unknown"})]:
            with self.assertRaises(ValueError):
                self.act(action, **payload)
            self.assertEqual(sidecar.read_bytes(), before)
        with patch.object(review_annotations.os, "replace", side_effect=OSError), self.assertRaises(OSError):
            self.act("create_group", name="其他")
        self.assertEqual(sidecar.read_bytes(), before)
        self.assertFalse(list(self.batch.glob("*.tmp")))

    def test_concurrent_tag_fields_merge_and_conflicting_rename_refreshes_the_form(self):
        self.act("create_tag", name="道具", color="#EEEEEE")
        tag = self.ui.view()["tags"][0]["id"]
        other = self.open()
        original = {"tag": tag, "original_name": "道具", "original_color": "#EEEEEE"}
        other.act("update_tag", json.dumps(dict(original, name="核心道具", color="#EEEEEE")))
        self.act("update_tag", name="道具", color="#226644", **original)
        with self.assertRaisesRegex(ValueError, "另一编辑器"):
            other.act("update_tag", json.dumps(dict(original, name="优先", color="#EEEEEE")))
        self.assertEqual(other.view()["tags"][0], {"id": tag, "name": "核心道具", "color": "#226644"})

    def test_incomplete_historical_round_does_not_break_the_current_review(self):
        (self.first / "review.json").write_text(json.dumps(dict(self.report, scanned_paths=None)))
        self.report = dict(self.report, revision=2, created_at_utc="2026-10-03", scanned_paths=[self.b])
        self.ui = self.open()
        self.assertEqual(self.ui.view()["updated_at"], "2026-10-03")
        self.ui.act("select", self.rows[1]["asset_path"])
        self.assertEqual(self.ui.view()["updated_at"], "")

    def test_damaged_sidecar_does_not_block_review_or_get_overwritten(self):
        sidecar = self.batch / "workbench.json"
        sidecar.write_text('{"version":2}')
        self.ui = self.open()
        self.assertIn("原文件", self.ui.view()["message"])
        self.ui.message = "已复验当前资产"
        self.assertIn("已复验", self.ui.view()["message"])
        self.assertEqual(self.ui.view()["path"], self.b)
        with self.assertRaises(ValueError):
            self.act("create_group", name="测试")
        self.assertEqual(sidecar.read_text(), '{"version":2}')

    def test_current_round_html_and_verified_physical_directory(self):
        content = self.root / "Content"
        folder = content / "Meshes"
        folder.mkdir(parents=True)
        (folder / "B.uasset").write_bytes(b"test fixture")
        self.ui.ue = SimpleNamespace(Paths=SimpleNamespace(project_content_dir=lambda: str(content),
                                                            convert_relative_path_to_full=str))
        view = self.ui.view()
        self.assertEqual(view["source_dir"], str(folder))
        self.assertTrue(view["can_report"])
        with patch("os.startfile", create=True) as launch:
            self.ui.act("open_report")
            launch.assert_called_once_with(str(self.first / "index.html"))
        (self.first / "index.html").unlink()
        self.assertFalse(self.ui.view()["can_report"])
        with self.assertRaisesRegex(ValueError, "HTML"):
            self.ui.act("open_report")
