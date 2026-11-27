"""Unreal texture importer for packaged DCC AssetForge textures."""

from __future__ import absolute_import

from asset_forge.unreal.property_utils import get_unreal_property, set_unreal_property
from asset_forge.unreal.unreal_bridge import get_unreal


COMPRESSION_SETTING_BY_PROFILE = {
    "default": "TC_DEFAULT",
    "normalmap": "TC_NORMALMAP",
    "masks": "TC_MASKS",
}

DEFAULT_TEXTURE_GROUP_BY_USAGE = {
    "base_color": "World",
    "packed_arm": "World",
    "opacity_mask": "World",
    "imperfection_mask": "World",
    "emissive": "World",
    "normal": "WorldNormalMap",
}

TEXTURE_STRATEGY_OVERWRITE = "overwrite"
TEXTURE_STRATEGY_REUSE = "reuse"
TEXTURE_STRATEGY_SKIP = "skip"
TEXTURE_STRATEGY_ERROR = "error"


def preview_texture_import_policy_report(texture_import_plan):
    """Build an offline texture policy preview without touching Unreal assets."""

    texture_import_plan = texture_import_plan or {}
    report = {
        "status": "skipped",
        "mode": "offline_preview",
        "actual_policy_source": "offline_expected_from_requested_policy",
        "existing_texture_strategy": texture_import_plan.get("existing_texture_strategy", TEXTURE_STRATEGY_OVERWRITE),
        "actions": [],
        "issues": [],
    }
    for texture in texture_import_plan.get("textures", []):
        policy_report = _preview_texture_policy(texture)
        report["actions"].append(
            {
                "target_asset_path": texture.get("target_asset_path", ""),
                "strategy": texture.get("existing_texture_strategy", report["existing_texture_strategy"]),
                "action": "preview",
                "message": "\u79bb\u7ebf\u9884\u89c8\u8d34\u56fe\u5bfc\u5165\u7b56\u7565\uff0c\u672a\u542f\u52a8\u771f\u5b9e UE Editor\u3002",
                "policy_report": policy_report,
            }
        )
    if report["actions"]:
        report["status"] = "success"
    return report


def _preview_texture_policy(texture_plan):
    requested = {
        "virtual_texture_policy": texture_plan.get("virtual_texture_policy", "project_default"),
        "texture_streaming_policy": texture_plan.get("texture_streaming_policy", "project_default"),
        "texture_group": texture_plan.get("texture_group", "project_default"),
    }
    report = {
        "asset_path": texture_plan.get("target_asset_path", ""),
        "mode": "offline_preview",
        "actual_policy_source": "offline_expected_from_requested_policy",
        "requested_policy": requested,
        "virtual_texture_policy": requested["virtual_texture_policy"],
        "texture_streaming_policy": requested["texture_streaming_policy"],
        "texture_group": requested["texture_group"],
        "applied": [],
        "actual": {},
        "actual_policy": {},
        "unsupported": [],
        "warnings": [],
        "user_message": "",
        "next_action": "\u8fd9\u662f\u79bb\u7ebf\u9884\u89c8\uff1b\u771f\u5b9e UE \u5bfc\u5165\u540e\u4ecd\u9700\u6253\u5f00\u8d34\u56fe\u8d44\u4ea7\u786e\u8ba4\u5c5e\u6027\u3002",
    }

    _preview_virtual_texture_policy(report)
    _preview_streaming_policy(report)
    _preview_texture_group_policy(report)
    if "normal_format" in texture_plan:
        requested["normal_format"] = texture_plan["normal_format"]
        requested["flip_green_channel"] = texture_plan["flip_green_channel"]
        report["actual"]["flip_green_channel"] = texture_plan["flip_green_channel"]
    if texture_plan.get("normal_format_warning"):
        report["warnings"].append(texture_plan["normal_format_warning"])
    report["actual_policy"] = {
        "effective_virtual_texture": report.get("effective_virtual_texture", report.get("actual", {}).get("virtual_texture")),
        "never_stream": report.get("actual", {}).get("texture_streaming"),
        "texture_group": report.get("actual", {}).get("texture_group"),
    }
    if "flip_green_channel" in report["actual"]:
        report["actual_policy"]["flip_green_channel"] = report["actual"]["flip_green_channel"]
    report["user_message"] = _preview_policy_user_message(report)
    return report


def _preview_virtual_texture_policy(report):
    vt_policy = report["requested_policy"].get("virtual_texture_policy", "project_default")
    streaming_policy = report["requested_policy"].get("texture_streaming_policy", "project_default")
    if vt_policy == "auto" and streaming_policy == "never_stream":
        report["resolved_virtual_texture_policy"] = "auto_resolved_force_off"
        report["resolution_reason"] = "never_stream selects SVT force-off in the offline policy preview."
        report["applied"].append({"property": "virtual_texture_streaming", "value": False})
        report["actual"]["virtual_texture"] = False
        report["effective_virtual_texture"] = False
        return
    if vt_policy in ("force_on", "force_off"):
        expected = vt_policy == "force_on"
        report["resolved_virtual_texture_policy"] = vt_policy
        report["applied"].append({"property": "virtual_texture_streaming", "value": expected})
        report["actual"]["virtual_texture"] = expected
        report["effective_virtual_texture"] = expected
        return
    if vt_policy == "project_default":
        report["resolved_virtual_texture_policy"] = "project_default_resolved_force_off"
        report["resolution_reason"] = "DCC AssetForge Static Prop defaults keep imported textures non-VT unless force_on is requested."
        report["applied"].append({"property": "virtual_texture_streaming", "value": False})
        report["actual"]["virtual_texture"] = False
        report["effective_virtual_texture"] = False
        return
    if vt_policy == "auto":
        report["resolved_virtual_texture_policy"] = "auto_manual_confirm"
        report["actual"]["virtual_texture"] = "auto_project_default"
        report["effective_virtual_texture"] = "auto_project_default"
        report["warnings"].append("\u79bb\u7ebf\u9884\u89c8\u65e0\u6cd5\u8bfb\u53d6\u9879\u76ee Auto Virtual Texturing \u7ed3\u679c\uff0c\u9700\u771f\u5b9e UE \u786e\u8ba4\u3002")
        return
    report["resolved_virtual_texture_policy"] = vt_policy
    report["actual"]["virtual_texture"] = "project_default"
    report["effective_virtual_texture"] = "project_default"


def _preview_streaming_policy(report):
    streaming_policy = report["requested_policy"].get("texture_streaming_policy", "project_default")
    if streaming_policy in ("streaming", "never_stream"):
        expected = streaming_policy == "never_stream"
        report["applied"].append({"property": "never_stream", "value": expected})
        report["actual"]["texture_streaming"] = expected
        return
    report["actual"]["texture_streaming"] = "project_default"


def _preview_texture_group_policy(report):
    texture_group = report["requested_policy"].get("texture_group", "project_default")
    if texture_group and texture_group != "project_default":
        report["applied"].append({"property": "lod_group", "value": texture_group})
        report["actual"]["texture_group"] = texture_group
        return
    report["actual"]["texture_group"] = "project_default"


def _preview_policy_user_message(report):
    requested = report.get("requested_policy", {})
    actual = report.get("actual_policy", {})
    applied = ", ".join([item.get("property", "") for item in report.get("applied", [])]) or "\u65e0"
    return (
        "\u8bf7\u6c42\u7b56\u7565\uff1aVT={0}\uff0cStreaming={1}\uff0cTextureGroup={2}\uff1b"
        "\u79bb\u7ebf\u9884\u89c8\u5e94\u7528\uff1a{3}\uff1b"
        "\u9884\u671f\u7b56\u7565\uff1aVT={4}\uff0cNeverStream={5}\uff0cTextureGroup={6}\uff1b"
        "\u9700\u8981\u771f\u5b9e UE \u786e\u8ba4\uff1a\u662f"
    ).format(
        requested.get("virtual_texture_policy", ""),
        requested.get("texture_streaming_policy", ""),
        requested.get("texture_group", ""),
        applied,
        actual.get("effective_virtual_texture"),
        actual.get("never_stream"),
        actual.get("texture_group"),
    )


class UnrealTextureImporter(object):
    """Import texture files from a texture_import_plan."""

    def __init__(self, unreal_module=None):
        self.unreal = unreal_module or get_unreal()
        self.last_configuration_report = self._empty_configuration_report()
        self.last_import_policy_report = self._empty_policy_report()

    def is_available(self):
        return self.unreal is not None

    def import_textures(self, texture_import_plan):
        if not self.is_available():
            raise RuntimeError("当前环境不可用 Unreal Python 模块")

        self.last_configuration_report = self._empty_configuration_report()
        self.last_import_policy_report = self._empty_policy_report(texture_import_plan)
        imported = []
        tasks = []
        task_textures = []
        for texture in texture_import_plan.get("textures", []):
            action = self._existing_action(texture)
            if action == "skip":
                self._record_policy(texture, "skipped", "同名贴图已存在，按策略跳过。")
                continue
            if action == "error":
                raise RuntimeError("同名贴图已存在：{0}".format(texture.get("target_asset_path", "")))
            if action == "reuse":
                asset_path = texture.get("target_asset_path", "")
                imported.append(asset_path)
                self._record_policy(texture, "reused", "复用已有贴图资产。")
                self._configure_imported_texture(texture, [asset_path], reused=True)
                continue

            tasks.append(self._build_task(texture, replace_existing=True))
            task_textures.append(texture)
            self._record_policy(texture, "queued", "贴图已加入导入队列。")

        if tasks:
            self.unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)
            for task, texture in zip(tasks, task_textures):
                imported_paths = list(get_unreal_property(task, "imported_object_paths", []) or [])
                imported.extend(imported_paths)
                self._configure_imported_texture(texture, imported_paths)

        self._finish_configuration_report()
        self._finish_policy_report()
        return imported

    def _existing_action(self, texture):
        strategy = texture.get("existing_texture_strategy", TEXTURE_STRATEGY_OVERWRITE)
        asset_path = texture.get("target_asset_path", "")
        exists = self._asset_exists(asset_path)
        if not exists:
            return "import"
        if strategy == TEXTURE_STRATEGY_SKIP:
            return "skip"
        if strategy == TEXTURE_STRATEGY_ERROR:
            return "error"
        if strategy == TEXTURE_STRATEGY_REUSE:
            return "reuse"
        return "import"

    def _build_task(self, texture, replace_existing=True):
        task = self.unreal.AssetImportTask()
        set_unreal_property(task, "filename", texture["source_path"])
        set_unreal_property(task, "destination_path", texture["target_dir"])
        set_unreal_property(task, "destination_name", texture["asset_name"])
        set_unreal_property(task, "automated", True)
        set_unreal_property(task, "replace_existing", bool(replace_existing))
        set_unreal_property(task, "save", True)
        return task

    def _configure_imported_texture(self, texture_plan, imported_paths, reused=False):
        asset_path = self._primary_asset_path(imported_paths, texture_plan)
        if not asset_path:
            self.last_configuration_report["issues"].append("贴图导入后未返回资产路径：{0}".format(texture_plan.get("asset_name", "")))
            return

        texture_asset = self._load_asset(asset_path)
        if not texture_asset:
            self.last_configuration_report["issues"].append("无法加载导入后的贴图资产：{0}".format(asset_path))
            return

        set_unreal_property(texture_asset, "srgb", bool(texture_plan.get("srgb", False)))
        compression_value = self._compression_value(texture_plan.get("compression", ""))
        if compression_value is not None:
            set_unreal_property(texture_asset, "compression_settings", compression_value)
        policy_report = self._apply_texture_import_policy(texture_asset, asset_path, texture_plan, reused)
        self._save_asset(asset_path)
        self.last_configuration_report["configured"].append(
            {
                "asset_path": asset_path,
                "usage": texture_plan.get("usage", ""),
                "srgb": bool(texture_plan.get("srgb", False)),
                "compression": texture_plan.get("compression", ""),
                "virtual_texture_policy": texture_plan.get("virtual_texture_policy", "project_default"),
                "texture_streaming_policy": texture_plan.get("texture_streaming_policy", "project_default"),
                "texture_group": texture_plan.get("texture_group", "project_default"),
                "policy_report": policy_report,
            }
        )

    def _apply_texture_import_policy(self, texture_asset, asset_path, texture_plan, reused):
        report = {
            "asset_path": asset_path,
            "requested_policy": {
                "virtual_texture_policy": texture_plan.get("virtual_texture_policy", "project_default"),
                "texture_streaming_policy": texture_plan.get("texture_streaming_policy", "project_default"),
                "texture_group": texture_plan.get("texture_group", "project_default"),
            },
            "virtual_texture_policy": texture_plan.get("virtual_texture_policy", "project_default"),
            "texture_streaming_policy": texture_plan.get("texture_streaming_policy", "project_default"),
            "texture_group": texture_plan.get("texture_group", "project_default"),
            "usage": texture_plan.get("usage", ""),
            "applied": [],
            "actual": {},
            "actual_policy": {},
            "unsupported": [],
            "warnings": [],
            "user_message": "",
            "next_action": "",
        }

        self._apply_virtual_texture_policy(texture_asset, report)
        self._apply_streaming_policy(texture_asset, report)
        self._apply_texture_group_policy(texture_asset, report)
        self._apply_normal_format(texture_asset, texture_plan, report, reused)
        report["actual_policy"] = {
            "effective_virtual_texture": report.get("effective_virtual_texture", report.get("actual", {}).get("virtual_texture")),
            "never_stream": report.get("actual", {}).get("texture_streaming"),
            "texture_group": report.get("actual", {}).get("texture_group"),
        }
        if "flip_green_channel" in report["actual"]:
            report["actual_policy"]["flip_green_channel"] = report["actual"]["flip_green_channel"]
        report["user_message"] = self._policy_user_message(report)

        if report["warnings"]:
            report["next_action"] = "打开导入后的贴图资产，核对报告中标出的设置。"
            self.last_configuration_report["issues"].extend(report["warnings"])
        return report

    def _apply_normal_format(self, texture_asset, texture_plan, report, reused):
        if "normal_format" not in texture_plan:
            return
        if texture_plan.get("normal_format_warning"):
            report["warnings"].append(texture_plan["normal_format_warning"])
        property_name = "flip_green_channel"
        expected = texture_plan[property_name]
        report["requested_policy"].update(normal_format=texture_plan["normal_format"], flip_green_channel=expected)
        if reused:
            actual = self._first_actual_property(texture_asset, [property_name])
            report["actual"][property_name] = actual
            if actual != expected:
                report["warnings"].append("复用的法线贴图绿通道设置与当前包体约定不一致，请核对贴图，或按覆盖策略重新导入。")
            return
        result = self._apply_property(texture_asset, [property_name], expected)
        self._record_property_result(report, property_name, result, expected, "法线绿通道")

    def _apply_virtual_texture_policy(self, texture_asset, report):
        vt_policy = report["requested_policy"].get("virtual_texture_policy", "project_default")
        streaming_policy = report["requested_policy"].get("texture_streaming_policy", "project_default")
        if vt_policy == "auto" and streaming_policy == "never_stream":
            expected = False
            report["resolved_virtual_texture_policy"] = "auto_resolved_force_off"
            report["resolution_reason"] = "never_stream 选择下默认关闭 SVT，避免普通材质采样器与 VT 贴图不匹配。"
            result = self._apply_property(texture_asset, ["VirtualTextureStreaming", "virtual_texture_streaming", "virtual_texture_streaming_enabled"], expected, "virtual_texture_streaming")
            self._record_property_result(report, "virtual_texture", result, expected, "Virtual Texture")
            return
        if vt_policy in ("force_on", "force_off"):
            expected = vt_policy == "force_on"
            report["resolved_virtual_texture_policy"] = vt_policy
            result = self._apply_property(texture_asset, ["VirtualTextureStreaming", "virtual_texture_streaming", "virtual_texture_streaming_enabled"], expected, "virtual_texture_streaming")
            self._record_property_result(report, "virtual_texture", result, expected, "Virtual Texture")
            return
        if vt_policy == "project_default":
            expected = False
            report["resolved_virtual_texture_policy"] = "project_default_resolved_force_off"
            report["resolution_reason"] = "DCC AssetForge Static Prop 默认关闭导入贴图 VT；只有显式 force_on 才启用 VT 材质采样链路。"
            result = self._apply_property(texture_asset, ["VirtualTextureStreaming", "virtual_texture_streaming", "virtual_texture_streaming_enabled"], expected, "virtual_texture_streaming")
            self._record_property_result(report, "virtual_texture", result, expected, "Virtual Texture")
            return
        actual = self._first_actual_property(texture_asset, ["VirtualTextureStreaming", "virtual_texture_streaming", "virtual_texture_streaming_enabled"])
        report["actual"]["virtual_texture"] = actual
        if vt_policy == "auto":
            report["resolved_virtual_texture_policy"] = "auto_manual_confirm"
            report["effective_virtual_texture"] = actual if actual is not None else "auto_project_default"
            report["warnings"].append("Virtual Texture 使用 auto 策略：未强制开关，实际结果需按项目 Auto Virtual Texturing 规则确认。")
        else:
            report["resolved_virtual_texture_policy"] = vt_policy
            report["effective_virtual_texture"] = actual if actual is not None else "project_default"

    def _apply_streaming_policy(self, texture_asset, report):
        streaming_policy = report["requested_policy"].get("texture_streaming_policy", "project_default")
        if streaming_policy in ("streaming", "never_stream"):
            expected = streaming_policy == "never_stream"
            result = self._apply_property(texture_asset, ["NeverStream", "never_stream", "never_streaming"], expected, "never_stream")
            self._record_property_result(report, "texture_streaming", result, expected, "Texture Streaming / Never Stream")
            return
        report["actual"]["texture_streaming"] = self._first_actual_property(texture_asset, ["NeverStream", "never_stream", "never_streaming"])

    def _apply_texture_group_policy(self, texture_asset, report):
        texture_group = report["requested_policy"].get("texture_group", "project_default")
        if texture_group and texture_group != "project_default":
            expected = self._texture_group_value(texture_group)
            result = self._apply_property(texture_asset, ["LODGroup", "lod_group", "texture_group"], expected, "lod_group")
            self._record_property_result(report, "texture_group", result, expected, "Texture Group")
            return
        usage_default = DEFAULT_TEXTURE_GROUP_BY_USAGE.get(report.get("usage", ""))
        if usage_default:
            expected = self._texture_group_value(usage_default)
            result = self._apply_property(texture_asset, ["LODGroup", "lod_group", "texture_group"], expected, "lod_group")
            result["usage_default"] = True
            self._record_property_result(report, "texture_group", result, expected, "Texture Group")
            report["resolved_texture_group_policy"] = "usage_default"
            return
        report["actual"]["texture_group"] = self._first_actual_property(texture_asset, ["LODGroup", "lod_group", "texture_group"])

    def _apply_property(self, asset, names, value, report_property=None):
        for name in names:
            if self._set_property(asset, name, value):
                actual = get_unreal_property(asset, name, None)
                return {"property": report_property or name, "actual_property": name, "requested": value, "actual": actual, "supported": True}
        for name in names:
            actual = get_unreal_property(asset, name, None)
            if self._values_match(actual, value):
                return {"property": report_property or name, "actual_property": name, "requested": value, "actual": actual, "supported": True, "already_matching": True}
        return {"property": "", "requested": value, "actual": None, "supported": False, "candidates": list(names)}

    def _set_property(self, asset, name, value):
        if hasattr(asset, "set_editor_property"):
            try:
                asset.set_editor_property(name, value)
                return True
            except Exception:
                pass
        return set_unreal_property(asset, name, value)

    def _first_actual_property(self, asset, names):
        for name in names:
            value = get_unreal_property(asset, name, None)
            if value is not None:
                return value
        return None

    def _record_property_result(self, report, key, result, expected, label):
        if result.get("supported"):
            report["applied"].append({"property": result.get("property"), "value": self._json_value(result.get("requested"))})
            report["actual"][key] = self._json_value(result.get("actual"))
            if not self._values_match(result.get("actual"), expected):
                report["warnings"].append("{0} 已请求 {1}，但实际读取为 {2}，需要在 UE 中人工确认。".format(label, expected, result.get("actual")))
            if key == "virtual_texture":
                report["effective_virtual_texture"] = self._json_value(result.get("actual"))
            return
        report["unsupported"].append({"policy": key, "requested": self._json_value(expected), "candidates": result.get("candidates", [])})
        report["actual"][key] = None
        if key == "virtual_texture":
            report["effective_virtual_texture"] = "unsupported"
        report["warnings"].append("{0} 请求策略无法通过当前 UE Python 属性设置，需要人工确认。".format(label))

    def _json_value(self, value):
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    def _policy_user_message(self, report):
        requested = report.get("requested_policy", {})
        actual = report.get("actual_policy", {})
        applied = ", ".join([item.get("property", "") for item in report.get("applied", [])]) or "无"
        return (
            "请求策略：VT={0}，Streaming={1}，TextureGroup={2}；"
            "实际应用：{3}；"
            "实际读取：VT={4}，NeverStream={5}，TextureGroup={6}；"
            "需要人工确认：{7}"
        ).format(
            requested.get("virtual_texture_policy", ""),
            requested.get("texture_streaming_policy", ""),
            requested.get("texture_group", ""),
            applied,
            actual.get("effective_virtual_texture"),
            actual.get("never_stream"),
            actual.get("texture_group"),
            "是" if report.get("warnings") or report.get("unsupported") else "否",
        )

    def _primary_asset_path(self, imported_paths, texture_plan):
        if imported_paths:
            return imported_paths[0].split(".", 1)[0]
        return texture_plan.get("target_asset_path", "")

    def _asset_exists(self, asset_path):
        library = getattr(self.unreal, "EditorAssetLibrary", None)
        if library and hasattr(library, "does_asset_exist"):
            return bool(library.does_asset_exist(asset_path))
        if library and hasattr(library, "load_asset"):
            return bool(library.load_asset(asset_path))
        return False

    def _load_asset(self, asset_path):
        library = getattr(self.unreal, "EditorAssetLibrary", None)
        if library and hasattr(library, "load_asset"):
            return library.load_asset(asset_path)
        return None

    def _save_asset(self, asset_path):
        library = getattr(self.unreal, "EditorAssetLibrary", None)
        if library and hasattr(library, "save_asset"):
            library.save_asset(asset_path)

    def _texture_group_value(self, texture_group):
        normalized = self._canonical_texture_group_name(texture_group)
        enum_type = getattr(self.unreal, "TextureGroup", None)
        if enum_type is not None:
            for candidate in self._texture_group_enum_candidates(normalized):
                if hasattr(enum_type, candidate):
                    return getattr(enum_type, candidate)
        return normalized

    def _canonical_texture_group_name(self, texture_group):
        value = str(texture_group or "")
        if value.startswith("TEXTUREGROUP_"):
            return value
        aliases = {
            "World": "TEXTUREGROUP_World",
            "WorldNormalMap": "TEXTUREGROUP_WorldNormalMap",
            "Character": "TEXTUREGROUP_Character",
            "CharacterNormalMap": "TEXTUREGROUP_CharacterNormalMap",
            "UI": "TEXTUREGROUP_UI",
            "Lightmap": "TEXTUREGROUP_Lightmap",
            "Effects": "TEXTUREGROUP_Effects",
        }
        return aliases.get(value, "TEXTUREGROUP_{0}".format(value) if value else value)

    def _texture_group_enum_candidates(self, normalized):
        candidates = [normalized]
        if normalized.startswith("TEXTUREGROUP_"):
            suffix = normalized[len("TEXTUREGROUP_") :]
            candidates.append("TEXTUREGROUP_" + suffix.upper())
            upper_suffix = []
            for char in suffix:
                if char.isupper() and upper_suffix:
                    upper_suffix.append("_")
                upper_suffix.append(char.upper())
            candidates.append("TEXTUREGROUP_" + "".join(upper_suffix))
        return candidates

    def _values_match(self, actual, expected):
        if actual == expected:
            return True
        actual_text = str(actual)
        expected_text = str(expected)
        if actual_text == expected_text:
            return True
        if expected_text and expected_text in actual_text:
            return True
        if actual_text.replace("TEXTUREGROUP_", "") == expected_text.replace("TEXTUREGROUP_", ""):
            return True
        if actual_text.replace("_", "").upper().endswith(expected_text.replace("_", "").upper()):
            return True
        return False

    def _compression_value(self, compression):
        enum_name = COMPRESSION_SETTING_BY_PROFILE.get(compression)
        if not enum_name:
            return None
        enum_type = getattr(self.unreal, "TextureCompressionSettings", None)
        if enum_type is None:
            return enum_name
        return getattr(enum_type, enum_name, enum_name)

    def _record_policy(self, texture, action, message):
        self.last_import_policy_report["actions"].append(
            {
                "target_asset_path": texture.get("target_asset_path", ""),
                "strategy": texture.get("existing_texture_strategy", TEXTURE_STRATEGY_OVERWRITE),
                "action": action,
                "message": message,
            }
        )

    def _finish_configuration_report(self):
        report = self.last_configuration_report
        if report["issues"]:
            report["status"] = "warning" if report["configured"] else "skipped"
        else:
            report["status"] = "success" if report["configured"] else "skipped"

    def _finish_policy_report(self):
        report = self.last_import_policy_report
        report["status"] = "success" if report["actions"] else "skipped"

    def _empty_policy_report(self, texture_import_plan=None):
        texture_import_plan = texture_import_plan or {}
        return {
            "status": "skipped",
            "existing_texture_strategy": texture_import_plan.get("existing_texture_strategy", TEXTURE_STRATEGY_OVERWRITE),
            "actions": [],
            "issues": [],
        }

    def _empty_configuration_report(self):
        return {
            "status": "skipped",
            "configured": [],
            "issues": [],
        }
