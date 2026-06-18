"""Run Asset Forge UE accept-flow through UnrealEditor-Cmd."""

from __future__ import absolute_import

import json
import sys
import argparse


def _ensure_project_root():
    import os

    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    return project_root


def usage_text():
    return "\n".join(
        [
            "Usage:",
            "  unreal_run_accept_flow_commandlet.py <UnrealEditor-Cmd.exe> <uproject> <package_dir> <report_path> [target_path] [log_path]",
            "  unreal_run_accept_flow_commandlet.py <UnrealEditor-Cmd.exe> <uproject> <package_dir> <report_path> [target_path] [log_path] --with-material-evidence",
            "",
            "Defaults:",
            "  Uses -ddc=InstalledNoZenLocalFallback and forward-slash paths to avoid Zen/DDC and Windows escape noise.",
            "  --with-material-evidence runs a second fresh UE commandlet for material cold-start readback.",
        ]
    )


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Run Asset Forge UE accept-flow through UnrealEditor-Cmd.")
    parser.add_argument("unreal_editor_cmd")
    parser.add_argument("uproject")
    parser.add_argument("package_dir")
    parser.add_argument("report_path")
    parser.add_argument("target_path", nargs="?", default="")
    parser.add_argument("log_path", nargs="?", default="")
    parser.add_argument(
        "--with-material-evidence",
        action="store_true",
        help="Run material cold-start evidence after accept-flow succeeds.",
    )
    parser.add_argument(
        "--material-report",
        default="",
        help="Output path for the material evidence report. Implies --with-material-evidence.",
    )
    parser.add_argument(
        "--material-log",
        default="",
        help="Output path for the material evidence commandlet log.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    _ensure_project_root()
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print(usage_text())
        return 0
    if len(argv) < 4:
        print(usage_text(), file=sys.stderr)
        return 2

    args = parse_args(argv)
    if args.with_material_evidence or args.material_report or args.material_log:
        from asset_forge.unreal.commandlet_runner import run_accept_flow_with_material_evidence_commandlet

        report = run_accept_flow_with_material_evidence_commandlet(
            args.unreal_editor_cmd,
            args.uproject,
            args.package_dir,
            args.report_path,
            target_path=args.target_path,
            log_path=args.log_path,
            material_report_path=args.material_report,
            material_log_path=args.material_log,
        )
    else:
        from asset_forge.unreal.commandlet_runner import run_accept_flow_commandlet

        report = run_accept_flow_commandlet(
            args.unreal_editor_cmd,
            args.uproject,
            args.package_dir,
            args.report_path,
            target_path=args.target_path,
            log_path=args.log_path,
        )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report.get("status") == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
