"""Maya Static Prop MVP workflow orchestration."""

from __future__ import absolute_import

import os

from asset_forge.maya.adapter import MayaAdapter
from asset_forge.maya.fbx_exporter import MayaFbxExporter
from asset_forge.maya.manifest_writer import MayaManifestWriter
from asset_forge.shared.constants import TARGET_PLATFORM_HIGH_END_MOBILE
from asset_forge.shared.ai_analysis import LocalChineseSuggestionClient, analyze_validation
from asset_forge.shared.rule_validator import StaticPropRuleValidator
from asset_forge.shared.rules_schema import get_default_rules


class MayaStaticPropPipeline(object):
    """Run scan, validate, export, and manifest generation for one asset."""

    def __init__(self, adapter=None, exporter=None, validator=None, manifest_writer=None, rules=None, ai_client=None):
        self.rules = rules or get_default_rules()
        self.adapter = adapter or MayaAdapter()
        self.exporter = exporter or MayaFbxExporter()
        self.validator = validator or StaticPropRuleValidator(self.rules)
        self.manifest_writer = manifest_writer or MayaManifestWriter()
        self.ai_client = ai_client or LocalChineseSuggestionClient()

    def scan_selection(self):
        selection = self.adapter.get_current_selection()
        if not selection:
            raise RuntimeError("No selected asset")
        return self.scan_asset(selection[0])

    def scan_asset(self, asset_root):
        return self.adapter.scan_asset(asset_root, self.rules)

    def validate_scan(self, scan_result, target_platform=TARGET_PLATFORM_HIGH_END_MOBILE):
        return self.validator.validate(scan_result, target_platform)

    def export_asset(self, asset_root, output_dir, target_platform=TARGET_PLATFORM_HIGH_END_MOBILE, target_path="/Game/Props"):
        scan_result = self.scan_asset(asset_root)
        validation_result = self.validate_scan(scan_result, target_platform)
        if not validation_result.get("can_export", False):
            raise RuntimeError("Asset has blocking validation errors")

        asset_name = scan_result.get("asset_name", "Asset")
        fbx_path = os.path.join(output_dir, asset_name + ".fbx")
        manifest_path = os.path.join(output_dir, asset_name + "_manifest.json")

        self.exporter.export_asset(asset_root, fbx_path)
        manifest = self.manifest_writer.build(scan_result, validation_result, fbx_path, target_path)
        self.manifest_writer.write(manifest_path, manifest)

        return {
            "scan": scan_result,
            "validation": validation_result,
            "fbx_path": fbx_path,
            "manifest_path": manifest_path,
            "manifest": manifest,
        }

    def analyze(self, scan_result, validation_result):
        return analyze_validation(scan_result, validation_result, self.rules, self.ai_client)
