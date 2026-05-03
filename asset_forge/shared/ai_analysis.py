"""AI analysis interface and local suggestion provider.

The local provider is deterministic and offline. It keeps the AI advice layer
usable before binding a real model provider.
"""

from __future__ import absolute_import

from asset_forge.shared.constants import CHECK_STATUS_ERROR, CHECK_STATUS_WARNING
from asset_forge.shared.rules_schema import get_default_rules


class AiAnalysisInput(object):
    """Serializable input object for AI analysis providers."""

    def __init__(self, scan_result, validation_result, project_rules=None, target_platform=None):
        self.scan_result = scan_result or {}
        self.validation_result = validation_result or {}
        self.project_rules = project_rules or get_default_rules()
        self.target_platform = target_platform or self.validation_result.get("target_platform", "")

    def to_dict(self):
        return {
            "asset_name": self.scan_result.get("asset_name", ""),
            "asset_type": self.validation_result.get("asset_type", ""),
            "target_platform": self.target_platform,
            "score": self.validation_result.get("score", 0),
            "status": self.validation_result.get("status", ""),
            "can_export": self.validation_result.get("can_export", False),
            "checks": self.validation_result.get("checks", []),
            "scan": self.scan_result,
            "project_rules": self.project_rules,
        }


class AiAnalysisClient(object):
    """Provider interface for analysis suggestions."""

    provider_name = "base"

    def analyze(self, analysis_input):
        raise NotImplementedError


class LocalChineseSuggestionClient(AiAnalysisClient):
    """Offline Chinese suggestion provider for v0.1."""

    provider_name = "local_zh"

    def analyze(self, analysis_input):
        data = analysis_input.to_dict()
        checks = data.get("checks", [])
        failed_checks = [item for item in checks if item.get("status") in (CHECK_STATUS_ERROR, CHECK_STATUS_WARNING)]

        if not failed_checks:
            return self._pass_message(data)

        lines = [
            "?? {0} ???? {1}???? {2}?".format(
                data.get("asset_name", ""),
                data.get("score", 0),
                data.get("status", ""),
            ),
            "???????????????????? / ?????",
            "",
        ]

        for item in failed_checks:
            lines.append(self._suggestion_for_check(item, data))

        if not data.get("can_export", False):
            lines.append("")
            lines.append("????????????? error ??????")
        else:
            lines.append("")
            lines.append("????? warning ????????????????????")

        return "\n".join([line for line in lines if line is not None])

    def _pass_message(self, data):
        return "\n".join(
            [
                "?? {0} ???? {1}?????????".format(
                    data.get("asset_name", ""),
                    data.get("score", 0),
                ),
                "???? FBX ??? Unreal ?????",
                "AI ????????????????",
            ]
        )

    def _suggestion_for_check(self, item, data):
        check_id = item.get("id")
        label = item.get("label", check_id)
        message = item.get("message", "")

        handlers = {
            "name_prefix": "????????? SM_ ????? SM_Crate_01???? Unreal Static Mesh ?????",
            "mesh_exists": "???????????????????? polygon mesh?",
            "empty_mesh": "??? mesh???????????????????? shape?",
            "frozen_transform": "? Maya ??? Freeze Transformations??? Translate/Rotate ???Scale ? 1?",
            "illegal_scale": "?????? 0 ???????????? UE ?????????????????",
            "triangle_budget": "?????? {0} ?????????????????????????????".format(
                data.get("target_platform", "")
            ),
            "material_slots": "??????? ID??? draw call?????????????????????",
            "uv0": "???? UV0???????????????",
            "lightmap_uv": "???????? UV???? UE ???????? Lightmap UV?",
            "hidden_objects": "??????????????? manifest ??? FBX ??????",
            "history_nodes": "?? Delete History???????????????????",
        }

        suggestion = handlers.get(check_id, "????????????????????")
        return "- [{0}] {1}?{2} ???{3}".format(item.get("status", ""), label, message, suggestion)


def build_analysis_input(scan_result, validation_result, project_rules=None, target_platform=None):
    return AiAnalysisInput(scan_result, validation_result, project_rules, target_platform)


def analyze_validation(scan_result, validation_result, project_rules=None, client=None):
    analysis_input = build_analysis_input(
        scan_result,
        validation_result,
        project_rules,
        validation_result.get("target_platform", ""),
    )
    active_client = client or LocalChineseSuggestionClient()
    return active_client.analyze(analysis_input)
