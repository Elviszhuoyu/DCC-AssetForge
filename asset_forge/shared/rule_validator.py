# -*- coding: utf-8 -*-
"""Static Prop rule validation and scoring."""

from __future__ import absolute_import, unicode_literals

from asset_forge.shared.constants import (
    ASSET_TYPE_STATIC_PROP,
    CHECK_STATUS_ERROR,
    CHECK_STATUS_PASS,
    CHECK_STATUS_WARNING,
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    TARGET_PLATFORM_HIGH_END_MOBILE,
)
from asset_forge.shared.rules_schema import get_default_rules


def _missing_uv_meshes(coordinate_counts, channel):
    return sorted(mesh for mesh, counts in coordinate_counts.items() if len(counts) <= channel or not counts[channel])


def summarize_mesh_uvs(uv_sets, coordinate_counts):
    """Keep channel indices intact, including an empty first layer followed by a valid second layer."""
    missing_base = _missing_uv_meshes(coordinate_counts, 0)
    missing_lightmap = _missing_uv_meshes(coordinate_counts, 1)
    return {
        "uv_sets": uv_sets,
        "uv_coordinate_counts": coordinate_counts,
        "has_uv0": bool(coordinate_counts) and not missing_base,
        "has_lightmap_uv": bool(coordinate_counts) and not missing_lightmap,
        "missing_uv0_meshes": missing_base,
        "missing_lightmap_uv_meshes": missing_lightmap,
    }


class StaticPropRuleValidator(object):
    """Validate scanner results against executable Static Prop rules."""

    def __init__(self, rules=None):
        all_rules = rules or get_default_rules()
        self.rules = all_rules.get(ASSET_TYPE_STATIC_PROP, all_rules)

    def validate(self, scan_result, target_platform=TARGET_PLATFORM_HIGH_END_MOBILE):
        checks = []
        rules = self.rules

        checks.append(self._check_name_prefix(scan_result, rules))
        checks.append(self._check_mesh_exists(scan_result))
        checks.append(self._check_empty_mesh(scan_result))
        if scan_result.get("mesh_geometry"):
            measurements = scan_result["mesh_geometry"]
            checks.append(self._check_geometry_triangles(measurements))
            if any("zero_length_edges" in row for row in measurements.values()):
                measured = {mesh: row for mesh, row in measurements.items() if row.get("zero_length_edges") or row.get("read_error")}
                count = sum(len(row.get("zero_length_edges", [])) for row in measured.values())
                check = self._result("zero_length_edges", "零长度边", not measured, SEVERITY_WARNING, count, 0,
                                     "按原始边号检查重合端点与相邻拓扑。")
                if measured:
                    check.update(affected_meshes=sorted(measured), mesh_results=measured,
                                 next_action="按原始边号定位，检查重合端点与相邻拓扑。")
                checks.append(check)
        checks.append(self._check_frozen_transform(scan_result, rules))
        checks.append(self._check_illegal_scale(scan_result))
        checks.append(self._check_triangle_budget(scan_result, rules, target_platform))
        checks.append(self._check_material_slots(scan_result, rules, target_platform))
        checks.append(self._check_uv_channel("uv0", "UV0", scan_result, rules, SEVERITY_ERROR))
        checks.append(self._check_uv_channel("lightmap_uv", "Lightmap UV", scan_result, rules, SEVERITY_WARNING))
        checks.append(self._check_hidden_objects(scan_result))
        checks.append(self._check_history_nodes(scan_result))
        checks.append(self._check_collision_naming(scan_result))

        checks = [item for item in checks if self._is_check_enabled(item["id"], rules)]
        overrides = {item["id"]: item.get("severity") for item in rules.get("checks", []) if item.get("id")}
        for item in checks:
            severity = overrides.get(item["id"])
            if severity in (SEVERITY_ERROR, SEVERITY_WARNING):
                item["severity"] = severity
                if item["status"] != CHECK_STATUS_PASS:
                    item["status"] = severity
        summary = self._summary(checks)
        score = self._score(checks)
        status = CHECK_STATUS_PASS
        if summary["errors"]:
            status = CHECK_STATUS_ERROR
        elif summary["warnings"]:
            status = CHECK_STATUS_WARNING

        return {
            "asset_name": scan_result.get("asset_name", ""),
            "asset_type": ASSET_TYPE_STATIC_PROP,
            "target_platform": target_platform,
            "status": status,
            "score": score,
            "can_export": self._can_export(summary, rules),
            "block_export_on_error": rules.get("block_export_on_error", True),
            "allow_warning_export": rules.get("allow_warning_export", True),
            "checks": checks,
            "summary": summary,
        }

    def _is_check_enabled(self, check_id, rules):
        if not rules.get("require_" + check_id, True):
            return False
        for item in rules.get("checks", []):
            if item.get("id") == check_id:
                return item.get("enabled", True)
        return True

    def _check_name_prefix(self, scan_result, rules):
        prefix = rules.get("name_prefix", "SM_")
        asset_name = scan_result.get("asset_name", "")
        naming_issues = scan_result.get("naming_issues", [])
        passed = asset_name.startswith(prefix) and not naming_issues
        check = self._result(
            "name_prefix",
            "命名规范",
            passed,
            SEVERITY_ERROR,
            asset_name,
            prefix,
            "；".join(naming_issues) or "资产名应以 {0} 开头".format(prefix),
        )
        if naming_issues:
            check["naming_issues"] = naming_issues
        return check

    def _check_mesh_exists(self, scan_result):
        mesh_count = scan_result.get("mesh_count", 0)
        return self._result(
            "mesh_exists",
            "Mesh 存在",
            mesh_count > 0,
            SEVERITY_ERROR,
            mesh_count,
            ">= 1",
            "选择对象下没有可导出的 Mesh",
        )

    def _check_empty_mesh(self, scan_result):
        empty_meshes = scan_result.get("empty_meshes", [])
        return self._result(
            "empty_mesh",
            "空 Mesh",
            not empty_meshes,
            SEVERITY_ERROR,
            len(empty_meshes),
            0,
            "存在空 Mesh: {0}".format(", ".join(empty_meshes)),
        )

    def _check_geometry_triangles(self, results):
        affected = {name: row for name, row in results.items() if row.get("zero_area_count") or row.get("read_error")}
        total = sum(row.get("zero_area_count", 0) for row in affected.values())
        locations = []
        for name in sorted(affected)[:8]:
            row = affected[name]
            if row.get("read_error"):
                locations.append("{0}（未能读取三角形）".format(name))
                continue
            indices = [str(hit["face_index"]) for hit in row["faces"][:8]]
            locations.append("{0}，原始面 {1}{2}".format(name, ", ".join(indices), "…" if len(row["faces"]) > 8 else ""))
        if len(affected) > 8:
            locations.append("其余对象及全部面号见报告 mesh_results")
        check = self._result("zero_area_triangles", "零面积三角形", not affected, SEVERITY_WARNING,
                             total, 0, "已定位 {0} 个零面积三角形。{1}".format(total, " / ".join(locations)))
        if affected:
            check.update(affected_meshes=sorted(affected), mesh_results=affected,
                         next_action="按对象和原始面号定位，检查面内三角划分及相邻边。")
        return check

    def _check_frozen_transform(self, scan_result, rules):
        required = rules.get("require_frozen_transform", True)
        passed = (not required) or scan_result.get("frozen_transform", False)
        return self._result(
            "frozen_transform",
            "冻结变换",
            passed,
            SEVERITY_ERROR,
            scan_result.get("frozen_transform", False),
            True,
            "Transform 未冻结：Translate/Rotate 应归零，Scale 应为 1",
        )

    def _check_illegal_scale(self, scan_result):
        return self._result(
            "illegal_scale",
            "非法缩放",
            not scan_result.get("illegal_scale", False),
            SEVERITY_ERROR,
            scan_result.get("illegal_scale", False),
            False,
            "存在小于或等于 0 的缩放值",
        )

    def _check_triangle_budget(self, scan_result, rules, target_platform):
        budgets = rules.get("max_triangles", {})
        limit = budgets.get(target_platform)
        triangles = scan_result.get("triangles", 0)
        passed = True if limit is None else triangles <= limit
        return self._result(
            "triangle_budget",
            "三角面预算",
            passed,
            SEVERITY_WARNING,
            triangles,
            limit,
            "三角面数超过 {0} 平台预算".format(target_platform),
        )

    def _check_material_slots(self, scan_result, rules, target_platform):
        budgets = rules.get("max_material_slots", {})
        limit = budgets.get(target_platform)
        material_slots = scan_result.get("material_slots", 0)
        passed = True if limit is None else material_slots <= limit
        return self._result(
            "material_slots",
            "材质插槽",
            passed,
            SEVERITY_WARNING,
            material_slots,
            limit,
            "材质插槽数量超过 {0} 平台预算".format(target_platform),
        )

    def _check_uv_channel(self, check_id, label, scan_result, rules, severity):
        present = scan_result.get("has_" + check_id, False)
        required = rules.get("require_" + check_id, True)
        for setting in rules.get("checks", []):
            if setting.get("id") == check_id:
                severity = setting.get("severity", severity)
                break
        missing = scan_result.get("missing_" + check_id + "_meshes", [])
        message = u"缺少或无法读取 {0} 坐标".format(label)
        if missing:
            message += u"：" + u", ".join(missing)
        check = self._result(check_id, label, not required or present, severity, present, True, message)
        if required and missing:
            check["affected_meshes"] = missing
        return check

    def _check_hidden_objects(self, scan_result):
        hidden_objects = scan_result.get("hidden_objects", [])
        return self._result(
            "hidden_objects",
            "隐藏对象",
            not hidden_objects,
            SEVERITY_WARNING,
            len(hidden_objects),
            0,
            "存在隐藏对象: {0}".format(", ".join(hidden_objects)),
        )

    def _check_history_nodes(self, scan_result):
        history_nodes = scan_result.get("history_nodes", [])
        return self._result(
            "history_nodes",
            "历史节点",
            not history_nodes,
            SEVERITY_WARNING,
            len(history_nodes),
            0,
            "存在历史节点残留: {0}".format(", ".join(history_nodes[:8])),
        )

    def _check_collision_naming(self, scan_result):
        invalid_nodes = scan_result.get("invalid_collision_nodes", [])
        return self._result(
            "collision_naming",
            "Collision naming",
            not invalid_nodes,
            SEVERITY_WARNING,
            len(invalid_nodes),
            0,
            "Suspicious collision nodes should use UE prefixes: {0}".format(", ".join(invalid_nodes[:8])),
        )

    def _result(self, check_id, label, passed, severity, value, limit, fail_message):
        status = CHECK_STATUS_PASS if passed else severity
        message = "通过" if passed else fail_message
        return {
            "id": check_id,
            "label": label,
            "status": status,
            "severity": severity,
            "value": value,
            "limit": limit,
            "message": message,
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
        error_penalty = scoring.get("error_penalty", 20)
        warning_penalty = scoring.get("warning_penalty", 8)
        for item in checks:
            if item["status"] == CHECK_STATUS_ERROR:
                score -= error_penalty
            elif item["status"] == CHECK_STATUS_WARNING:
                score -= warning_penalty
        return max(score, scoring.get("min_score", 0))

    def _can_export(self, summary, rules):
        if summary["errors"] and rules.get("block_export_on_error", True):
            return False
        if summary["warnings"] and not rules.get("allow_warning_export", True):
            return False
        return True


def checks_to_manifest_dict(validation_result):
    """Flatten validation checks for manifest storage."""
    data = {}
    for item in validation_result.get("checks", []):
        data[item["id"]] = {
            "status": item["status"],
            "value": item.get("value"),
            "limit": item.get("limit"),
            "message": item.get("message", ""),
        }
        for key in ("affected_meshes", "mesh_results", "next_action"):
            if item.get(key):
                data[item["id"]][key] = item[key]
    return data
