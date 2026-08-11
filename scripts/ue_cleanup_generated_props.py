# -*- coding: utf-8 -*-
"""UE Editor Python runner: clean generated DCC AssetForge test folders under /Game/Props."""

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


def main(argv=None):
    argv = list(argv or sys.argv[1:])
    target_path = argv[0] if argv else "/Game/Props"
    report_path = argv[1] if len(argv) > 1 else ""
    repo_root = _ensure_repo_on_path()

    from asset_forge.unreal.editor_menu import cleanup_asset_forge_generated_props
    from asset_forge.shared.report_schema import normalize_report_value

    report = cleanup_asset_forge_generated_props(
        "",
        import_options={"cleanup_target_path": target_path, "confirmed_cleanup": True},
    )
    report["repo_root"] = repo_root.replace("\\", "/")
    report = normalize_report_value(report)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if report_path:
        with open(report_path, "w", encoding="utf-8") as stream:
            stream.write(text)
    print(text)


if __name__ == "__main__":
    main()
