"""Planned Skeletal Mesh validation and scoring."""

from __future__ import absolute_import

from asset_forge.shared.constants import (
    ASSET_TYPE_SKELETAL_MESH,
    CHECK_STATUS_ERROR,
    CHECK_STATUS_PASS,
    CHECK_STATUS_WARNING,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    TARGET_PLATFORM_HIGH_END_MOBILE,
)


DEFAULT_SKELETAL_RULES = {
    "name_prefix": "SK_",
    "max_influences": 4,
    "require_root_joint": True,
    "require_skin_cluster": True,
    "allow_warning_export": True,
    "block_export_on_error": True,
    "scoring": {
        "error_penalty": 20,
        "warning_penalty": 8,
        "min_score": 0,
    },
}


class SkeletalMeshRuleValidator(object):
    """Validate planned Skeletal Mesh scan results without entering export flow."""

    def __init__(self, rules=None):
        self.rules = rules or dict(DEFAULT_SKELETAL_RULES)

    def validate(self, scan_result, target_platform=TARGET_PLATFORM_HIGH_END_MOBILE):
        checks = [
            self._check_name_prefix(scan_result),
            self._check_root_joint(scan_result),
            self._check_skin_cluster(scan_result),
            self._check_max_influences(scan_result),
            self._check_lod_order(scan_result),
            self._check_material_slots(scan_result),
        ]
        summary = self._summary(checks)
        status = CHECK_STATUS_PASS
        if summary["errors"]:
            status = CHECK_STATUS_ERROR
        elif summary["warnings"]:
            status = CHECK_STATUS_WARNING

        return {
            "asset_name": scan_result.get("asset_name", ""),
            "asset_type": ASSET_TYPE_SKELETAL_MESH,
            "target_platform": target_platform,
            "status": status,
            "score": self._score(checks),
            "can_export": self._can_export(summary),
            "checks": checks,
            "summary": summary,
        }

    def _check_name_prefix(self, scan_result):
        prefix = self.rules.get("name_prefix", "SK_")
        asset_name = scan_result.get("asset_name", "")
        return self._result(
            "sk_prefix",
            "Skeletal Mesh ??",
            asset_name.startswith(prefix),
            SEVERITY_ERROR,
            asset_name,
            prefix,
            "Skeletal Mesh ????? {0} ??".format(prefix),
        )

    def _check_root_joint(self, scan_result):
        required = self.rules.get("require_root_joint", True)
        root_joint = scan_result.get("root_joint", "")
        return self._result(
            "has_root_joint",
            "Root Joint",
            (not required) or bool(root_joint),
            SEVERITY_ERROR,
            root_joint,
            "required",
            "?? root joint",
        )

    def _check_skin_cluster(self, scan_result):
        required = self.rules.get("require_skin_cluster", True)
        count = scan_result.get("skin_cluster_count", 0)
        return self._result(
            "has_skin_cluster",
            "Skin Cluster",
            (not required) or count > 0,
            SEVERITY_ERROR,
            count,
            ">= 1",
            "?? skinCluster",
        )

    def _check_max_influences(self, scan_result):
        limit = self.rules.get("max_influences", 4)
        value = scan_result.get("max_influences", 0)
        return self._result(
            "max_influences",
            "Max Influences",
            value > 0 and value <= limit,
            SEVERITY_WARNING,
            value,
            limit,
            "????????????",
        )

    def _check_lod_order(self, scan_result):
        lod_names = [item.get("name", "") for item in scan_result.get("lods", [])]
        indexed_names = ["LOD{0}".format(index) for index in range(len(lod_names))]
        return self._result(
            "lod_order",
            "LOD Order",
            not lod_names or lod_names == indexed_names,
            SEVERITY_WARNING,
            lod_names,
            indexed_names,
            "LOD ????????",
        )

    def _check_material_slots(self, scan_result):
        slots = scan_result.get("material_slots", 0)
        return self._result(
            "material_slots",
            "Material Slots",
            slots > 0,
            SEVERITY_WARNING,
            slots,
            ">= 1",
            "??????",
        )

    def _result(self, check_id, label, passed, severity, value, limit, fail_message):
        return {
            "id": check_id,
            "label": label,
            "status": CHECK_STATUS_PASS if passed else severity,
            "severity": severity,
            "value": value,
            "limit": limit,
            "message": "??" if passed else fail_message,
        }

    def _summary(self, checks):
        summary = {"errors": 0, "warnings": 0, "passes": 0}
        for item in checks:
            if item["status"] == CHECK_STATUS_ERROR:
                summary["errors"] += 1
            elif item["status"] == CHECK_STATUS_WARNING:
                summary["warnings"] += 1
            elif item["status"] == CHECK_STATUS_PASS:
                summary["passes"] += 1
        return summary

    def _score(self, checks):
        score = 100
        scoring = self.rules.get("scoring", {})
        for item in checks:
            if item["status"] == CHECK_STATUS_ERROR:
                score -= scoring.get("error_penalty", 20)
            elif item["status"] == CHECK_STATUS_WARNING:
                score -= scoring.get("warning_penalty", 8)
        return max(score, scoring.get("min_score", 0))

    def _can_export(self, summary):
        if summary["errors"] and self.rules.get("block_export_on_error", True):
            return False
        if summary["warnings"] and not self.rules.get("allow_warning_export", True):
            return False
        return True
