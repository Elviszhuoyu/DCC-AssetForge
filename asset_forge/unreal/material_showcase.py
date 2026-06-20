"""Material showcase planning and optional UE scene generation."""

from __future__ import absolute_import

import os

from asset_forge.unreal.material_package_schema import get_default_material_package_plan


SHOWCASE_DIRECTORY = "/AssetForge/Showcase"
SHOWCASE_LEVEL_PATH = SHOWCASE_DIRECTORY + "/LV_AF_Material_Showcase"

REQUIRED_SHOWCASE_ROLES = {
    "props_default",
    "props_masked_base_alpha",
    "props_masked_separate_mask",
    "props_emissive",
    "props_dirty_wear",
    "props_metal",
    "props_rubber",
    "environment_default",
    "environment_masked_base_alpha",
    "environment_masked_separate_mask",
    "environment_emissive",
    "environment_tile_floor",
    "environment_worn_wall",
    "character_default",
    "character_skin",
}


def get_default_material_showcase_plan(material_plan=None):
    """Return the product preview layout for generated material presets."""
    active_plan = material_plan or get_default_material_package_plan()
    instances = {item["name"]: item for item in active_plan.get("material_instances", [])}
    rows = [
        _row(
            "Props",
            0,
            [
                ("props_default", "MI_AF_Props_Default", "Baseline prop PBR"),
                ("props_masked_base_alpha", "MI_AF_Props_Masked", "BaseColor alpha mask"),
                ("props_masked_separate_mask", "MI_AF_Props_Masked_SeparateMask", "Separate opacity mask"),
                ("props_emissive", "MI_AF_Props_Emissive", "Emissive switch branch"),
                ("props_dirty_wear", "MI_AF_Props_DirtyWear", "Wear and imperfection mask"),
                ("props_metal", "MI_AF_Props_MetalPanel", "Packed ARM metal"),
                ("props_rubber", "MI_AF_Props_RubberMatte", "High roughness rubber"),
            ],
            instances,
        ),
        _row(
            "Environment",
            1,
            [
                ("environment_default", "MI_AF_Environment_Default", "Baseline modular surface"),
                ("environment_masked_base_alpha", "MI_AF_Environment_Masked", "BaseColor alpha cutout"),
                ("environment_masked_separate_mask", "MI_AF_Environment_Masked_SeparateMask", "Separate mask cutout"),
                ("environment_emissive", "MI_AF_Environment_Emissive", "Panel emissive branch"),
                ("environment_tile_floor", "MI_AF_Environment_TileFloor", "Tiled floor UV preview"),
                ("environment_worn_wall", "MI_AF_Environment_WornWall", "Worn repeated wall"),
            ],
            instances,
        ),
        _row(
            "Character",
            2,
            [
                ("character_default", "MI_AF_Character_Default", "Baseline character surface"),
                ("character_skin", "MI_AF_Character_SkinPreview", "Warm skin subsurface preview"),
            ],
            instances,
        ),
    ]
    return {
        "status": "planned",
        "directory": SHOWCASE_DIRECTORY,
        "level_path": SHOWCASE_LEVEL_PATH,
        "mesh_path": "/Engine/BasicShapes/Sphere.Sphere",
        "label_actor": "TextRenderActor",
        "rows": rows,
    }


def validate_material_showcase_plan(showcase_plan=None, material_plan=None):
    """Return issues that would make the showcase unable to validate presets."""
    active_material_plan = material_plan or get_default_material_package_plan()
    active_showcase_plan = showcase_plan or get_default_material_showcase_plan(active_material_plan)
    instances = {item["path"]: item for item in active_material_plan.get("material_instances", [])}
    issues = []
    roles = set()
    labels = set()
    positions = set()

    if active_showcase_plan.get("level_path") != SHOWCASE_LEVEL_PATH:
        issues.append("showcase level must be {0}".format(SHOWCASE_LEVEL_PATH))

    for row in active_showcase_plan.get("rows", []):
        if not row.get("entries"):
            issues.append("showcase row has no entries: {0}".format(row.get("name", "")))
        for entry in row.get("entries", []):
            role = entry.get("role", "")
            label = entry.get("label", "")
            material_path = entry.get("material_instance_path", "")
            position = tuple(entry.get("location", []))
            roles.add(role)
            if label in labels:
                issues.append("duplicate showcase label: {0}".format(label))
            labels.add(label)
            if position in positions:
                issues.append("duplicate showcase location: {0}".format(position))
            positions.add(position)
            if material_path not in instances:
                issues.append("showcase role {0} references missing material instance: {1}".format(role, material_path))

    missing_roles = sorted(REQUIRED_SHOWCASE_ROLES.difference(roles))
    if missing_roles:
        issues.append("showcase missing roles: {0}".format(", ".join(missing_roles)))

    return issues


def build_material_showcase_report(material_plan=None):
    """Return a compact report for product readiness gates."""
    active_material_plan = material_plan or get_default_material_package_plan()
    showcase_plan = get_default_material_showcase_plan(active_material_plan)
    issues = validate_material_showcase_plan(showcase_plan, active_material_plan)
    entry_count = sum(len(row.get("entries", [])) for row in showcase_plan.get("rows", []))
    return {
        "status": "pass" if not issues else "error",
        "issue_count": len(issues),
        "issues": issues,
        "level_path": showcase_plan.get("level_path", ""),
        "category_count": len(showcase_plan.get("rows", [])),
        "entry_count": entry_count,
        "roles": sorted(
            entry.get("role", "")
            for row in showcase_plan.get("rows", [])
            for entry in row.get("entries", [])
        ),
    }


class UnrealMaterialShowcaseBuilder(object):
    """Build a lightweight UE level that previews every default material preset."""

    def __init__(self, unreal_module=None, material_plan=None, showcase_plan=None):
        self.unreal = unreal_module
        self.material_plan = material_plan or get_default_material_package_plan()
        self.showcase_plan = showcase_plan or get_default_material_showcase_plan(self.material_plan)

    def build(self):
        report = {
            "status": "skipped",
            "level_path": self.showcase_plan.get("level_path", SHOWCASE_LEVEL_PATH),
            "created_actors": [],
            "issues": [],
            "entry_count": 0,
        }
        issues = validate_material_showcase_plan(self.showcase_plan, self.material_plan)
        if issues:
            report["status"] = "error"
            report["issues"].extend(issues)
            return report
        if self.unreal is None:
            report["issues"].append("Unreal Python module is not available.")
            return report

        editor_level_library = getattr(self.unreal, "EditorLevelLibrary", None)
        editor_asset_library = getattr(self.unreal, "EditorAssetLibrary", None)
        if editor_level_library is None or not hasattr(editor_level_library, "new_level"):
            report["issues"].append("EditorLevelLibrary.new_level is not available.")
            return report
        if editor_asset_library is None:
            report["issues"].append("EditorAssetLibrary is not available.")
            return report

        try:
            if hasattr(editor_asset_library, "make_directory"):
                editor_asset_library.make_directory(self.showcase_plan.get("directory", SHOWCASE_DIRECTORY))
            if self._showcase_level_exists(editor_asset_library):
                report["status"] = "skipped"
                report["entry_count"] = self._planned_entry_count()
                report["message"] = "Material showcase level already exists; skipped rebuild to avoid deleting an open world asset."
                return report
            self._delete_existing_showcase_level(editor_asset_library)
            editor_level_library.new_level(self.showcase_plan.get("level_path", SHOWCASE_LEVEL_PATH))
            self._spawn_preview_grid(report)
            self._spawn_lighting(report)
            self._save_current_level(editor_level_library, editor_asset_library, report)
            report["status"] = "success" if not report["issues"] else "warning"
        except Exception as exc:
            report["status"] = "error"
            report["issues"].append("Material showcase build failed: {0}".format(exc))
        return report

    def _spawn_preview_grid(self, report):
        mesh = self._load_asset(self.showcase_plan.get("mesh_path", ""))
        static_mesh_actor_class = getattr(self.unreal, "StaticMeshActor", None)
        text_actor_class = getattr(self.unreal, "TextRenderActor", None)
        if static_mesh_actor_class is None:
            report["issues"].append("StaticMeshActor is not available.")
            return
        if mesh is None:
            report["issues"].append("Showcase mesh is missing: {0}".format(self.showcase_plan.get("mesh_path", "")))
            return

        for row in self.showcase_plan.get("rows", []):
            for entry in row.get("entries", []):
                actor = self._spawn_actor(static_mesh_actor_class, entry.get("location", [0, 0, 0]), [0, 0, 0])
                if actor is None:
                    report["issues"].append("Failed to spawn showcase actor: {0}".format(entry.get("label", "")))
                    continue
                self._set_actor_label(actor, "AF_" + entry.get("role", "preview"))
                self._configure_static_mesh_actor(actor, mesh, entry.get("material_instance_path", ""), report)
                report["created_actors"].append(entry.get("role", ""))
                report["entry_count"] += 1
                if text_actor_class is not None:
                    self._spawn_label(text_actor_class, entry)

    def _spawn_lighting(self, report):
        directional_class = getattr(self.unreal, "DirectionalLight", None)
        sky_class = getattr(self.unreal, "SkyLight", None)
        camera_class = getattr(self.unreal, "CameraActor", None)
        if directional_class is not None:
            actor = self._spawn_actor(directional_class, [-480, -560, 640], [-38, -35, 0])
            self._set_actor_label(actor, "AF_Showcase_KeyLight")
        if sky_class is not None:
            actor = self._spawn_actor(sky_class, [0, 0, 260], [0, 0, 0])
            self._set_actor_label(actor, "AF_Showcase_SkyLight")
        if camera_class is not None:
            actor = self._spawn_actor(camera_class, [-560, -720, 360], [-18, 0, -35])
            self._set_actor_label(actor, "AF_Showcase_Camera")

    def _spawn_label(self, text_actor_class, entry):
        location = list(entry.get("location", [0, 0, 0]))
        location[2] = location[2] - 95
        actor = self._spawn_actor(text_actor_class, location, [0, 0, 0])
        if actor is None:
            return
        self._set_actor_label(actor, "AF_Label_" + entry.get("role", "preview"))
        component = self._get_component(actor, "TextRenderComponent")
        if component is None:
            return
        self._set_editor_property(component, "text", entry.get("label", ""))
        self._set_editor_property(component, "world_size", 22.0)
        self._set_editor_property(component, "horizontal_alignment", self._enum_value("HorizTextAligment", "EHTA_Center"))

    def _configure_static_mesh_actor(self, actor, mesh, material_path, report):
        component = self._get_component(actor, "StaticMeshComponent")
        if component is None:
            component = getattr(actor, "static_mesh_component", None)
        if component is None:
            report["issues"].append("Static mesh component is missing on showcase actor.")
            return
        if hasattr(component, "set_static_mesh"):
            component.set_static_mesh(mesh)
        else:
            self._set_editor_property(component, "static_mesh", mesh)
        material = self._load_asset(material_path)
        if material is None:
            report["issues"].append("Showcase material is missing: {0}".format(material_path))
            return
        if hasattr(component, "set_material"):
            component.set_material(0, material)
        else:
            self._set_editor_property(component, "override_materials", [material])

    def _spawn_actor(self, actor_class, location, rotation):
        editor_level_library = getattr(self.unreal, "EditorLevelLibrary", None)
        spawn = getattr(editor_level_library, "spawn_actor_from_class", None)
        if spawn is None:
            return None
        return spawn(actor_class, self._vector(location), self._rotator(rotation))

    def _load_asset(self, asset_path):
        library = getattr(self.unreal, "EditorAssetLibrary", None)
        if not library or not hasattr(library, "load_asset"):
            return None
        return library.load_asset(asset_path)

    def _get_component(self, actor, component_name):
        component_class = getattr(self.unreal, component_name, None)
        getter = getattr(actor, "get_component_by_class", None)
        if component_class is not None and getter is not None:
            try:
                return getter(component_class)
            except Exception:
                return None
        return None

    def _set_actor_label(self, actor, label):
        if actor is not None and hasattr(actor, "set_actor_label"):
            actor.set_actor_label(label)

    def _set_editor_property(self, target, name, value):
        if target is None or value is None:
            return
        setter = getattr(target, "set_editor_property", None)
        if setter is not None:
            setter(name, value)
        else:
            setattr(target, name, value)

    def _vector(self, values):
        vector_class = getattr(self.unreal, "Vector", None)
        values = list(values or [0, 0, 0])
        if vector_class is None:
            return values
        return vector_class(float(values[0]), float(values[1]), float(values[2]))

    def _rotator(self, values):
        rotator_class = getattr(self.unreal, "Rotator", None)
        values = list(values or [0, 0, 0])
        if rotator_class is None:
            return values
        return rotator_class(float(values[0]), float(values[1]), float(values[2]))

    def _enum_value(self, enum_name, value_name):
        enum_class = getattr(self.unreal, enum_name, None)
        if enum_class is None:
            return None
        return getattr(enum_class, value_name, None)

    def _save_current_level(self, editor_level_library, editor_asset_library, report):
        loading_saving = getattr(self.unreal, "EditorLoadingAndSavingUtils", None)
        if loading_saving is not None and hasattr(loading_saving, "save_current_level"):
            loading_saving.save_current_level()
            return
        if loading_saving is not None and hasattr(loading_saving, "save_dirty_packages"):
            loading_saving.save_dirty_packages(True, True)
            return
        if hasattr(editor_asset_library, "save_asset"):
            editor_asset_library.save_asset(self.showcase_plan.get("level_path", SHOWCASE_LEVEL_PATH))
            return
        report["issues"].append("No available API to save the material showcase level.")

    def _showcase_level_exists(self, editor_asset_library):
        exists = getattr(editor_asset_library, "does_asset_exist", None)
        if exists is None:
            return False
        try:
            return bool(exists(self.showcase_plan.get("level_path", SHOWCASE_LEVEL_PATH)))
        except Exception:
            return False

    def _planned_entry_count(self):
        return sum(len(row.get("entries", [])) for row in self.showcase_plan.get("rows", []))

    def _delete_existing_showcase_level(self, editor_asset_library):
        level_path = self.showcase_plan.get("level_path", SHOWCASE_LEVEL_PATH)
        if hasattr(editor_asset_library, "delete_asset") and hasattr(editor_asset_library, "does_asset_exist"):
            try:
                if editor_asset_library.does_asset_exist(level_path):
                    editor_asset_library.delete_asset(level_path)
            except Exception:
                pass
        disk_path = self._asset_disk_path(level_path, ".umap")
        if disk_path and os.path.isfile(disk_path):
            try:
                os.remove(disk_path)
            except Exception:
                pass

    def _asset_disk_path(self, asset_path, extension):
        paths = getattr(self.unreal, "Paths", None)
        if paths is None or not asset_path.startswith("/AssetForge/"):
            return ""
        plugins_dir_method = getattr(paths, "project_plugins_dir", None) or getattr(paths, "ProjectPluginsDir", None)
        if plugins_dir_method is None:
            return ""
        try:
            content_root = os.path.join(plugins_dir_method(), "AssetForge", "Content")
        except Exception:
            return ""
        relative_path = asset_path[len("/AssetForge/") :].replace("/", os.sep) + extension
        candidate = os.path.normpath(os.path.join(content_root, relative_path))
        allowed_root = os.path.normpath(content_root)
        if not candidate.startswith(allowed_root):
            return ""
        return candidate


def _row(name, row_index, entries, instances):
    row_y = row_index * -260
    return {
        "name": name,
        "entries": [
            _entry(role, instance_name, label, column_index, row_y, instances)
            for column_index, (role, instance_name, label) in enumerate(entries)
        ],
    }


def _entry(role, instance_name, label, column_index, row_y, instances):
    instance = instances.get(instance_name, {})
    return {
        "role": role,
        "label": label,
        "material_instance_name": instance_name,
        "material_instance_path": instance.get("path", "/AssetForge/MaterialInstances/" + instance_name),
        "location": [column_index * 220, row_y, 100],
    }
