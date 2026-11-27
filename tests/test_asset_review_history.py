import json
import tempfile
import unittest
from pathlib import Path

from asset_forge.unreal.review_history import record_review


def issue(rule, actual):
    return {"rule_id": rule, "object_path": "/Game/Props/T_One", "actual": actual,
            "expected": "符合预设", "suggestion": "<定位对象>", "owner": "美术"}


def asset(name, issues=(), incomplete=False):
    return {"asset_path": "/Game/Props/" + name, "revision": name + str(len(issues)),
            "status": "blocked" if issues else "needs_review" if incomplete else "pass",
            "incomplete": incomplete, "issues": list(issues)}


class TestReviewHistory(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)

    def record(self, assets, prev=None, policy=None):
        return record_review({"assets": assets, "policy": policy or {}}, self.root,
                             previous=prev["json_path"] if prev else None)

    def test_partial_round_preserves_baseline_and_compares_issue_identities(self):
        first = self.record([asset("A"), asset("B", [issue("srgb", True)]), asset("C", [issue("budget", 500)])])
        initial_html = Path(first["html_path"]).read_bytes()
        second = self.record([asset("B"), asset("C", [issue("budget", 420), issue("slot", None)])], first)
        changes = second["changes"]
        self.assertEqual([i["before"]["rule_id"] for i in changes["resolved"]], ["srgb"])
        self.assertEqual([i["after"]["rule_id"] for i in changes["new"]], ["slot"])
        self.assertEqual(changes["persisting"][0]["before"]["actual"], 500)
        self.assertEqual(changes["persisting"][0]["after"]["actual"], 420)
        third = self.record([asset("C")], second)
        self.assertEqual(len(third["changes"]["resolved"]), 2)
        self.assertEqual(len(third["changes_since_first"]["resolved"]), 2)
        self.assertEqual(first["assets"][0], third["assets"][0])
        self.assertEqual(Path(first["html_path"]).read_bytes(), initial_html)
        html = Path(third["html_path"]).read_text(encoding="utf-8")
        self.assertIn("沿用上一轮", html)
        self.assertIn("../r0001/index.html", html)
        self.assertIn("&lt;定位对象&gt;", html)
        self.assertEqual(json.loads(Path(third["json_path"]).read_text(encoding="utf-8")), third)
        with self.assertRaises(FileExistsError):
            self.record([asset("B")], first)

    def test_unknown_readback_does_not_resolve_or_forget_an_old_issue(self):
        first = self.record([asset("A", [issue("budget", 900)])])
        second = self.record([asset("A", [issue("readback", None)], True)], first)
        self.assertEqual(len(second["changes"]["resolved"]), 0)
        self.assertEqual(second["changes"]["unverified"][0]["before"]["rule_id"], "budget")
        third = self.record([asset("A")], second)
        self.assertIn("budget", [i["before"]["rule_id"] for i in third["changes"]["resolved"]])

    def test_conflicting_identities_and_policy_change_do_not_create_a_revision(self):
        with self.assertRaises(ValueError):
            self.record([asset("A"), asset("A")])
        with self.assertRaises(ValueError):
            self.record([asset("A", [issue("budget", 100), issue("budget", 200)])])
        first = self.record([asset("A")], policy={"budget": 100})
        with self.assertRaises(ValueError):
            self.record([asset("A")], first, {"budget": 200})
        self.assertEqual(list(Path(first["html_path"]).parent.parent.glob("r0002")), [])
