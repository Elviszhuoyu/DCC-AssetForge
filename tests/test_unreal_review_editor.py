import json
import tempfile
import unittest
from pathlib import Path

from asset_forge.unreal.review_editor import recent_review


class ReviewEditorHistoryTests(unittest.TestCase):
    def write_round(self, root, batch, revision, selected, time):
        path = root / batch / ("r%04d" % revision) / "review.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({
            "review_id": batch, "revision": revision, "created_at_utc": time,
            "assets": [{"asset_path": p} for p in selected],
            "json_path": "/another-project/review.json", "html_path": "/another-project/open.exe",
        }), encoding="utf-8")
        return path

    def test_overlap_requires_explicit_batch_choice_and_uses_its_latest_round(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            self.write_round(root, "first", 1, ["/Game/C"], "2026-01-01")
            p = self.write_round(root, "first", 2, ["/Game/C"], "2026-01-02")
            self.write_round(root, "another", 1, ["/Game/C", "/Game/A"], "2026-01-03")
            with self.assertRaises(ValueError):
                recent_review(root, ["/Game/C"])
            self.assertIsNone(recent_review(root, ["/Game/C"], lambda choices: None))
            report = recent_review(root, ["/Game/C"], lambda choices: next(
                entry for entry in choices if entry["review_id"] == "first"))
            self.assertEqual(report["revision"], 2)
            self.assertEqual(Path(report["json_path"]), p.resolve())
            self.assertEqual(Path(report["html_path"]), p.with_name("index.html").resolve())
