# -*- coding: utf-8 -*-
"""Read saved UE assets and their referencers for a scoped editor review."""

import re

from asset_forge.unreal.unreal_bridge import get_unreal
from asset_forge.unreal.material_texture_binding_validator import is_official_texture_default, official_texture_parameter_usage


def package_path(value):
    return str(value).split(".", 1)[0]


def _name(obj):
    return str(obj.get_class().get_name())


def _path(obj):
    return package_path(obj.get_path_name())


def _enum(value):
    return str(getattr(value, "name", value))


def _try(operation):
    try:
        return operation()
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return None


class ReviewHost:
    def __init__(self, unreal_module=None):
        self.ue = unreal_module or get_unreal()
        if self.ue is None:
            raise RuntimeError("该检查需要 Unreal Editor。")
        self.lib = self.ue.EditorAssetLibrary
        self.registry = self.ue.AssetRegistryHelpers.get_asset_registry()
        self.material_cache = {}
        # A fresh commandlet can see saved packages before its Asset Registry has indexed them.
        self.registry_ready = _try(self._ready_registry)

    def _ready_registry(self):
        if not self.registry.is_search_all_assets():
            self.registry.search_all_assets(True)
        elif self.registry.is_loading_assets():
            self.registry.wait_for_completion()
        return self.registry.is_search_all_assets() and not self.registry.is_loading_assets()

    def load(self, path):
        return _try(lambda: self.lib.load_asset(path)) or _try(lambda: self.ue.load_asset(path))

    def kind(self, obj):
        return _name(obj) if obj is not None else "unknown"

    def mesh(self, obj, policy):
        facts = {"lod0_triangles": _try(lambda: obj.get_num_triangles(0)),
                 "lod_count": _try(obj.get_num_lods) if hasattr(obj, "get_num_lods") else None,
                 "slots": [], "textures": {}, "unreadable_bindings": [], "required_texture_bindings": {}}
        if policy.get("require_simple_collision"):
            def collision_count():
                subsystem = (self.ue.get_editor_subsystem(self.ue.StaticMeshEditorSubsystem)
                             or self.ue.get_default_object(self.ue.StaticMeshEditorSubsystem))
                return subsystem.get_simple_collision_count(obj)
            facts["simple_collision_count"] = _try(collision_count)
        slots = _try(lambda: obj.get_editor_property("static_materials"))
        if slots is None:
            facts["slots"] = None
            return facts
        for index, slot in enumerate(slots):
            name = _try(lambda: str(slot.get_editor_property("material_slot_name"))) or str(index)
            try:
                material = slot.get_editor_property("material_interface")
                material_path = _path(material) if material else ""
            except (AttributeError, RuntimeError, TypeError, ValueError):
                material, material_path = None, None
            facts["slots"].append({"name": name, "index": index, "material": material_path})
            if not material or material_path in policy["default_materials"]:
                continue
            if material_path not in self.material_cache:
                self.material_cache[material_path] = self._material_textures(material, policy)
            textures, complete, required = self.material_cache[material_path]
            if not complete:
                facts["unreadable_bindings"].append(material_path)
            elif required:
                facts["required_texture_bindings"][material_path] = required
            for path, roles in textures.items():
                facts["textures"].setdefault(path, set()).update(roles)
        facts["textures"] = {path: sorted(roles) for path, roles in sorted(facts["textures"].items())}
        facts["unreadable_bindings"] = sorted(set(facts["unreadable_bindings"]))
        return facts

    def _material_textures(self, material, policy):
        editing = self.ue.MaterialEditingLibrary
        textures, required = {}, {}
        try:
            is_base = _name(material) == "Material"
            base = material if is_base else material.get_base_material()
            profile_parent = _path(base) in policy["profile_parents"]
            trusted = profile_parent or policy["parameter_roles_explicit"]
            required_names = {}
            if profile_parent:
                required = dict.fromkeys(policy["required_texture_parameters"], "")
                required_names = {name.casefold(): parameter
                                  for parameter, names in policy["required_texture_parameters"].items() for name in names}
            defaults = set()
            for parameter in editing.get_texture_parameter_names(material):
                name = str(parameter)
                default = editing.get_material_default_texture_parameter_value(base, name)
                if default is not None:
                    defaults.add(_path(default))
                texture = default if is_base else editing.get_material_instance_texture_parameter_value(material, name)
                if texture is not None:
                    role = policy["parameter_roles"].get(name) if trusted else None
                    texture_path = str(texture.get_path_name())
                    required_parameter = required_names.get(name.casefold())
                    if required_parameter:
                        required[required_parameter] = texture_path
                        if is_official_texture_default(texture_path):
                            continue
                    default_usage = role or official_texture_parameter_usage(name)
                    if trusted and default_usage and is_official_texture_default(texture_path, default_usage):
                        continue
                    textures.setdefault(package_path(texture_path), set()).add(role or "unknown")
            # Include texture samples that have no named parameter; their roles need a contract.
            for texture in editing.get_used_textures(base):
                path = _path(texture)
                if path not in defaults:
                    textures.setdefault(path, set()).add("unknown")
            return textures, True, required
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return textures, False, {}

    def texture(self, obj):
        tags = _try(lambda: self.lib.get_tag_values(_path(obj)))
        dimensions = None
        if tags is not None:
            sizes = next((str(v) for k, v in tags.items() if str(k) == "Dimensions"), "")
            match = re.fullmatch(r"\s*(\d+)\s*x\s*(\d+)\s*", sizes, re.IGNORECASE)
            if match and all(int(n) > 0 for n in match.groups()):
                dimensions = [int(n) for n in match.groups()]
        return {"srgb": _try(lambda: obj.get_editor_property("srgb")),
                "compression": _try(lambda: _enum(obj.get_editor_property("compression_settings"))),
                "source_size": dimensions}

    def impact(self, path, selected, observed_meshes):
        refs, meshes, materials = set(), set(), set()
        done, active = set(), set()
        problems = []

        def visit(node):
            if node in active:
                problems.append("引用链存在循环")
                return
            if node in done:
                return
            active.add(node)
            parents = self.registry.get_referencers(node, options)
            if parents is None:
                raise ValueError("注册表未能读取引用")
            parents = sorted({str(p) for p in parents if str(p) != node})
            if not parents and node != path:
                problems.append("有独立材质引用且无法归属到选中网格")
            for parent in parents:
                refs.add(parent)
                data = self.registry.get_assets_by_package_name(parent, True)
                if not data or len(data) != 1:
                    problems.append("引用包不能唯一识别")
                    continue
                kind = str(data[0].asset_class_path.asset_name)
                if kind == "StaticMesh":
                    meshes.add(parent)
                elif kind in ("Material", "MaterialInstanceConstant", "MaterialFunction", "MaterialFunctionInstance"):
                    if kind in ("Material", "MaterialInstanceConstant"):
                        materials.add(parent)
                    visit(parent)
                else:
                    problems.append("包含选区以外或不支持的引用类型 " + kind)
            active.remove(node)
            done.add(node)

        try:
            if not self.registry_ready or self.registry.is_loading_assets():
                raise ValueError("注册表尚未完成全项目扫描")
            saving = self.ue.EditorLoadingAndSavingUtils
            dirty = list(saving.get_dirty_content_packages()) + list(saving.get_dirty_map_packages())
            if any(not str(item.get_name()).startswith(("/Temp/", "/Engine/Transient")) for item in dirty):
                raise ValueError("存在尚未保存的包，磁盘注册表不能确认当前引用范围")
            if not self.registry.get_assets_by_package_name(path, True):
                raise ValueError("贴图尚未登记到磁盘包")
            options = self.ue.AssetRegistryDependencyOptions(
                include_soft_package_references=True, include_hard_package_references=True,
                include_searchable_names=True, include_soft_management_references=True,
                include_hard_management_references=True)
            visit(path)
            if set(observed_meshes) != (meshes & selected):
                problems.append("网格实读与注册表的引用范围不一致")
        except (AttributeError, RuntimeError, TypeError, ValueError, RecursionError) as exc:
            problems.append(str(exc))
        if not path.startswith("/Game/"):
            problems.append("项目内容目录以外的贴图需要人工处理")
        if not meshes.issubset(selected):
            problems.append("贴图有选区以外的网格引用")
        return {"referencers": sorted(refs), "mesh_owners": sorted(meshes), "materials": sorted(materials),
                "can_apply": not problems, "reason": "；".join(sorted(set(problems)))}

    def referenced_roles(self, path, material_paths, policy):
        roles = set()
        for material_path in material_paths:
            if material_path not in self.material_cache:
                material = self.load(material_path)
                self.material_cache[material_path] = self._material_textures(material, policy)
            bindings, complete, _ = self.material_cache[material_path]
            roles.update(bindings.get(path, ()))
            if not complete:
                roles.add("unknown")
        return roles

    def save_settings(self, path, old, new):
        obj = self.load(path)
        if obj is None:
            raise ValueError("无法加载贴图")
        properties = {"compression": "compression_settings", "srgb": "srgb"}
        original = {key: obj.get_editor_property(field) for key, field in properties.items()}
        def settings():
            return {"compression": _enum(obj.get_editor_property("compression_settings")),
                    "srgb": obj.get_editor_property("srgb")}
        if settings() != old:
            raise ValueError("保存前属性已变化，请重新检查")
        saved = False
        try:
            # Changing compression can change sRGB as a side effect.
            if old["compression"] != new["compression"]:
                enum = getattr(self.ue.TextureCompressionSettings, new["compression"])
                obj.set_editor_property("compression_settings", enum)
            if obj.get_editor_property("srgb") != new["srgb"]:
                obj.set_editor_property("srgb", new["srgb"])
            if settings() != new:
                raise RuntimeError("贴图属性读回失败")
            saved = self.lib.save_loaded_asset(obj, False)
            if not saved:
                raise RuntimeError("贴图保存失败")
            if settings() != new:
                raise RuntimeError("保存后贴图属性与计划不符")
        except Exception:
            for key, field in properties.items():
                obj.set_editor_property(field, original[key])
            if saved and not self.lib.save_loaded_asset(obj, False):
                raise RuntimeError("保存后读回失败且无法恢复磁盘旧值，请核实此贴图")
            raise

