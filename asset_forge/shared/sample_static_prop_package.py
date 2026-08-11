"""Offline sample Static Prop package generator for tests and local validation."""

from __future__ import absolute_import

import os
import struct
import zlib

from asset_forge.maya.export_package import build_export_package
from asset_forge.shared.constants import IMPORT_PRESET_STATIC_PROP_HIGH_END_MOBILE, TARGET_PLATFORM_HIGH_END_MOBILE
from asset_forge.shared.manifest_schema import create_manifest, write_manifest
from asset_forge.shared.material_profile_schema import get_default_material_profiles, write_material_profiles
from asset_forge.shared.path_utils import normalize_path
from asset_forge.shared.texture_metadata import apply_texture_metadata


def create_offline_static_prop_package(root_dir, asset_name="SM_AF_Offline_Crate"):
    """Create a tiny DCC AssetForge package without Maya or Unreal."""
    package = build_export_package(root_dir, asset_name)
    _write_static_cube_fbx(package["fbx_path"], asset_name)

    texture_dir = os.path.join(package["package_dir"], "Textures")
    if not os.path.isdir(texture_dir):
        os.makedirs(texture_dir)

    base_color = os.path.join(texture_dir, asset_name + "_BaseColor.png")
    normal = os.path.join(texture_dir, asset_name + "_Normal.tga")
    _write_png(base_color, 64, 64)
    _write_tga(normal, 64, 64)

    textures = [
        _texture_entry(base_color, "base_color", "BaseColor", True, "default"),
        _texture_entry(normal, "normal", "Normal", False, "normalmap"),
    ]
    snapshot_path = os.path.join(package["package_dir"], "material_profiles_snapshot.json")
    write_material_profiles(snapshot_path, get_default_material_profiles())
    material_name = "M_" + asset_name.replace("SM_", "")
    manifest = create_manifest(
        asset_name,
        package["fbx_path"],
        "/Game/AssetForgeOffline",
        checks={},
        score=100,
        target_platform=TARGET_PLATFORM_HIGH_END_MOBILE,
        import_preset=IMPORT_PRESET_STATIC_PROP_HIGH_END_MOBILE,
        package_dir=package["package_dir"],
        material_profile="Props_Opaque_PainterUE_ARM",
        material_profiles_snapshot_path=snapshot_path,
        materials=[{"name": material_name, "textures": textures}],
        material_slots=[{"name": material_name, "index": 0}],
        textures=textures,
        existing_mesh_strategy="overwrite",
        existing_texture_strategy="overwrite",
        existing_material_strategy="reuse",
    )
    write_manifest(package["manifest_path"], manifest)
    return dict(package, manifest=manifest, textures=textures)


def _texture_entry(path, usage, parameter, srgb, compression):
    entry = {
        "node": "offline_" + usage,
        "path": normalize_path(path),
        "source_path": normalize_path(path),
        "package_path": normalize_path(path),
        "copied": True,
        "source_type": "offline_sample",
        "source_label": "离线样例贴图",
        "usage": usage,
        "parameter": parameter,
        "srgb": srgb,
        "compression": compression,
    }
    return apply_texture_metadata(entry, path)


def _write_png(path, width, height):
    pixels = []
    for y in range(height):
        row = []
        for x in range(width):
            checker = ((x // 8) + (y // 8)) % 2
            row.append((142, 154, 168, 255) if checker else (70, 76, 86, 255))
        pixels.append(row)

    raw = b"".join(b"\x00" + b"".join(bytes(pixel) for pixel in row) for row in pixels)
    data = b"\x89PNG\r\n\x1a\n"
    data += _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    data += _png_chunk(b"IDAT", zlib.compress(raw))
    data += _png_chunk(b"IEND", b"")
    with open(path, "wb") as stream:
        stream.write(data)


def _png_chunk(chunk_type, payload):
    length = struct.pack(">I", len(payload))
    crc = struct.pack(">I", zlib.crc32(chunk_type + payload) & 0xFFFFFFFF)
    return length + chunk_type + payload + crc


def _write_tga(path, width, height):
    header = bytearray(18)
    header[2] = 2
    header[12:14] = struct.pack("<H", width)
    header[14:16] = struct.pack("<H", height)
    header[16] = 32
    header[17] = 8 | 32
    with open(path, "wb") as stream:
        stream.write(bytes(header))
        for y in range(height):
            for x in range(width):
                ridge = 10 if ((x // 8) + (y // 8)) % 2 else 0
                stream.write(bytes((255 - ridge, 128 + ridge, 128 - ridge, 255)))


def _write_static_cube_fbx(path, asset_name):
    vertices = [
        -50, -50, -50,
        50, -50, -50,
        50, 50, -50,
        -50, 50, -50,
        -50, -50, 50,
        50, -50, 50,
        50, 50, 50,
        -50, 50, 50,
    ]
    polygon_indices = [
        0, 1, 2, -4,
        4, 7, 6, -6,
        0, 4, 5, -2,
        3, 2, 6, -8,
        0, 3, 7, -5,
        1, 5, 6, -3,
    ]
    normals = []
    for normal in (
        (0, 0, -1),
        (0, 0, 1),
        (0, -1, 0),
        (0, 1, 0),
        (-1, 0, 0),
        (1, 0, 0),
    ):
        normals.extend(normal * 4)
    uvs = (0, 0, 1, 0, 1, 1, 0, 1) * 6
    material_name = "M_" + asset_name.replace("SM_", "")
    content = _fbx_template(asset_name, material_name, vertices, polygon_indices, normals, uvs)
    with open(path, "w", encoding="ascii", newline="\n") as stream:
        stream.write(content)


def _fbx_template(asset_name, material_name, vertices, polygon_indices, normals, uvs):
    return """; FBX 7.4.0 project file
FBXHeaderExtension:  {{
	FBXHeaderVersion: 1003
	FBXVersion: 7400
	Creator: "DCC AssetForge offline sample"
}}
GlobalSettings:  {{
	Version: 1000
	Properties70:  {{
		P: "UpAxis", "int", "Integer", "",1
		P: "UpAxisSign", "int", "Integer", "",1
		P: "FrontAxis", "int", "Integer", "",2
		P: "FrontAxisSign", "int", "Integer", "",1
		P: "CoordAxis", "int", "Integer", "",0
		P: "CoordAxisSign", "int", "Integer", "",1
		P: "UnitScaleFactor", "double", "Number", "",1
	}}
}}
Documents:  {{
	Count: 1
	Document: 1, "Scene", "Scene" {{
		RootNode: 0
	}}
}}
Definitions:  {{
	Version: 100
	Count: 3
	ObjectType: "Geometry" {{ Count: 1 }}
	ObjectType: "Model" {{ Count: 1 }}
	ObjectType: "Material" {{ Count: 1 }}
}}
Objects:  {{
	Geometry: 100000, "Geometry::{asset_name}Mesh", "Mesh" {{
		Vertices: *{vertex_count} {{
			a: {vertices}
		}}
		PolygonVertexIndex: *{polygon_index_count} {{
			a: {polygon_indices}
		}}
		GeometryVersion: 124
		LayerElementNormal: 0 {{
			Version: 101
			Name: ""
			MappingInformationType: "ByPolygonVertex"
			ReferenceInformationType: "Direct"
			Normals: *{normal_count} {{
				a: {normals}
			}}
		}}
		LayerElementUV: 0 {{
			Version: 101
			Name: "UVMap"
			MappingInformationType: "ByPolygonVertex"
			ReferenceInformationType: "Direct"
			UV: *{uv_count} {{
				a: {uvs}
			}}
		}}
		LayerElementMaterial: 0 {{
			Version: 101
			Name: ""
			MappingInformationType: "AllSame"
			ReferenceInformationType: "IndexToDirect"
			Materials: *1 {{
				a: 0
			}}
		}}
		Layer: 0 {{
			Version: 100
			LayerElement:  {{
				Type: "LayerElementNormal"
				TypedIndex: 0
			}}
			LayerElement:  {{
				Type: "LayerElementUV"
				TypedIndex: 0
			}}
			LayerElement:  {{
				Type: "LayerElementMaterial"
				TypedIndex: 0
			}}
		}}
	}}
	Model: 100001, "Model::{asset_name}", "Mesh" {{
		Version: 232
		Properties70:  {{
			P: "RotationActive", "bool", "", "",1
			P: "InheritType", "enum", "", "",1
			P: "ScalingMax", "Vector3D", "Vector", "",0,0,0
			P: "DefaultAttributeIndex", "int", "Integer", "",0
		}}
		Shading: T
		Culling: "CullingOff"
	}}
	Material: 100002, "Material::{material_name}", "" {{
		Version: 102
		ShadingModel: "phong"
		MultiLayer: 0
		Properties70:  {{
			P: "DiffuseColor", "Color", "", "A",0.55,0.6,0.66
			P: "SpecularColor", "Color", "", "A",0.08,0.08,0.08
			P: "Shininess", "double", "Number", "",20
		}}
	}}
}}
Connections:  {{
	C: "OO",100000,100001
	C: "OO",100001,0
	C: "OO",100002,100001
}}
""".format(
        asset_name=asset_name,
        material_name=material_name,
        vertex_count=len(vertices),
        vertices=_format_fbx_numbers(vertices),
        polygon_index_count=len(polygon_indices),
        polygon_indices=_format_fbx_numbers(polygon_indices),
        normal_count=len(normals),
        normals=_format_fbx_numbers(normals),
        uv_count=len(uvs),
        uvs=_format_fbx_numbers(uvs),
    )


def _format_fbx_numbers(values):
    formatted = []
    for value in values:
        if isinstance(value, int):
            formatted.append(str(value))
        else:
            formatted.append(("{0:.6f}".format(value)).rstrip("0").rstrip("."))
    return ",".join(formatted)
