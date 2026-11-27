# -*- coding: utf-8 -*-
"""Review static meshes and textures already saved in an Unreal project."""

import hashlib
import json

from asset_forge.shared.material_profile_schema import get_material_profile, resolve_material_profile
from asset_forge.shared.rules_schema import get_project_rules
from asset_forge.unreal.texture_importer import COMPRESSION_SETTING_BY_PROFILE
from asset_forge.unreal.asset_review_host import ReviewHost, package_path
from asset_forge.unreal.material_texture_binding_validator import (
    is_official_texture_default, required_texture_rules, texture_parameter_names,
)
from asset_forge.unreal.review_diagnostics import diagnostic


def _policy(overrides):
    overrides = dict(overrides or {})
    platform = overrides.get("platform", "pc")
    rules = get_project_rules()["static_prop"]
    profile_name = overrides.get("material_profile", "Props_Opaque_PBR")
    snapshot = overrides.get("material_profile_snapshot")
    profile = snapshot or get_material_profile(profile_name)
    if not profile or profile.get("name") != profile_name:
        raise ValueError("找不到批审指定的材质规则 " + profile_name)
    profile = resolve_material_profile(profile)
    declared = {name: rule["usage"] for rule in profile["texture_rules"]
                for name in texture_parameter_names(profile, rule["parameter"])}
    policy = {
        "platform": platform, "material_profile": profile["name"],
        "max_triangles": rules["max_triangles"].get(platform),
        "max_material_slots": rules["max_material_slots"].get(platform),
        "max_texture_size": None, "min_lods": None, "require_simple_collision": False,
        "texture_roles": {}, "parameter_roles": declared,
        "default_materials": sorted({"/Engine/EngineMaterials/DefaultMaterial", "/Engine/EngineMaterials/WorldGridMaterial"}
                                    | {package_path(p) for p in overrides.get("default_materials", [])}),
        "parameter_roles_explicit": overrides.get("parameter_roles_explicit", "parameter_roles" in overrides),
        "profile_parents": sorted({package_path(p) for p in [profile["master_material"],
                                   *profile.get("material_variants", {}).values()] if p}),
    }
    for key in ("max_triangles", "max_material_slots", "max_texture_size", "min_lods",
                "require_simple_collision", "parameter_roles", "profile_parents"):
        if key in overrides:
            policy[key] = overrides[key]
    if "asset_budgets" in overrides:
        budgets = overrides["asset_budgets"]
        keys = ("triangles", "material_slots")
        if not isinstance(budgets, dict) or any(type(budgets.get(key)) is not int or budgets[key] <= 0 for key in keys):
            raise ValueError("包体需要声明有效的三角面与材质槽预算。")
        policy["asset_budgets"] = {key: budgets[key] for key in keys}
        if overrides.get("manual_budget") is not True:
            policy["max_triangles"] = budgets["triangles"]
            policy["max_material_slots"] = budgets["material_slots"]
    if overrides.get("manual_budget") is True:
        policy["manual_budget"] = True
    if snapshot:
        policy["material_profile_snapshot"] = snapshot
    policy["texture_roles"] = {package_path(k): v for k, v in overrides.get("texture_roles", {}).items()}
    for key in ("max_triangles", "max_material_slots", "max_texture_size", "min_lods"):
        value = policy[key]
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError("无效预算 " + key)
    if policy["max_triangles"] is None or policy["max_material_slots"] is None:
        raise ValueError("项目须为该平台声明三角面与材质槽预算")
    return policy, profile


def _pass(row, rule, path, actual, expected):
    row["passed"].append(dict(diagnostic(rule, actual, expected, "pass"), rule_id=rule, object_path=path))


def _issue(row, rule, path, actual, expected, suggestion="", severity="error", slot=None, can_preview=False):
    issue = {"asset_path": row["asset_path"], "object_path": path, "rule_id": rule,
             "actual": actual, "expected": expected, "suggestion": suggestion,
             "severity": severity, "owner": "美术" if severity == "error" else "技术美术"}
    issue["diagnostic"] = diagnostic(rule, actual, expected,
                                     {"error": "blocked", "warning": "warning"}.get(severity, "needs_review"),
                                     suggestion, can_preview)
    if slot is not None:
        issue["slot"] = slot
    row["issues"].append(issue)


def _mesh_checks(row, policy):
    facts, path = row["facts"], row["asset_path"]
    slots = facts["slots"]
    for field, value, limit, minimum, suggestion in (
        ("lod0_triangles", facts["lod0_triangles"], policy["max_triangles"], False, "调整 LOD0 几何或确认项目预算。"),
        ("material_slots", len(slots) if slots is not None else None, policy["max_material_slots"], False,
         "检查空槽、重复槽和可合并的材质分区。"),
        ("lod_count", facts["lod_count"], policy["min_lods"], True, "按项目用途制作需要的 LOD。"),
        ("simple_collision", facts.get("simple_collision_count"), 1 if policy["require_simple_collision"] else None,
         True, "补齐项目要求的简单碰撞。"),
    ):
        if limit is None:
            continue
        if value is None or value < 0:
            _issue(row, "mesh."+field, path, None, limit, "无法读取实测值，需在静态网格编辑器核对。", "unknown")
        elif (value < limit if minimum else value > limit):
            _issue(row, "mesh."+field, path, value, limit, suggestion)
        else:
            _pass(row, "mesh."+field, path, value, limit)
    triangles = facts["lod0_triangles"]
    if triangles == 0:
        _issue(row, "mesh.empty_lod0", path, 0, "大于 0", "核对缺失的 LOD0 渲染几何。")
    elif triangles is not None and triangles > 0:
        _pass(row, "mesh.empty_lod0", path, triangles, "大于 0")
    if slots == []:
        _issue(row, "mesh.slot_material", path, [], "assigned", "给网格分配材质。")
    for slot in slots or ():
        mat = slot["material"]
        if not mat or mat in policy["default_materials"]:
            name = slot["name"]
            if sum(s["name"] == name for s in slots) > 1:
                name = "{}[{}]".format(name, slot["index"])
            _issue(row, "mesh.slot_material", path, mat, "assigned", "检查该槽并指定交付材质。",
                   "unknown" if mat is None else "error", slot=name)
    materials = {slot["material"] for slot in slots or () if slot["material"] and slot["material"] not in policy["default_materials"]}
    if slots and all(slot["material"] in materials for slot in slots):
        _pass(row, "mesh.slot_material", path, "{} 个槽已绑定交付材质".format(len(slots)), "assigned")
    for mat in sorted(materials):
        if mat in facts["unreadable_bindings"]:
            _issue(row, "material.texture_bindings", mat, None, "readable",
                   "在材质编辑器核对实际贴图绑定。", "unknown")
        else:
            _pass(row, "material.texture_bindings", mat, "已读取材质的实际贴图引用", "readable")
            material_name = mat.rsplit("/", 1)[-1]
            for parameter, texture in facts["required_texture_bindings"].get(mat, {}).items():
                label = "{} 的 {} 槽".format(material_name, parameter)
                expected = "绑定该槽的交付贴图"
                if not texture or is_official_texture_default(texture):
                    state = "仍使用母材质默认贴图" if texture else "未读到贴图绑定"
                    _issue(row, "material.required_texture", mat, label + state, expected,
                           "打开该材质实例核对此槽，从 DCC 补齐真实贴图后重新交付。", "warning", slot=parameter)
                else:
                    _pass(row, "material.required_texture", mat, label + "已绑定 " + package_path(texture).rsplit("/", 1)[-1], expected)


def scan_assets(asset_paths, policy=None, unreal_module=None):
    """Run a read-only review over exact selected package/object paths."""
    active, profile = _policy(policy)
    return _scan(asset_paths, active, profile, ReviewHost(unreal_module))


def _scan(asset_paths, policy, profile, host):
    selected = sorted({package_path(path) for path in asset_paths if path})
    host_policy = dict(policy, required_texture_parameters={
        rule["parameter"]: texture_parameter_names(profile, rule["parameter"])
        for rule in required_texture_rules(profile)
    })
    assets, textures, fixes = {}, {}, []
    for path in selected:
        obj = host.load(path)
        kind = host.kind(obj)
        row = {"asset_path": path, "asset_type": kind, "facts": {}, "issues": [], "passed": []}
        assets[path] = row
        if kind == "StaticMesh":
            facts = row["facts"] = host.mesh(obj, host_policy)
            _mesh_checks(row, policy)
            uses = facts["textures"]
        elif kind == "Texture2D":
            uses = {path: []}
        else:
            _issue(row, "asset.read", path, kind, "StaticMesh / Texture2D", "核对选区和资产类型。", "unknown")
            continue
        _pass(row, "asset.read", path, kind, "StaticMesh / Texture2D")
        for texture, roles in uses.items():
            entry = textures.setdefault(texture, {"owners": [], "roles": set()})
            entry["owners"].append(path)
            entry["roles"].update(roles)
    settings = {r["usage"]: r for r in profile["texture_rules"]}
    for path, entry in sorted(textures.items()):
        obj = host.load(path)
        kind = host.kind(obj)
        observed = host.texture(obj) if kind == "Texture2D" else {"srgb": None, "compression": None, "source_size": None}
        declared_role = policy["texture_roles"].get(path)
        roles = set(entry["roles"])
        meshes = [owner for owner in entry["owners"] if assets[owner]["asset_type"] == "StaticMesh"]
        impact = None
        if path in selected and not meshes:
            impact = host.impact(path, set(selected), meshes)
            roles.update(host.referenced_roles(path, impact["materials"], host_policy))
        if declared_role:
            roles.discard("unknown")
            roles.add(declared_role)
        role = next(iter(roles)) if len(roles) == 1 else ""
        rule = settings.get(role)
        expected = {}
        if rule:
            compression = COMPRESSION_SETTING_BY_PROFILE.get(rule.get("compression"))
            if compression and type(rule.get("srgb")) is bool:
                expected = {"compression": compression, "srgb": rule["srgb"]}
        old = {k: observed[k] for k in ("compression", "srgb")}
        differences = {k for k in expected if old.get(k) is not None and old[k] != expected[k]}
        if differences:
            impact = impact or host.impact(path, set(selected), meshes)
            if None in old.values():
                impact.update(can_apply=False, reason="未能读取全部待写属性")
            fixes.append(dict(impact, texture_path=path, role=role, old=old, new=expected))
        for owner in entry["owners"]:
            row = assets[owner]
            collected = dict(observed, role=role or "unknown", role_candidates=sorted(roles))
            if owner == path:
                row["facts"].update(collected)
            else:
                row["facts"].setdefault("texture_facts", {})[path] = collected
            if not expected:
                reason = "规则没有为 {} 声明可检查的色彩空间与压缩。".format(role) if role in roles and role != "unknown" else sorted(roles)
                _issue(row, "texture.role", path, reason, "unique profile rule", severity="unknown")
            else:
                _pass(row, "texture.role", path, role, "unique profile rule")
            size = observed["source_size"]
            limit = policy["max_texture_size"]
            if size is None:
                _issue(row, "texture.source_size", path, None, limit, "读取源尺寸失败，核对导入源信息。", "unknown")
            elif limit is not None and max(size) > limit:
                _issue(row, "texture.source_size", path, size, limit, "复核平台预算及画面细节需求。")
            else:
                _pass(row, "texture.source_size", path, size, limit)
            for key in ("srgb", "compression"):
                if old[key] is None or key in differences:
                    advice = "预览修改和受影响引用；确认后保存并复扫。"
                    if old[key] is None:
                        advice = "在纹理编辑器核对属性。"
                    elif not impact["can_apply"]:
                        advice = "需人工处理。" + impact["reason"]
                    _issue(row, "texture."+key, path, old[key], expected.get(key), advice,
                           "unknown" if old[key] is None else "error",
                           can_preview=old[key] is not None and impact["can_apply"])
                elif key in expected:
                    _pass(row, "texture."+key, path, old[key], expected[key])
            if differences and not impact["can_apply"]:
                _issue(row, "texture.repair_scope", path, impact["reason"], "verified private texture",
                       "核对引用范围后由项目负责人处理。", "unknown")
            elif differences:
                _pass(row, "texture.repair_scope", path, "已确认本次修改的全部引用", "verified private texture")
    fixable = {p["texture_path"] for p in fixes if p["can_apply"]}
    for row in assets.values():
        severities = {i["severity"] for i in row["issues"]}
        row["incomplete"] = "unknown" in severities
        row["fully_fixable"] = bool(row["issues"]) and all(
            i["severity"] == "error" and i["object_path"] in fixable and
            i["rule_id"] in ("texture.srgb", "texture.compression") for i in row["issues"])
        row["status"] = "blocked" if "error" in severities else ("needs_review" if row["issues"] else "pass")
        digest = json.dumps(row["facts"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        row["revision"] = hashlib.sha256(digest.encode("utf-8")).hexdigest()
    return {"stage": "asset_review", "asset_paths": selected, "policy": policy, "assets": list(assets.values()),
            "issues": [i for row in assets.values() for i in row["issues"]], "fix_plan": fixes}


def apply_fixes(review, approved_texture_paths, unreal_module=None):
    """Recheck each approved plan immediately before changing and saving a texture."""
    approved = sorted({package_path(p) for p in approved_texture_paths})
    original = {item["texture_path"]: item for item in review["fix_plan"]}
    changes = []
    host = ReviewHost(unreal_module)
    policy, profile = _policy(review["policy"])
    fresh = _scan(review["asset_paths"], policy, profile, host)
    fresh_plans = {p["texture_path"]: p for p in fresh["fix_plan"]}
    for path in approved:
        previous = original.get(path)
        change = {"texture_path": path, "status": "skipped", "reason": "没有已预览并可批准的修改。"}
        changes.append(change)
        if not previous or not previous["can_apply"]:
            continue
        plan = fresh_plans.get(path)
        if not plan or plan != previous:
            change["reason"] = "当前属性、用途或引用与预览不同，请复核新计划。"
            continue
        try:
            impact = host.impact(path, set(fresh["asset_paths"]), plan["mesh_owners"])
            if any(impact[key] != plan[key] for key in impact):
                change["reason"] = "写入前引用发生变化，请复核新计划。"
                continue
            host.save_settings(path, plan["old"], plan["new"])
        except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
            change.update(status="failed", reason=str(exc))
        else:
            change.update(status="saved", reason="修改已保存且读回匹配。", old=plan["old"], new=plan["new"])
    return {"stage": "asset_review_apply", "changes": changes,
            "changed_count": sum(c["status"] == "saved" for c in changes),
            "review": scan_assets(review["asset_paths"], review["policy"], unreal_module)}

