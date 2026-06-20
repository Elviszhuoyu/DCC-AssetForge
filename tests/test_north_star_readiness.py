from __future__ import absolute_import

import shutil
import tempfile
import unittest

from asset_forge.shared.sample_static_prop_package import create_offline_static_prop_package
from asset_forge.unreal.capability_matrix import create_capability_matrix
from asset_forge.unreal.north_star_readiness import create_north_star_readiness
from asset_forge.unreal.stage_validation_bundle import collect_stage_validation_bundle


class NorthStarReadinessTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_default_matrix_keeps_real_ue_validation_not_full_score(self):
        readiness = create_north_star_readiness(capability_matrix=create_capability_matrix())
        items = dict((item["id"], item) for item in readiness["items"])

        self.assertEqual(items["real_ue_validation"]["score"], 0)
        self.assertEqual(items["real_ue_validation"]["status"], "manual_validation_required")
        self.assertLess(readiness["score"], 100)

    def test_missing_ue_evidence_is_reported_from_stage_bundle(self):
        package = create_offline_static_prop_package(self.temp_dir)
        bundle = collect_stage_validation_bundle(package["package_dir"])
        readiness = bundle["stages"]["north_star_readiness"]

        self.assertEqual(readiness["stage"], "north_star_readiness")
        self.assertTrue(any(item["id"] == "real_ue_validation" for item in readiness["items"]))
        self.assertTrue(readiness["warnings"])

    def test_offline_capabilities_score_but_do_not_complete_real_ue(self):
        package = create_offline_static_prop_package(self.temp_dir)
        bundle = collect_stage_validation_bundle(package["package_dir"])
        readiness = create_north_star_readiness(bundle, bundle["stages"]["capability_matrix"])
        items = dict((item["id"], item) for item in readiness["items"])

        self.assertGreater(readiness["score"], 50)
        self.assertEqual(items["package_protocol"]["status"], "pass")
        self.assertEqual(items["real_ue_validation"]["score"], 0)

    def test_dcc_compatibility_contract_is_visible_without_raising_maturity(self):
        readiness = create_north_star_readiness(capability_matrix=create_capability_matrix())
        items = dict((item["id"], item) for item in readiness["items"])
        dcc = items["dcc_compatibility_contract"]

        self.assertEqual(dcc["weight"], 0)
        self.assertEqual(dcc["score"], 0)
        self.assertEqual(dcc["status"], "warning")
        self.assertIn("Maya is the MVP real export path.", dcc["evidence"])
        self.assertIn("Blender and 3ds Max are roadmap/contract-only DCC targets.", dcc["evidence"])
        self.assertIn("No Blender/3ds Max real-chain validation is claimed in MVP.", dcc["missing_evidence"])

    def test_real_ue_string_marker_does_not_complete_real_ue_dimension(self):
        readiness = create_north_star_readiness({"tas_102_real_ue_evidence": "provided"})
        items = dict((item["id"], item) for item in readiness["items"])

        self.assertEqual(items["real_ue_validation"]["status"], "manual_validation_required")
        self.assertEqual(items["real_ue_validation"]["score"], 0)
        self.assertEqual(items["real_ue_validation"]["evidence"], [])
        self.assertTrue(readiness["manual_validation_required"])

    def test_structured_real_ue_evidence_marker_completes_real_ue_dimension(self):
        readiness = create_north_star_readiness(
            {
                "tas_102_real_ue_evidence": {
                    "is_tas_102_completion_evidence": True,
                    "status": "pass",
                    "gate_passed": True,
                    "can_accept": True,
                    "post_import_validation": {"status": "pass"},
                }
            }
        )
        items = dict((item["id"], item) for item in readiness["items"])

        self.assertEqual(items["real_ue_validation"]["status"], "pass")
        self.assertEqual(items["real_ue_validation"]["score"], 100)
        self.assertIn("tas_102_real_ue_evidence", items["real_ue_validation"]["evidence"])
        self.assertEqual(readiness["manual_validation_required"], [])

    def test_real_ue_stage_must_be_explicit_completion_evidence(self):
        bundle = {
            "stages": {
                "accept_flow": {
                    "status": "pass",
                    "gate_passed": True,
                    "can_accept": True,
                    "post_import_validation": {"status": "pass"},
                }
            }
        }

        readiness = create_north_star_readiness(bundle)
        items = dict((item["id"], item) for item in readiness["items"])

        self.assertEqual(items["real_ue_validation"]["status"], "manual_validation_required")

        bundle["stages"]["accept_flow"]["is_tas_102_completion_evidence"] = True
        readiness = create_north_star_readiness(bundle)
        items = dict((item["id"], item) for item in readiness["items"])

        self.assertEqual(items["real_ue_validation"]["status"], "pass")
        self.assertIn("accept_flow", items["real_ue_validation"]["evidence"])


if __name__ == "__main__":
    unittest.main()
