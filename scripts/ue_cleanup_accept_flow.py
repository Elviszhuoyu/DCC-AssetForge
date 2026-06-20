# -*- coding: utf-8 -*-
"""UE Editor Python runner: clean one Asset Forge target path, then run accept-flow."""

from __future__ import absolute_import

import json
import os
import sys


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ensure_repo_on_path():
    root = _repo_root()
    normalized = os.path.normcase(os.path.abspath(root))
    sys.path[:] = [item for item in sys.path if os.path.normcase(os.path.abspath(item)) != normalized]
    sys.path.insert(0, root)
    return root


def _purge_asset_forge_modules():
    for name in sorted(list(sys.modules.keys()), reverse=True):
        if name == "asset_forge" or name.startswith("asset_forge."):
            del sys.modules[name]


def _read_manifest(package_dir):
    manifest_path = os.path.join(package_dir, os.path.basename(package_dir) + "_manifest.json")
    if not os.path.exists(manifest_path):
        candidates = [
            os.path.join(package_dir, name)
            for name in os.listdir(package_dir)
            if name.endswith("_manifest.json") or name == "manifest.json"
        ]
        if not candidates:
            raise RuntimeError("未找到 manifest: {0}".format(package_dir))
        manifest_path = candidates[0]
    with open(manifest_path, "r", encoding="utf-8") as stream:
        return json.load(stream), manifest_path


def _delete_assets_under(target_path):
    import unreal

    library = getattr(unreal, "EditorAssetLibrary", None)
    if library is None:
        return {"target_path": target_path, "deleted_assets": [], "existing_assets": [], "status": "skipped", "message": "EditorAssetLibrary unavailable"}
    existing = list(library.list_assets(target_path, True, False) or [])
    deleted = []
    failed = []
    for asset_path in sorted(existing, reverse=True):
        try:
            if library.delete_asset(asset_path):
                deleted.append(asset_path)
            else:
                failed.append(asset_path)
        except Exception:
            failed.append(asset_path)
    return {
        "target_path": target_path,
        "status": "success" if not failed else "warning",
        "existing_assets": existing,
        "deleted_assets": deleted,
        "failed_assets": failed,
    }


def main(argv=None):
    argv = list(argv or sys.argv[1:])
    if len(argv) < 2:
        raise RuntimeError("Usage: ue_cleanup_accept_flow.py <package_dir> <report_path> [target_path]")
    repo_root = _ensure_repo_on_path()
    _purge_asset_forge_modules()
    package_dir = argv[0]
    report_path = argv[1]
    manifest, manifest_path = _read_manifest(package_dir)
    target_path_override = argv[2] if len(argv) > 2 else ""
    target_path = target_path_override or manifest.get("target_path", "")
    if not target_path:
        raise RuntimeError("manifest 缺少 target_path: {0}".format(manifest_path))

    cleanup = _delete_assets_under(target_path)

    from asset_forge.unreal.acceptance_runner import run_asset_forge_package_acceptance

    report = run_asset_forge_package_acceptance(
        package_dir,
        report_path,
        run_import=True,
        auto_bootstrap_material_assets=True,
        strict=False,
        block_warnings=False,
        require_import=True,
        import_options=None,
        command_args=["ue_cleanup_accept_flow", package_dir, report_path],
        target_path_override=target_path_override,
    )
    report["cleanup_before_import"] = cleanup
    report["repo_root"] = repo_root.replace("\\", "/")
    from asset_forge.shared.report_schema import normalize_report_value

    report = normalize_report_value(report)
    with open(report_path, "w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, sort_keys=True)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
