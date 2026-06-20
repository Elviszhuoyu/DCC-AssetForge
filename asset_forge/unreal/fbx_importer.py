"""Unreal Static Mesh FBX importer."""

from __future__ import absolute_import

from asset_forge.shared.unreal_path import sanitize_unreal_package_path
from asset_forge.unreal.property_utils import get_unreal_property, set_first_available_property, set_unreal_property
from asset_forge.unreal.unreal_bridge import get_unreal


MESH_STRATEGY_OVERWRITE = "overwrite"
MESH_STRATEGY_REUSE = "reuse"
MESH_STRATEGY_SKIP = "skip"
MESH_STRATEGY_ERROR = "error"


class UnrealStaticMeshFbxImporter(object):
    """Import Static Mesh FBX files using Unreal Python."""

    def __init__(self, unreal_module=None):
        self.unreal = unreal_module or get_unreal()
        self.last_import_policy_report = self._empty_policy_report()
        self.last_fbx_import_options_report = self._empty_options_report()

    def is_available(self):
        return self.unreal is not None

    def import_static_mesh(self, manifest, preset):
        if not self.is_available():
            raise RuntimeError("当前环境不可用 Unreal Python 模块")

        target_asset_path = self._target_asset_path(manifest)
        strategy = manifest.get("existing_mesh_strategy", MESH_STRATEGY_OVERWRITE)
        self.last_import_policy_report = self._empty_policy_report(strategy)
        self.last_fbx_import_options_report = self.plan_fbx_import_options(manifest, preset)
        if self._asset_exists(target_asset_path):
            if strategy == MESH_STRATEGY_SKIP:
                self._record_policy(target_asset_path, strategy, "skipped", "同名 Static Mesh 已存在，按策略跳过。")
                return [target_asset_path]
            if strategy == MESH_STRATEGY_REUSE:
                self._record_policy(target_asset_path, strategy, "reused", "复用已有 Static Mesh。")
                return [target_asset_path]
            if strategy == MESH_STRATEGY_ERROR:
                raise RuntimeError("同名 Static Mesh 已存在：{0}".format(target_asset_path))

        unreal = self.unreal
        task = unreal.AssetImportTask()
        set_unreal_property(task, "filename", manifest["fbx_path"])
        set_unreal_property(task, "destination_path", sanitize_unreal_package_path(manifest["target_path"]))
        set_unreal_property(task, "destination_name", manifest.get("asset_name", ""))
        set_unreal_property(task, "automated", True)
        set_unreal_property(task, "replace_existing", strategy == MESH_STRATEGY_OVERWRITE)
        set_unreal_property(task, "save", True)
        set_unreal_property(task, "options", self._build_fbx_import_ui(manifest, preset))

        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        imported = self._resolve_imported_assets(task, target_asset_path)
        self._record_policy(target_asset_path, strategy, "imported", "Static Mesh 已执行 FBX 导入。")
        self._apply_static_mesh_policy(manifest, imported)
        return imported

    def plan_fbx_import_options(self, manifest, preset):
        """Create a reportable Static Mesh FBX import option plan.

        UE 5.6 exposes these on FbxImportUI / FbxStaticMeshImportData. We record
        the option names before running UE so dry-run reports can be inspected.
        """
        manifest = manifest or {}
        preset = preset or {}
        policy = dict(manifest.get("static_mesh_import_policy", {}) or {})
        nanite_policy = policy.get("nanite_policy", "project_default")
        import_lod_policy = policy.get("import_lod_policy", policy.get("static_mesh_lod_import_policy", "import_existing"))
        lod_group = policy.get("lod_group", policy.get("static_mesh_lod_group", "project_default"))
        build_nanite = True if nanite_policy == "enable" else (False if nanite_policy == "disable" else None)
        import_mesh_lods = True if import_lod_policy == "import_existing" else (False if import_lod_policy == "ignore_lods" else None)
        reversed_policy = policy.get("build_reversed_index_buffer", "report_only")

        normal_import_method = str(preset.get("normal_import_method", "") or "").strip().lower()
        vertex_color_import_option = str(preset.get("vertex_color_import_option", "") or "").strip().lower()

        options = {
            "fbx_import_type": "FBXIT_STATIC_MESH",
            "import_mesh": _option_bool(preset.get("import_mesh", True), True),
            "import_as_skeletal": False,
            "import_materials": _option_bool(preset.get("fbx_import_materials", False), False),
            "import_textures": _option_bool(preset.get("fbx_import_textures", False), False),
            "combine_meshes": _option_bool(preset.get("combine_meshes", False), False),
            "auto_generate_collision": _option_bool(
                preset.get("auto_generate_collision", preset.get("generate_missing_collision", False)),
                False,
            ),
            "generate_lightmap_uvs": _option_bool(preset.get("generate_lightmap_uvs", True), True),
            "convert_scene": _option_bool(preset.get("convert_scene", True), True),
            "force_front_x_axis": _option_bool(preset.get("force_front_x_axis", False), False),
            "convert_scene_unit": _option_bool(preset.get("convert_scene_unit", True), True),
            "transform_vertex_to_absolute": _option_bool(preset.get("transform_vertex_to_absolute", True), True),
            "bake_pivot_in_vertex": _option_bool(preset.get("bake_pivot_in_vertex", False), False),
            "import_translation": _float_triplet(preset.get("import_translation"), [0.0, 0.0, 0.0]),
            "import_rotation": _float_triplet(preset.get("import_rotation"), [0.0, 0.0, 0.0]),
            "import_uniform_scale": float(preset.get("import_uniform_scale", 1.0)),
            "one_convex_hull_per_ucx": _option_bool(preset.get("one_convex_hull_per_ucx", True), True),
            "remove_degenerates": _option_bool(preset.get("remove_degenerates", True), True),
            "compute_weighted_normals": _option_bool(preset.get("compute_weighted_normals", False), False),
            "build_nanite": build_nanite,
            "build_reversed_index_buffer": _policy_bool(reversed_policy),
            "static_mesh_lod_group": lod_group,
            "import_mesh_lods": import_mesh_lods,
            "normal_import_method": normal_import_method,
            "normal_generation_method": preset.get("normal_generation_method", "mikk_t_space"),
            "vertex_color_import_option": vertex_color_import_option,
            "fbx_version_note": "UE FBX Content Pipeline 建议使用 FBX 2020.2；导入报告只记录策略，不验证源 FBX 版本。",
        }
        if _normalized_option(options["vertex_color_import_option"]) == "override":
            options["vertex_override_color"] = list(preset.get("vertex_override_color") or [1.0, 1.0, 1.0])[:3]

        warnings = []
        if nanite_policy in ("project_default", "report_only"):
            warnings.append("Nanite 策略为 {0}，本次只记录，不强制修改 UE 导入设置。".format(nanite_policy))
        if import_lod_policy == "report_only":
            warnings.append("LOD 导入策略为 report_only，本次不强制 import_mesh_lods。")
        return {
            "status": "warning" if warnings else "ready",
            "api": {
                "import_ui": "unreal.FbxImportUI",
                "static_mesh_import_data": "unreal.FbxStaticMeshImportData",
                "import_type": "unreal.FBXImportType.FBXIT_STATIC_MESH",
            },
            "policy": policy,
            "options": options,
            "warnings": warnings,
            "ignored_options": [],
            "next_action": "在真实 UE 5.6 导入报告中确认这些 editor properties 是否被成功设置。" if warnings else "可按该 FBX Static Mesh 导入策略执行。",
        }

    def _target_asset_path(self, manifest):
        return "{0}/{1}".format(sanitize_unreal_package_path(manifest.get("target_path", "")), manifest.get("asset_name", ""))

    def _asset_exists(self, asset_path):
        library = getattr(self.unreal, "EditorAssetLibrary", None)
        if library and hasattr(library, "does_asset_exist"):
            return bool(library.does_asset_exist(asset_path))
        if library and hasattr(library, "load_asset"):
            return bool(library.load_asset(asset_path))
        return False

    def _resolve_imported_assets(self, task, target_asset_path):
        imported = list(get_unreal_property(task, "imported_object_paths", []) or [])
        if imported:
            return imported
        if self._asset_exists(target_asset_path):
            return [target_asset_path]
        object_path = target_asset_path + "." + target_asset_path.rsplit("/", 1)[-1]
        if self._asset_exists(object_path):
            return [target_asset_path]
        return []

    def _record_policy(self, target_asset_path, strategy, action, message):
        self.last_import_policy_report["actions"].append(
            {
                "target_asset_path": target_asset_path,
                "strategy": strategy,
                "action": action,
                "message": message,
            }
        )
        self.last_import_policy_report["status"] = "success"

    def _empty_policy_report(self, strategy="overwrite"):
        return {
            "status": "skipped",
            "existing_mesh_strategy": strategy,
            "actions": [],
            "issues": [],
            "static_mesh_import_policy": {},
            "static_mesh_policy_report": {
                "status": "skipped",
                "message": "",
                "applied": [],
                "warnings": [],
                "next_action": "",
            },
        }

    def _empty_options_report(self):
        return {
            "status": "skipped",
            "api": {},
            "policy": {},
            "options": {},
            "warnings": [],
            "ignored_options": [],
            "next_action": "",
        }

    def _apply_static_mesh_policy(self, manifest, imported_paths):
        policy = dict(manifest.get("static_mesh_import_policy", {}) or {})
        if not policy:
            policy = {"nanite_policy": "project_default", "lod_group": "project_default", "import_lod_policy": "import_existing"}
        report = {
            "status": "skipped",
            "policy": policy,
            "message": "Nanite 是虚拟化几何系统，不等同传统 LOD；当前策略按项目 / 资产类型决定是否启用。",
            "applied": [],
            "warnings": [],
            "next_action": "",
        }
        self.last_import_policy_report["static_mesh_import_policy"] = policy
        asset_paths = [path.split(".", 1)[0] for path in (imported_paths or [])]
        if not asset_paths:
            report["warnings"].append("Static Mesh 导入后未返回资产路径，无法应用 Nanite / LOD 策略。")
            report["status"] = "warning"
            report["next_action"] = "在 UE 中打开导入后的 Static Mesh，手动确认 Nanite、LODGroup 与 LOD 导入设置。"
            self.last_import_policy_report["static_mesh_policy_report"] = report
            self.last_import_policy_report["issues"].extend(report["warnings"])
            return report

        for asset_path in asset_paths:
            asset = self._load_asset(asset_path)
            if not asset:
                report["warnings"].append("无法加载 Static Mesh 资产以应用导入策略：{0}".format(asset_path))
                continue
            self._apply_nanite_policy(asset, asset_path, policy.get("nanite_policy", "project_default"), report)
            self._apply_lod_group(asset, asset_path, policy.get("lod_group", "project_default"), report)

        if policy.get("import_lod_policy") not in ("", "project_default", "import_existing"):
            report["warnings"].append("LOD 导入策略已记录为 {0}，导入阶段按报告策略处理，不声明生产级自动 LOD 完成。".format(policy.get("import_lod_policy")))
        for field in ["build_reversed_index_buffer", "generate_lightmap_uvs", "collision_complexity"]:
            if policy.get(field) and policy.get(field) != "report_only":
                report["warnings"].append("{0} 策略已记录为 {1}，当前阶段按 report-only 处理。".format(field, policy.get(field)))

        report["status"] = "warning" if report["warnings"] else ("success" if report["applied"] else "skipped")
        if report["warnings"]:
            report["next_action"] = "在真实 UE 5.6 中打开 Static Mesh，确认 Nanite、LODGroup 与 LOD 导入结果。"
            self.last_import_policy_report["issues"].extend(report["warnings"])
        self.last_import_policy_report["static_mesh_policy_report"] = report
        return report

    def _apply_nanite_policy(self, asset, asset_path, nanite_policy, report):
        if nanite_policy not in ("enable", "disable"):
            return
        enabled = nanite_policy == "enable"
        settings = get_unreal_property(asset, "nanite_settings")
        if settings is not None and set_unreal_property(settings, "enabled", enabled):
            report["applied"].append({"asset_path": asset_path, "property": "nanite_settings.enabled", "value": enabled})
            return
        prop = set_first_available_property(asset, ["nanite_enabled", "enable_nanite"], enabled)
        if prop:
            report["applied"].append({"asset_path": asset_path, "property": prop, "value": enabled})
        else:
            report["warnings"].append("无法通过当前 UE Python API 设置 Nanite：{0}".format(asset_path))

    def _apply_lod_group(self, asset, asset_path, lod_group, report):
        if not lod_group or lod_group == "project_default":
            return
        prop = set_first_available_property(asset, ["lod_group", "lod_group_name", "static_mesh_lod_group"], lod_group)
        if prop:
            report["applied"].append({"asset_path": asset_path, "property": prop, "value": lod_group})
        else:
            report["warnings"].append("无法通过当前 UE Python API 设置 Static Mesh LODGroup：{0}".format(asset_path))

    def _load_asset(self, asset_path):
        library = getattr(self.unreal, "EditorAssetLibrary", None)
        if library and hasattr(library, "load_asset"):
            return library.load_asset(asset_path)
        return None

    def _build_fbx_import_ui(self, manifest, preset):
        unreal = self.unreal
        report = self.plan_fbx_import_options(manifest, preset)
        self.last_fbx_import_options_report = report
        options = unreal.FbxImportUI()
        set_unreal_property(options, "import_mesh", report["options"]["import_mesh"])
        set_unreal_property(options, "import_materials", report["options"]["import_materials"])
        set_unreal_property(options, "import_textures", report["options"]["import_textures"])
        set_unreal_property(options, "import_as_skeletal", False)
        self._apply_import_type(options, report)

        static_mesh_data = get_unreal_property(options, "static_mesh_import_data")
        if static_mesh_data is None:
            report["warnings"].append("FbxImportUI 未返回 static_mesh_import_data，无法设置 Static Mesh 细节导入选项。")
            report["status"] = "warning"
            return options

        self._set_reported_property(static_mesh_data, "combine_meshes", report["options"]["combine_meshes"], report)
        self._set_reported_property(static_mesh_data, "convert_scene", report["options"]["convert_scene"], report)
        self._set_reported_property(static_mesh_data, "force_front_x_axis", report["options"]["force_front_x_axis"], report)
        self._set_reported_property(static_mesh_data, "convert_scene_unit", report["options"]["convert_scene_unit"], report)
        self._set_reported_property(static_mesh_data, "transform_vertex_to_absolute", report["options"]["transform_vertex_to_absolute"], report)
        self._set_reported_property(static_mesh_data, "bake_pivot_in_vertex", report["options"]["bake_pivot_in_vertex"], report)
        self._set_reported_property(static_mesh_data, "import_translation", self._make_unreal_vector(report["options"]["import_translation"]), report)
        self._set_reported_property(static_mesh_data, "import_rotation", self._make_unreal_rotator(report["options"]["import_rotation"]), report)
        self._set_reported_property(static_mesh_data, "import_uniform_scale", report["options"]["import_uniform_scale"], report)
        self._set_reported_property(static_mesh_data, "one_convex_hull_per_ucx", report["options"]["one_convex_hull_per_ucx"], report)
        self._set_reported_property(static_mesh_data, "remove_degenerates", report["options"]["remove_degenerates"], report)
        self._set_reported_property(static_mesh_data, "compute_weighted_normals", report["options"]["compute_weighted_normals"], report)
        self._set_reported_property(static_mesh_data, "auto_generate_collision", report["options"]["auto_generate_collision"], report)
        self._set_reported_property(static_mesh_data, "build_nanite", report["options"]["build_nanite"], report)
        self._set_reported_property(static_mesh_data, "build_reversed_index_buffer", report["options"]["build_reversed_index_buffer"], report)
        self._set_reported_property(static_mesh_data, "static_mesh_lod_group", report["options"]["static_mesh_lod_group"], report)
        self._set_first_reported_property(
            static_mesh_data,
            ["import_mesh_lods", "import_mesh_lo_ds"],
            report["options"]["import_mesh_lods"],
            report,
            "import_mesh_lods",
        )
        self._apply_vertex_color_import_option(static_mesh_data, report["options"].get("vertex_color_import_option"), report)
        self._set_first_reported_property(
            static_mesh_data,
            ["generate_lightmap_u_vs", "generate_lightmap_uvs"],
            report["options"]["generate_lightmap_uvs"],
            report,
            "generate_lightmap_uvs",
        )
        self._apply_normal_import_method(static_mesh_data, report["options"].get("normal_import_method"), report)
        if _normalized_option(report["options"].get("normal_import_method")) == "import_normals_and_tangents":
            report.setdefault("ignored_options", []).append(
                {
                    "property": "normal_generation_method",
                    "value": report["options"].get("normal_generation_method"),
                    "reason": "UE ignores normal_generation_method when source normals and tangents are imported.",
                }
            )
        else:
            self._apply_normal_generation_method(static_mesh_data, report["options"].get("normal_generation_method"), report)
        if _normalized_option(report["options"].get("vertex_color_import_option")) == "override":
            self._apply_vertex_override_color(static_mesh_data, report["options"].get("vertex_override_color"), report)
        report["status"] = "warning" if report["warnings"] else "ready"
        return options

    def _apply_import_type(self, options, report):
        enum = getattr(self.unreal, "FBXImportType", None)
        static_mesh_type = getattr(enum, "FBXIT_STATIC_MESH", None) if enum else None
        if static_mesh_type is None:
            report["warnings"].append("当前 UE Python API 未暴露 FBXImportType.FBXIT_STATIC_MESH，已通过 import_as_skeletal=False 对齐 Static Mesh。")
            return
        if set_unreal_property(options, "mesh_type_to_import", static_mesh_type):
            report["options"]["mesh_type_to_import"] = "FBXIT_STATIC_MESH"
        else:
            report["warnings"].append("无法设置 FbxImportUI.mesh_type_to_import，需在 UE 导入报告中人工确认 Static Mesh 类型。")

    def _set_reported_property(self, obj, name, value, report):
        if value is None or value == "project_default":
            return
        if set_unreal_property(obj, name, value):
            report.setdefault("applied_options", []).append(
                {"property": name, "value": self._report_value(value), "readback": self._report_value(get_unreal_property(obj, name, None))}
            )
        else:
            report["warnings"].append("无法设置 FbxStaticMeshImportData.{0}，请在 UE 导入界面或报告中确认。".format(name))

    def _set_first_reported_property(self, obj, names, value, report, report_name):
        prop = set_first_available_property(obj, names, value)
        if prop:
            report.setdefault("applied_options", []).append(
                {"property": prop, "value": self._report_value(value), "option": report_name, "readback": self._report_value(get_unreal_property(obj, prop, None))}
            )
        else:
            report["warnings"].append("无法设置 FbxStaticMeshImportData.{0}；请在 UE 导入报告中确认。".format(report_name))
            report["status"] = "warning"

    def _apply_normal_import_method(self, static_mesh_data, method_name, report):
        unreal = self.unreal
        if not method_name or not hasattr(unreal, "FBXNormalImportMethod"):
            return

        normal_enum = unreal.FBXNormalImportMethod
        enum_value = None
        if method_name == "import_normals_and_tangents":
            enum_value = getattr(normal_enum, "FBXNIM_IMPORT_NORMALS_AND_TANGENTS", None)
        elif method_name == "import_normals":
            enum_value = getattr(normal_enum, "FBXNIM_IMPORT_NORMALS", None)
        elif method_name == "compute_normals":
            enum_value = getattr(normal_enum, "FBXNIM_COMPUTE_NORMALS", None)

        if enum_value is None:
            report["warnings"].append("无法解析 FBXNormalImportMethod.{0}；请在 UE 导入报告中确认法线导入策略。".format(method_name))
            report["status"] = "warning"
            return
        if set_unreal_property(static_mesh_data, "normal_import_method", enum_value):
            report.setdefault("applied_options", []).append(
                {"property": "normal_import_method", "value": method_name, "readback": self._report_value(get_unreal_property(static_mesh_data, "normal_import_method", None))}
            )
        else:
            report["warnings"].append("无法设置 FbxStaticMeshImportData.normal_import_method；请在 UE 导入报告中确认。")
            report["status"] = "warning"

    def _apply_normal_generation_method(self, static_mesh_data, method_name, report):
        if not method_name:
            return
        enum = getattr(self.unreal, "FBXNormalGenerationMethod", None) or getattr(self.unreal, "EFBXNormalGenerationMethod", None)
        normalized = str(method_name).strip().lower()
        candidates = {
            "mikk_t_space": ["MIKK_T_SPACE", "MikkTSpace", "MIKK_TSPACE", "MikkTSPace"],
            "built_in": ["BUILT_IN", "BuiltIn"],
        }.get(normalized, [])
        enum_value = None
        if enum is not None:
            for candidate in candidates:
                enum_value = getattr(enum, candidate, None)
                if enum_value is not None:
                    break
        if enum_value is None:
            # UE namespace enums are exposed inconsistently across versions; plain strings still work in tests and keep reports explicit.
            enum_value = "MikkTSpace" if normalized == "mikk_t_space" else ("BuiltIn" if normalized == "built_in" else None)
        if enum_value is None:
            report["warnings"].append("无法解析 EFBXNormalGenerationMethod.{0}；请在 UE 导入报告中确认法线生成策略。".format(method_name))
            report["status"] = "warning"
            return
        if set_unreal_property(static_mesh_data, "normal_generation_method", enum_value):
            report.setdefault("applied_options", []).append(
                {"property": "normal_generation_method", "value": method_name, "readback": self._report_value(get_unreal_property(static_mesh_data, "normal_generation_method", None))}
            )
        else:
            report["warnings"].append("无法设置 FbxStaticMeshImportData.normal_generation_method；请在 UE 导入报告中确认。")
            report["status"] = "warning"

    def _apply_vertex_override_color(self, static_mesh_data, color_values, report):
        if not color_values:
            return
        try:
            channels = [max(0.0, min(1.0, float(value))) for value in list(color_values)[:3]]
        except Exception:
            report["warnings"].append("无法解析 vertex_override_color；请在 UE 导入报告中确认覆盖色。")
            report["status"] = "warning"
            return
        while len(channels) < 3:
            channels.append(1.0)

        color_value = self._make_unreal_color(channels)
        if set_unreal_property(static_mesh_data, "vertex_override_color", color_value):
            report.setdefault("applied_options", []).append(
                {"property": "vertex_override_color", "value": channels, "readback": self._report_value(get_unreal_property(static_mesh_data, "vertex_override_color", None))}
            )
        else:
            report["warnings"].append("无法设置 FbxStaticMeshImportData.vertex_override_color；请在 UE 导入报告中确认。")
            report["status"] = "warning"

    def _make_unreal_color(self, channels):
        color_class = getattr(self.unreal, "Color", None)
        values = [int(round(max(0.0, min(1.0, channel)) * 255.0)) for channel in channels]
        if color_class is not None:
            try:
                return color_class(values[0], values[1], values[2], 255)
            except Exception:
                pass
        linear_color_class = getattr(self.unreal, "LinearColor", None)
        if linear_color_class is not None:
            try:
                return linear_color_class(channels[0], channels[1], channels[2], 1.0)
            except Exception:
                pass
        return tuple(values + [255])

    def _make_unreal_vector(self, channels):
        vector_class = getattr(self.unreal, "Vector", None)
        values = _float_triplet(channels, [0.0, 0.0, 0.0])
        if vector_class is not None:
            try:
                return vector_class(values[0], values[1], values[2])
            except Exception:
                pass
        return values

    def _make_unreal_rotator(self, channels):
        rotator_class = getattr(self.unreal, "Rotator", None)
        values = _float_triplet(channels, [0.0, 0.0, 0.0])
        if rotator_class is not None:
            try:
                return rotator_class(values[0], values[1], values[2])
            except Exception:
                pass
        return values

    def _report_value(self, value):
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        if isinstance(value, (list, tuple)):
            return list(value)
        axis_values = []
        for name in ("x", "y", "z"):
            if hasattr(value, name):
                axis_values.append(getattr(value, name))
        if axis_values:
            return axis_values
        rotator_values = []
        for name in ("pitch", "yaw", "roll"):
            if hasattr(value, name):
                rotator_values.append(getattr(value, name))
        if rotator_values:
            return rotator_values
        channels = []
        for name in ("r", "g", "b", "a"):
            if hasattr(value, name):
                channels.append(getattr(value, name))
        if channels:
            return channels
        return str(value)

    def _apply_vertex_color_import_option(self, static_mesh_data, option_name, report):
        if not option_name:
            return
        enum = getattr(self.unreal, "EVertexColorImportOption", None) or getattr(self.unreal, "VertexColorImportOption", None)
        enum_value = None
        normalized = str(option_name).strip().lower()
        if enum is not None:
            candidates = {
                "replace": ["REPLACE", "Replace"],
                "ignore": ["IGNORE", "Ignore"],
                "override": ["OVERRIDE", "Override"],
            }.get(normalized, [])
            for candidate in candidates:
                enum_value = getattr(enum, candidate, None)
                if enum_value is not None:
                    break
        if enum_value is None:
            report["warnings"].append("无法解析 EVertexColorImportOption.{0}；请在 UE 导入报告中确认顶点色导入策略。".format(option_name))
            report["status"] = "warning"
            return
        if set_unreal_property(static_mesh_data, "vertex_color_import_option", enum_value):
            report.setdefault("applied_options", []).append(
                {"property": "vertex_color_import_option", "value": option_name, "readback": self._report_value(get_unreal_property(static_mesh_data, "vertex_color_import_option", None))}
            )
        else:
            report["warnings"].append("无法设置 FbxStaticMeshImportData.vertex_color_import_option；请在 UE 导入报告中确认。")
            report["status"] = "warning"


def _policy_bool(value):
    if isinstance(value, bool):
        return value
    if value in ("enable", "true", "on", "yes", "1"):
        return True
    if value in ("disable", "false", "off", "no", "0"):
        return False
    return None


def _normalized_option(value):
    return str(value or "").strip().lower()


def _float_triplet(value, default):
    try:
        values = [float(item) for item in list(value or default)[:3]]
    except Exception:
        values = list(default)
    while len(values) < 3:
        values.append(float(default[len(values)] if len(default) > len(values) else 0.0))
    return values


def _option_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    if isinstance(value, (int, float)):
        return value != 0
    normalized = str(value).strip().lower()
    if normalized in ("true", "1", "yes", "on", "enable", "enabled"):
        return True
    if normalized in ("false", "0", "no", "off", "disable", "disabled"):
        return False
    return bool(default)
