"""Resolve packed maps from proven texture sets without editing Maya or disk assets."""

import os

from asset_forge.maya.material_scanner import valid_texture_count
from asset_forge.shared.path_utils import normalize_path


def apply_scene_textures(scan, profile, scanner):
    rules = {rule["usage"]: rule for rule in profile.get("texture_rules", [])}
    packed = rules.get("packed_arm")
    copies = {}

    def connected(texture):
        key = id(texture)
        if key not in copies:
            entry = copies[key] = dict(texture)
            path = texture.get("path", "")
            if packed and path and scanner.texture_set_identity(path, packed):
                entry["usage"] = "packed_arm"
        return copies[key]

    files_by_directory = {}
    inferred = {}
    separate = []
    materials = []
    for material in scan.get("materials", []):
        textures = [connected(item) for item in material.get("textures", [])]
        source = _connected_set(textures, rules, scanner) if packed else None
        if source:
            directory, set_name = source
            if directory not in files_by_directory:
                files_by_directory[directory] = [path for path in scanner.texture_files_in_directory(directory)
                                                  if os.path.dirname(os.path.realpath(path)) == directory]
            files = files_by_directory[directory]
            matches = _match_set_files(files, set_name, packed, scanner)
            if len(matches) == 1:
                path = matches[0]
                selected = inferred.setdefault(path, {
                    "path": normalize_path(path), "usage": "packed_arm", "source_type": "maya_same_directory_packed",
                    "source_label": "同目录自动补齐", "match_mode": "same_scene_texture_set",
                    "selected_texture_set": set_name,
                })
                textures.append(selected)
            elif all(_match_set_files(files, set_name, rules.get(usage, {"usage": usage}), scanner)
                     for usage in ("roughness", "metallic")):
                separate.append(material.get("name") or material.get("material_name", ""))
        materials.append(dict(material, textures=textures))

    connected_textures = [connected(item) for item in scan.get("textures", [])]
    if not packed:
        return dict(scan, materials=materials, textures=connected_textures)
    paths = {os.path.normcase(os.path.realpath(item["path"])) for item in connected_textures if item.get("path")}
    compiled = connected_textures + [texture for path, texture in inferred.items() if os.path.normcase(path) not in paths]
    return dict(scan, materials=materials, textures=compiled,
                scene_texture_count=valid_texture_count(connected_textures),
                scene_inferred_texture_count=len(inferred),
                scene_separate_texture_materials=separate,
                texture_selection_policy={
                    "primary": "maya_material_assignment", "fallback": "same_directory_packed_texture",
                    "reason": "scene_texture_connections",
                })


def _connected_set(textures, rules, scanner):
    linked = {}
    for texture in textures:
        usage = texture.get("usage")
        path = texture.get("path", "")
        if usage in ("base_color", "normal", "packed_arm") and path and os.path.isfile(path):
            linked.setdefault(usage, {})[os.path.normcase(os.path.realpath(path))] = path
    if linked.get("packed_arm"):
        return None
    if len(linked.get("base_color", {})) != 1 or len(linked.get("normal", {})) != 1:
        return None
    identities = []
    for usage in ("base_color", "normal"):
        if usage not in rules:
            return None
        path = next(iter(linked[usage].values()))
        set_name = scanner.texture_set_identity(path, rules[usage])
        if not set_name:
            return None
        identities.append((os.path.dirname(os.path.realpath(path)), set_name))
    directory, set_name = identities[0]
    if identities[1][0] != directory or identities[1][1].casefold() != set_name.casefold():
        return None
    return directory, set_name


def _match_set_files(files, set_name, rule, scanner):
    name = set_name.casefold()
    return [path for path in files if scanner.texture_set_identity(path, rule).casefold() == name]
