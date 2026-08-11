"""Launch Unreal Editor with DCC AssetForge-safe defaults."""

from __future__ import absolute_import

import argparse
import json
import sys


def _ensure_project_root():
    import os

    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    return project_root


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Launch Unreal Editor with DDC fallback and crash reporter cleanup.")
    parser.add_argument("unreal_editor")
    parser.add_argument("uproject")
    parser.add_argument("--ddc-mode", default="InstalledNoZenLocalFallback")
    parser.add_argument("--wait-seconds", type=float, default=10.0)
    parser.add_argument("--keep-crash-reporters", action="store_true")
    parser.add_argument("--force-new", action="store_true")
    parser.add_argument("--extra-arg", action="append", default=[])
    return parser.parse_args(argv)


def main(argv=None):
    _ensure_project_root()
    args = parse_args(sys.argv[1:] if argv is None else argv)
    from asset_forge.unreal.commandlet_runner import launch_unreal_editor_safe

    report = launch_unreal_editor_safe(
        args.unreal_editor,
        args.uproject,
        ddc_mode=args.ddc_mode,
        close_crash_reporters=not args.keep_crash_reporters,
        force_new=args.force_new,
        wait_seconds=args.wait_seconds,
        extra_args=args.extra_arg,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.get("status") == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
