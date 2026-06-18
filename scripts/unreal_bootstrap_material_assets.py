from __future__ import absolute_import

import json
import os
import sys


def _repo_python_root():
    here = os.path.abspath(os.path.dirname(__file__))
    return os.path.abspath(os.path.join(here, ".."))


def _ensure_repo_on_path():
    root = _repo_python_root()
    if root not in sys.path:
        sys.path.insert(0, root)


def _purge_asset_forge_modules():
    for name in list(sys.modules):
        if name == "asset_forge" or name.startswith("asset_forge."):
            sys.modules.pop(name, None)


def _project_saved_dir(unreal):
    paths = getattr(unreal, "Paths", None)
    if paths and hasattr(paths, "project_saved_dir"):
        return paths.project_saved_dir()
    return os.path.join(os.getcwd(), "Saved")


def main():
    import unreal

    _ensure_repo_on_path()
    _purge_asset_forge_modules()
    from asset_forge.unreal.material_asset_bootstrap import UnrealMaterialAssetBootstrap
    from asset_forge.shared.report_schema import normalize_report_value

    bootstrap = UnrealMaterialAssetBootstrap(unreal_module=unreal)
    report = normalize_report_value(
        bootstrap.bootstrap(
            dry_run=False,
            cleanup_obsolete_assets="--cleanup-obsolete-assets" in sys.argv[1:],
        )
    )
    saved_dir = _project_saved_dir(unreal)
    output_dir = os.path.join(saved_dir, "AssetForge")
    if not os.path.isdir(output_dir):
        os.makedirs(output_dir)
    output_path = os.path.join(output_dir, "material_bootstrap_report.json")
    with open(output_path, "w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    unreal.log("AssetForge material bootstrap report: {0}".format(output_path.replace("\\", "/")))
    return report


if __name__ == "__main__":
    main()
