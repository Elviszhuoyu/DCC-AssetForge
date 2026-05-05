"""Bootstrap default Asset Forge material assets inside the UE plugin mount."""

from __future__ import absolute_import

from asset_forge.unreal.material_package_schema import get_default_material_package_plan
from asset_forge.unreal.property_utils import set_unreal_property
from asset_forge.unreal.unreal_bridge import get_unreal


ASSET_KIND_MATERIAL = "material"
ASSET_KIND_FUNCTION = "material_function"
ASSET_KIND_PARAMETER_COLLECTION = "parameter_collection"


class UnrealMaterialAssetBootstrap(object):
    """Create minimal UE assets required by material binding plans."""

    def __init__(self, unreal_module=None, package_plan=None):
        self.unreal = unreal_module or get_unreal()
        self.package_plan = package_plan or get_default_material_package_plan()

    def plan(self):
        assets = []
        assets.extend(self._planned_assets(self.package_plan.get("materials", []), ASSET_KIND_MATERIAL))
        assets.extend(self._planned_assets(self.package_plan.get("functions", []), ASSET_KIND_FUNCTION))
        assets.extend(self._planned_assets(self.package_plan.get("parameter_collections", []), ASSET_KIND_PARAMETER_COLLECTION))
        return {
            "status": "ready",
            "content_mount": self.package_plan.get("content_mount", ""),
            "directories": list(self.package_plan.get("directories", [])),
            "asset_count": len(assets),
            "assets": assets,
        }

    def bootstrap(self, dry_run=False):
        bootstrap_plan = self.plan()
        report = {
            "status": "skipped" if dry_run else "failed",
            "message": "材质资产预检查完成，未创建资产" if dry_run else "材质资产 Bootstrap 失败",
            "plan": bootstrap_plan,
            "created_assets": [],
            "existing_assets": [],
            "issues": [],
        }
        if self.unreal is None:
            report["issues"].append("当前环境不可用 Unreal Python 模块")
            return report
        if dry_run:
            report["status"] = "skipped"
            return report

        self._ensure_directories(bootstrap_plan.get("directories", []))
        for asset_plan in bootstrap_plan.get("assets", []):
            self._ensure_asset(asset_plan, report)

        report["status"] = "warning" if report["issues"] else "success"
        report["message"] = "默认材质资产 Bootstrap 完成" if not report["issues"] else "默认材质资产 Bootstrap 完成，但存在警告"
        return report

    def _planned_assets(self, items, kind):
        assets = []
        for item in items:
            asset_path = item.get("path", "")
            package_path, asset_name = asset_path.rsplit("/", 1)
            assets.append(
                {
                    "kind": kind,
                    "name": asset_name,
                    "path": asset_path,
                    "package_path": package_path,
                    "render_mode": item.get("render_mode", ""),
                    "asset_family": item.get("asset_family", ""),
                    "factory": self._factory_name(kind),
                    "asset_class": self._asset_class_name(kind),
                }
            )
        return assets

    def _ensure_directories(self, directories):
        library = getattr(self.unreal, "EditorAssetLibrary", None)
        if not library or not hasattr(library, "make_directory"):
            return
        for directory in directories:
            library.make_directory(directory)

    def _ensure_asset(self, asset_plan, report):
        asset_path = asset_plan.get("path", "")
        if self._asset_exists(asset_path):
            report["existing_assets"].append(asset_path)
            return

        factory_class = getattr(self.unreal, asset_plan.get("factory", ""), None)
        asset_class = getattr(self.unreal, asset_plan.get("asset_class", ""), None)
        if factory_class is None or asset_class is None:
            report["issues"].append("当前 UE Python API 不支持创建资产：{0}".format(asset_path))
            return

        asset = self.unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            asset_plan.get("name", ""),
            asset_plan.get("package_path", ""),
            asset_class,
            factory_class(),
        )
        if not asset:
            report["issues"].append("资产创建失败：{0}".format(asset_path))
            return

        if asset_plan.get("kind") == ASSET_KIND_MATERIAL:
            self._configure_material(asset, asset_plan)
        self._save_asset(asset_path)
        report["created_assets"].append(asset_path)

    def _configure_material(self, material_asset, asset_plan):
        blend_mode = self._blend_mode(asset_plan.get("render_mode", ""))
        if blend_mode is not None:
            set_unreal_property(material_asset, "blend_mode", blend_mode)

    def _blend_mode(self, render_mode):
        blend_enum = getattr(self.unreal, "BlendMode", None)
        if blend_enum is None:
            return None
        lookup = {
            "opaque": "BLEND_OPAQUE",
            "masked": "BLEND_MASKED",
            "translucent": "BLEND_TRANSLUCENT",
        }
        enum_name = lookup.get(render_mode)
        return getattr(blend_enum, enum_name, None) if enum_name else None

    def _asset_exists(self, asset_path):
        library = getattr(self.unreal, "EditorAssetLibrary", None)
        if library and hasattr(library, "does_asset_exist"):
            return bool(library.does_asset_exist(asset_path))
        if library and hasattr(library, "load_asset"):
            return bool(library.load_asset(asset_path))
        return False

    def _save_asset(self, asset_path):
        library = getattr(self.unreal, "EditorAssetLibrary", None)
        if library and hasattr(library, "save_asset"):
            library.save_asset(asset_path)

    def _factory_name(self, kind):
        return {
            ASSET_KIND_MATERIAL: "MaterialFactoryNew",
            ASSET_KIND_FUNCTION: "MaterialFunctionFactoryNew",
            ASSET_KIND_PARAMETER_COLLECTION: "MaterialParameterCollectionFactoryNew",
        }[kind]

    def _asset_class_name(self, kind):
        return {
            ASSET_KIND_MATERIAL: "Material",
            ASSET_KIND_FUNCTION: "MaterialFunction",
            ASSET_KIND_PARAMETER_COLLECTION: "MaterialParameterCollection",
        }[kind]


def plan_default_material_assets():
    return UnrealMaterialAssetBootstrap().plan()


def bootstrap_default_material_assets(dry_run=False):
    return UnrealMaterialAssetBootstrap().bootstrap(dry_run)
