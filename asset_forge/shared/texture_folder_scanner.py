# -*- coding: utf-8 -*-
"""Scan Painter or Designer texture folders using a Material Profile."""

from __future__ import absolute_import

import os
import re

from asset_forge.shared.path_utils import normalize_path
from asset_forge.shared.texture_metadata import apply_texture_metadata


DEFAULT_TEXTURE_EXTENSIONS = [".png", ".tga", ".jpg", ".jpeg", ".tif", ".tiff", ".exr"]

TEXTURE_SET_SPLIT_RE = re.compile(r"[,，、;；\s]+")


class TextureFolderScanner(object):
    """Match texture files to profile rules by suffix, asset name, and texture set."""

    def __init__(self, extensions=None, recursive=False):
        self.extensions = [item.lower() for item in (extensions or DEFAULT_TEXTURE_EXTENSIONS)]
        self.recursive = bool(recursive)

    def scan(self, texture_folder, asset_name, material_profile, recursive=None, texture_set_token=""):
        active_recursive = self.recursive if recursive is None else bool(recursive)
        files = self._texture_files(texture_folder, active_recursive)
        texture_sets = self._texture_sets(files, material_profile)
        requested_tokens = parse_texture_set_selection(texture_set_token)
        selected_sets, selection_issues, auto_selected, requires_selection = self._select_texture_sets(texture_sets, texture_set_token, asset_name)
        selection_blocked = bool([item for item in selection_issues if item.get("status") == "error" or item.get("id") == "texture_set_selection_unmatched"])
        issues = list(selection_issues)

        matched_paths = set()
        textures = []
        required_missing = []
        duplicate_matches = []
        candidates_by_usage = {}

        for rule in material_profile.get("texture_rules", []):
            usage = rule.get("usage", "")
            matches = []
            if selected_sets:
                for selected_set in selected_sets:
                    matches.extend(
                        self._matches_for_rule(
                            files,
                            asset_name,
                            rule,
                            texture_set_token,
                            selected_set.get("set_name", ""),
                        )
                    )
            elif requested_tokens or requires_selection:
                matches = []
            else:
                matches = self._matches_for_rule(files, asset_name, rule, texture_set_token, "")
            candidates_by_usage[usage] = [self._candidate_entry(item) for item in matches]
            if not matches:
                if rule.get("required", False):
                    required_missing.append(usage)
                    issues.append({"status": "warning", "id": "required_texture_missing", "message": "缺少必需贴图类型：{0}".format(usage), "usage": usage})
                continue

            expected_match_count = len(selected_sets) if selected_sets else 1
            if len(matches) > expected_match_count:
                duplicate_match = {"usage": usage, "matches": [normalize_path(item["path"]) for item in matches]}
                duplicate_matches.append(duplicate_match)
                issues.append({"status": "warning", "id": "duplicate_texture_match", "message": "同一贴图类型匹配到多个文件：{0}".format(usage), "usage": usage, "matches": duplicate_match["matches"]})

            selected_matches = matches if selected_sets else matches[:1]
            for selected in selected_matches:
                if selected.get("match_mode") == "suffix_only":
                    issues.append(
                        {
                            "status": "warning",
                            "id": "suffix_only_match",
                            "message": "贴图 {0} 未匹配到资产名，已按贴图集候选选择；如目录内有多套贴图，请显式填写贴图集关键词。".format(usage),
                            "usage": usage,
                            "path": normalize_path(selected["path"]),
                            "match_mode": "suffix_only",
                            "next_action": "在“贴图集关键词”中填写 a1,d1 或完整贴图集名称片段后重新扫描。",
                        }
                    )

                matched_paths.add(selected["path"])
                textures.append(
                    self._texture_entry(
                        selected["path"],
                        rule,
                        selected.get("match_mode", ""),
                        selected.get("score", 0),
                        texture_set_token,
                        selected.get("selected_texture_set", ""),
                    )
                )

        unrecognized = [normalize_path(path) for path in files if path not in matched_paths]
        directory_status = self._directory_status(files, textures, required_missing)
        if selection_blocked:
            directory_status = "incomplete"
        return self._scan_result(
            asset_name,
            material_profile,
            texture_folder,
            texture_set_token,
            active_recursive,
            directory_status,
            directory_status == "valid" and not selection_blocked,
            textures,
            required_missing,
            duplicate_matches,
            candidates_by_usage,
            issues,
            unrecognized,
            texture_sets,
            selected_sets,
            requires_selection or selection_blocked,
            auto_selected,
        )

    def plan_texture_prefix_renames(self, scan_result, texture_prefix="T_", require_selected_set=False):
        prefix = texture_prefix or "T_"
        if require_selected_set and not scan_result.get("selected_texture_sets"):
            return {
                "status": "error",
                "will_modify_disk": False,
                "texture_prefix": prefix,
                "actions": [],
                "planned_count": 0,
                "skipped_count": 0,
                "message": "请先在“贴图集关键词”中选择或确认贴图集，再执行贴图前缀重命名。",
            }
        actions = []
        for texture in scan_result.get("textures", []):
            source = texture.get("source_path") or texture.get("path", "")
            if not source:
                continue
            directory = os.path.dirname(source)
            file_name = os.path.basename(source)
            if file_name.lower().startswith(prefix.lower()):
                actions.append({"status": "skipped", "reason": "already_prefixed", "source_path": normalize_path(source), "target_path": normalize_path(source), "message": "贴图已包含前缀：{0}".format(file_name)})
                continue
            target = os.path.join(directory, prefix + file_name)
            if os.path.exists(target):
                actions.append({"status": "skipped", "reason": "target_exists", "source_path": normalize_path(source), "target_path": normalize_path(target), "message": "目标文件已存在，跳过重命名：{0}".format(normalize_path(target))})
                continue
            actions.append({"status": "planned", "reason": "add_texture_prefix", "source_path": normalize_path(source), "target_path": normalize_path(target), "message": "可添加贴图前缀：{0} -> {1}".format(file_name, os.path.basename(target))})
        return {
            "status": "warning" if any(item["status"] == "skipped" for item in actions) else "pass",
            "will_modify_disk": False,
            "texture_prefix": prefix,
            "actions": actions,
            "planned_count": len([item for item in actions if item["status"] == "planned"]),
            "skipped_count": len([item for item in actions if item["status"] == "skipped"]),
        }

    def execute_texture_prefix_renames(self, scan_result, texture_prefix="T_", require_selected_set=False):
        plan = self.plan_texture_prefix_renames(scan_result, texture_prefix, require_selected_set=require_selected_set)
        if plan.get("status") == "error":
            return plan
        executed = []
        for action in plan.get("actions", []):
            if action.get("status") != "planned":
                executed.append(action)
                continue
            source = action["source_path"]
            target = action["target_path"]
            if os.path.exists(target):
                updated = dict(action, status="skipped", reason="target_exists", message="目标文件已存在，跳过重命名：{0}".format(target))
            else:
                os.rename(source, target)
                updated = dict(action, status="renamed", will_modify_disk=True, message="已重命名贴图：{0}".format(os.path.basename(target)))
            executed.append(updated)
        result = dict(plan, actions=executed, will_modify_disk=True)
        result["renamed_count"] = len([item for item in executed if item.get("status") == "renamed"])
        result["skipped_count"] = len([item for item in executed if item.get("status") == "skipped"])
        result["status"] = "warning" if result["skipped_count"] else "pass"
        return result

    def _scan_result(
        self,
        asset_name,
        material_profile,
        texture_folder,
        texture_set_token,
        active_recursive,
        directory_status,
        can_use_directory,
        textures,
        required_missing,
        duplicate_matches,
        candidates_by_usage,
        issues,
        unrecognized,
        texture_sets,
        selected_sets,
        requires_selection,
        auto_selected=False,
    ):
        naming_validation = self._validate_texture_naming(textures, material_profile)
        feature_hints = _feature_hints_from_textures(textures, material_profile)
        return {
            "asset_name": asset_name,
            "asset_name_candidates": _asset_name_candidates(asset_name, texture_sets, selected_sets),
            "profile": material_profile.get("name", ""),
            "texture_folder": normalize_path(texture_folder),
            "texture_set_token": texture_set_token,
            "texture_set_filter": texture_set_token,
            "selected_texture_set": selected_sets[0].get("set_name", "") if selected_sets else "",
            "selected_texture_sets": [item.get("set_name", "") for item in selected_sets],
            "selected_texture_set_short_names": [_short_texture_set_name(item.get("set_name", "")) for item in selected_sets],
            "auto_selected_texture_sets": bool(auto_selected),
            "requires_texture_set_selection": bool(requires_selection),
            "texture_sets": texture_sets,
            "recursive": active_recursive,
            "directory_status": directory_status,
            "can_use_directory": bool(can_use_directory),
            "matched_count": len(textures),
            "matched_usages": [texture.get("usage", "") for texture in textures],
            "material_feature_hints": feature_hints["features"],
            "variant_candidates": feature_hints["variants"],
            "required_missing": required_missing,
            "duplicate_matches": duplicate_matches,
            "candidates_by_usage": candidates_by_usage,
            "textures": textures,
            "issues": issues,
            "unrecognized": unrecognized,
            "unrecognized_count": len(unrecognized),
            "texture_naming_validation": naming_validation,
            "naming_warnings": naming_validation.get("warnings", []),
            "rename_suggestions": naming_validation.get("rename_suggestions", []),
        }

    def _texture_files(self, texture_folder, recursive=False):
        if not texture_folder or not os.path.isdir(texture_folder):
            return []
        result = []
        if recursive:
            for root, _, file_names in os.walk(texture_folder):
                for file_name in sorted(file_names):
                    path = os.path.join(root, file_name)
                    if os.path.isfile(path) and os.path.splitext(file_name)[1].lower() in self.extensions:
                        result.append(path)
            return sorted(result)

        for file_name in sorted(os.listdir(texture_folder)):
            path = os.path.join(texture_folder, file_name)
            if os.path.isfile(path) and os.path.splitext(file_name)[1].lower() in self.extensions:
                result.append(path)
        return result

    def _matches_for_rule(self, files, asset_name, rule, texture_set_token="", selected_set_name=""):
        matches = []
        suffixes = [_normalize_name(suffix) for suffix in self._expanded_suffixes(rule)]
        active_asset_name = (asset_name or "").lower()
        active_token = _normalize_name(texture_set_token)
        active_set = _normalize_name(selected_set_name)
        for path in files:
            stem = os.path.splitext(os.path.basename(path))[0]
            normalized_stem = stem.lower()
            normalized_compact = _normalize_name(stem)
            if not any(normalized_compact.endswith(suffix) for suffix in suffixes):
                continue
            file_set = _normalize_name(self._texture_set_name_for_rule(stem, rule))
            if active_set and file_set != active_set:
                continue
            score, match_mode = self._match_score(normalized_stem, active_asset_name)
            if active_token and active_token in normalized_compact:
                score += 60
                match_mode = "texture_set_token" if match_mode == "suffix_only" else match_mode + "+texture_set_token"
            if active_set and file_set == active_set and score <= 10:
                score += 40
                match_mode = "texture_set" if match_mode == "suffix_only" else match_mode + "+texture_set"
            matches.append({"path": path, "score": score, "match_mode": match_mode, "selected_texture_set": selected_set_name})
        return [item for item in sorted(matches, key=lambda item: (-item["score"], item["path"].lower()))]

    def _texture_sets(self, files, material_profile):
        groups = {}
        rules = material_profile.get("texture_rules", [])
        required = [rule.get("usage", "") for rule in rules if rule.get("required", False)]
        for path in files:
            stem = os.path.splitext(os.path.basename(path))[0]
            for rule in rules:
                if not self._stem_matches_rule(stem, rule):
                    continue
                set_name = self._texture_set_name_for_rule(stem, rule)
                group = groups.setdefault(
                    set_name,
                    {
                        "set_name": set_name,
                        "short_name": _short_texture_set_name(set_name),
                        "display_name": set_name,
                        "usages": [],
                        "files": [],
                        "missing_usages": [],
                        "completeness": 0.0,
                        "is_complete": False,
                        "ambiguous_usages": [],
                    },
                )
                usage = rule.get("usage", "")
                if usage not in group["usages"]:
                    group["usages"].append(usage)
                group["files"].append({"usage": usage, "path": normalize_path(path)})
                break

        result = []
        for group in groups.values():
            usages = sorted(group["usages"])
            group["usages"] = usages
            group["missing_usages"] = [usage for usage in required if usage not in usages]
            group["is_complete"] = len(group["missing_usages"]) == 0
            group["completeness"] = 1.0 if not required else round(float(len([usage for usage in required if usage in usages])) / float(len(required)), 3)
            usage_counts = {}
            for item in group["files"]:
                usage_counts[item["usage"]] = usage_counts.get(item["usage"], 0) + 1
            group["ambiguous_usages"] = sorted([usage for usage, count in usage_counts.items() if count > 1])
            result.append(group)
        return sorted(result, key=lambda item: (-item["completeness"], item["set_name"].lower()))

    def _select_texture_sets(self, texture_sets, texture_set_token, asset_name=""):
        if not texture_sets:
            return [], [], False, False
        tokens = parse_texture_set_selection(texture_set_token)
        issues = []
        if tokens:
            selected = []
            selected_names = set()
            for token in tokens:
                normalized_token = _normalize_name(token)
                exact_matches = []
                token_matches = []
                substring_matches = []
                for item in texture_sets:
                    set_name = item.get("set_name", "")
                    normalized_set = _normalize_name(set_name)
                    normalized_short = _normalize_name(_short_texture_set_name(set_name))
                    if normalized_token in (normalized_set, normalized_short):
                        exact_matches.append(item)
                    elif normalized_token in [_normalize_name(part) for part in _tokens(set_name)]:
                        token_matches.append(item)
                    elif normalized_token in normalized_set:
                        substring_matches.append(item)

                matches = exact_matches or token_matches or substring_matches[:1]
                if matches:
                    for matched in matches:
                        if matched.get("set_name", "") in selected_names:
                            continue
                        selected.append(matched)
                        selected_names.add(matched.get("set_name", ""))
                else:
                    issues.append({"status": "warning", "id": "texture_set_selection_unmatched", "message": "贴图集关键词未匹配到候选：{0}".format(token), "token": token})
            return selected, issues, False, bool(issues)

        if len(texture_sets) == 1:
            return [texture_sets[0]], issues, False, False
        asset_matches = self._asset_matched_texture_sets(texture_sets, asset_name)
        if asset_matches:
            best_asset_matches = self._best_texture_sets(asset_matches)
            if len(best_asset_matches) == 1:
                return [best_asset_matches[0]], issues, False, False
        best = self._best_texture_sets(texture_sets)
        if best and best[0].get("completeness", 0) > 0:
            selected = [best[0]]
            issues.append(
                {
                    "status": "warning",
                    "id": "texture_set_selection_required",
                    "message": "未填写贴图集关键词，已自动选择当前最优贴图集：{0}。".format(best[0].get("set_name", "")),
                    "selected_texture_set": best[0].get("set_name", ""),
                    "next_action": "如需指定其它套件，请填写 a1,d1 或完整贴图集名称片段后重新扫描。",
                }
            )
            return [], issues, False, True
        return [], issues, False, False

    def _asset_matched_texture_sets(self, texture_sets, asset_name):
        if not asset_name:
            return []
        result = []
        for item in texture_sets or []:
            score, _ = self._match_score((item.get("set_name", "") or "").lower(), (asset_name or "").lower())
            if score >= 80 and item.get("completeness", 0) > 0:
                result.append(item)
        return result

    def _best_texture_sets(self, texture_sets):
        if not texture_sets:
            return []
        best_score = texture_sets[0].get("completeness", 0)
        return [item for item in texture_sets if item.get("completeness", 0) == best_score]

    def _stem_matches_rule(self, stem, rule):
        normalized = _normalize_name(stem)
        return any(normalized.endswith(_normalize_name(suffix)) for suffix in self._expanded_suffixes(rule))

    def _texture_set_name_for_rule(self, stem, rule):
        normalized_stem = _normalize_name(stem)
        best_suffix = ""
        for suffix in self._expanded_suffixes(rule):
            active = _normalize_name(suffix)
            if normalized_stem.endswith(active) and len(active) > len(best_suffix):
                best_suffix = active
        result = stem
        if best_suffix:
            result = stem[: -len(best_suffix)]
        result = result.rstrip(" _-.")
        if result.lower().startswith("t_"):
            result = result[2:]
        return result or stem

    def _belongs_to_asset(self, stem, asset_name):
        return not asset_name or stem == asset_name or stem.startswith(asset_name + "_")

    def _match_score(self, stem, asset_name):
        if not asset_name:
            return 10, "suffix_only"
        if self._belongs_to_asset(stem, asset_name):
            return 100, "asset_prefix"
        stem_tokens = _tokens(stem)
        asset_tokens = [item for item in _tokens(asset_name) if item.lower() != "sm"]
        if asset_tokens and all(_token_in_stem(token, stem_tokens) for token in asset_tokens):
            return 80, "asset_tokens"
        return 10, "suffix_only"

    def _expanded_suffixes(self, rule):
        suffixes = list(rule.get("suffixes", []))
        usage = rule.get("usage", "")
        if usage == "base_color":
            suffixes.extend(["BaseColor", "Base Color", "Base_Color", "Color", "Albedo", "Diffuse"])
        elif usage == "normal":
            suffixes.extend(["Normal", "NormalMap", "N"])
        elif usage == "packed_arm":
            suffixes.extend(["ARM", "ORM", "OcclusionRoughnessMetallic", "Occlusion_Roughness_Metallic"])
        elif usage == "emissive":
            suffixes.extend(["Emissive", "Emission", "Emit", "Glow"])
        elif usage == "height":
            suffixes.extend(["Height", "HeightMap", "Displacement", "Disp", "POM"])
        elif usage == "imperfection_mask":
            suffixes.extend(["Imperfection", "Imperfections", "Dirty", "Dirt", "Grime", "Wear", "EdgeWear", "Scratches"])
        elif usage == "opacity_mask":
            suffixes.extend(["OpacityMask", "Opacity Mask", "Mask"])
        elif usage == "opacity":
            suffixes.extend(["Opacity", "Alpha"])
        return suffixes

    def _texture_entry(self, path, rule, match_mode="", match_score=0, texture_set_token="", selected_texture_set=""):
        entry = {
            "node": "",
            "path": normalize_path(path),
            "source_path": normalize_path(path),
            "package_path": "",
            "copied": False,
            "source_type": "texture_folder",
            "source_label": "贴图目录",
            "usage": rule.get("usage", "unknown"),
            "parameter": rule.get("parameter", ""),
            "srgb": bool(rule.get("srgb", False)),
            "compression": rule.get("compression", ""),
            "match_mode": match_mode,
            "match_score": match_score,
            "texture_set_token": texture_set_token,
            "selected_texture_set": selected_texture_set,
        }
        if rule.get("channels"):
            entry["channels"] = dict(rule["channels"])
        return apply_texture_metadata(entry, path)

    def _candidate_entry(self, match):
        return {"path": normalize_path(match.get("path", "")), "score": match.get("score", 0), "match_mode": match.get("match_mode", "")}

    def _validate_texture_naming(self, textures, material_profile):
        rules_by_usage = dict((rule.get("usage", ""), rule) for rule in material_profile.get("texture_rules", []))
        warnings = []
        rename_suggestions = []
        checks = []

        for texture in textures:
            path = texture.get("source_path") or texture.get("path", "")
            file_name = os.path.basename(path)
            stem, extension = os.path.splitext(file_name)
            usage = texture.get("usage", "")
            rule = rules_by_usage.get(usage, {})

            if not stem.lower().startswith("t_"):
                suggested_name = "T_{0}{1}".format(stem, extension)
                suggestion = {
                    "status": "suggestion",
                    "action": "add_texture_prefix",
                    "usage": usage,
                    "path": normalize_path(path),
                    "current_name": file_name,
                    "suggested_name": suggested_name,
                    "suggested_path": normalize_path(os.path.join(os.path.dirname(path), suggested_name)),
                    "message": "贴图命名缺少 T_ 前缀，是否添加 T_ 前缀：{0}".format(suggested_name),
                    "will_modify_disk": False,
                }
                rename_suggestions.append(suggestion)
                warnings.append({"status": "warning", "id": "texture_missing_t_prefix", "usage": usage, "path": normalize_path(path), "message": "贴图命名缺少 T_ 前缀：{0}。该问题不会阻断导出，可按建议重命名。".format(file_name)})
                checks.append({"status": "warning", "id": "texture_prefix", "usage": usage, "path": normalize_path(path), "message": "贴图文件应使用 T_ 前缀。"})
            else:
                checks.append({"status": "pass", "id": "texture_prefix", "usage": usage, "path": normalize_path(path), "message": "贴图文件已使用 T_ 前缀。"})

            expected_suffixes = list(rule.get("suffixes", []))
            if expected_suffixes and not self._matches_expected_suffix(stem, expected_suffixes):
                warnings.append({"status": "warning", "id": "texture_suffix_mismatch", "usage": usage, "path": normalize_path(path), "expected_suffixes": expected_suffixes, "message": "贴图命名未符合 Material Profile suffix 规范：{0} 应匹配 {1}".format(file_name, ", ".join(expected_suffixes))})
                checks.append({"status": "warning", "id": "texture_suffix", "usage": usage, "path": normalize_path(path), "message": "贴图文件 suffix 未命中当前 Material Profile 规范。"})
            elif expected_suffixes:
                checks.append({"status": "pass", "id": "texture_suffix", "usage": usage, "path": normalize_path(path), "message": "贴图文件 suffix 符合当前 Material Profile 规范。"})

        status = "warning" if warnings else "pass"
        return {
            "status": status,
            "can_export": True,
            "warning_count": len(warnings),
            "warnings": warnings,
            "checks": checks,
            "rename_suggestions": rename_suggestions,
            "next_action": "检查贴图命名建议；如需要，可在 UI 确认后再执行重命名。" if warnings else "贴图命名符合当前规范。",
        }

    def _matches_expected_suffix(self, stem, suffixes):
        normalized_stem = _normalize_name(stem)
        for suffix in suffixes:
            if normalized_stem.endswith(_normalize_name(suffix)):
                return True
        return False

    def _directory_status(self, files, textures, required_missing):
        if required_missing:
            return "incomplete"
        if textures:
            return "valid"
        if files:
            return "unrecognized"
        return "empty"


def _normalize_name(value):
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def parse_texture_set_selection(value):
    return [item.strip() for item in TEXTURE_SET_SPLIT_RE.split(value or "") if item.strip()]


def _short_texture_set_name(value):
    parts = [item for item in re.split(r"[^a-zA-Z0-9]+", value or "") if item]
    return parts[-1] if parts else value


def _asset_name_candidates(asset_name, texture_sets, selected_sets):
    candidates = []
    seen = set()
    for name, source, value in [(asset_name, "asset_name", asset_name)]:
        candidate = _asset_family_name(name)
        if candidate and candidate not in seen:
            candidates.append({"name": candidate, "source": source, "source_value": value, "confidence": "medium"})
            seen.add(candidate)
    active_sets = selected_sets or texture_sets or []
    for item in active_sets:
        set_name = item.get("set_name", "")
        candidate = _asset_family_name(set_name)
        if candidate and candidate not in seen:
            candidates.append({"name": candidate, "source": "texture_set", "source_value": set_name, "confidence": "medium"})
            seen.add(candidate)
    return candidates


def _asset_family_name(value):
    tokens = [item for item in re.split(r"[^a-zA-Z0-9]+", value or "") if item]
    if tokens and tokens[0].upper() in ("SM", "SK", "M", "MI", "T"):
        tokens = tokens[1:]
    while tokens and re.match(r"^[a-zA-Z]\d+$", tokens[-1]):
        tokens = tokens[:-1]
    if len(tokens) >= 3 and len(tokens[-1]) == 1 and tokens[-1].isalpha():
        tokens = tokens[:-1]
    if len(tokens) >= 2 and re.match(r"^[A-Za-z]+\d+$", tokens[0]) and len(tokens[1]) == 1 and tokens[1].isalpha():
        return tokens[0] + tokens[1].upper()
    return tokens[0] if tokens else ""


def _feature_hints_from_textures(textures, material_profile):
    usages = set(texture.get("usage", "") for texture in textures or [])
    features = set()
    variants = set()
    if "base_color" in usages:
        features.add("base_color")
    if "normal" in usages:
        features.add("normal")
    if "packed_arm" in usages:
        features.add("packed_arm")
    if "opacity_mask" in usages or material_profile.get("render_mode") == "masked":
        features.add("opacity_mask")
        variants.add("masked")
    if "opacity" in usages or material_profile.get("render_mode") == "translucent":
        features.add("opacity")
        variants.add("translucent")
    if "emissive" in usages:
        features.add("emissive")
        variants.add("emissive")
    if "imperfection_mask" in usages:
        features.add("imperfection_mask")
        variants.add("dirty_wear")
    if "height" in usages:
        features.add("height")
        variants.add("pom")
    if not variants:
        variants.add("opaque")
    return {"features": sorted(features), "variants": sorted(variants)}


def _tokens(value):
    return [item for item in re.split(r"[^a-zA-Z0-9]+", value or "") if item]


def _token_in_stem(token, stem_tokens):
    normalized = token.lower()
    for item in stem_tokens:
        active = item.lower()
        if active == normalized or active.startswith(normalized):
            return True
    return False
