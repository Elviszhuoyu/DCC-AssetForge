"""Command line helper for installing the DCC AssetForge UE plugin package."""

from __future__ import absolute_import

import json
import os
import sys


def _configure_stdout():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass


def _ensure_project_root():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    return project_root


def _write_text(stream, text):
    if hasattr(stream, "buffer"):
        stream.buffer.write(text.encode("utf-8"))
    else:
        stream.write(text)


def usage_text():
    return "\n".join(
        [
            "Usage:",
            "  unreal_plugin_install.py <uproject_or_project_dir> [report_path] [--dry-run] [--no-enable]",
            "",
            "Next action:",
            "  传入目标 .uproject 或 UE 项目目录；安装后重启 UE，让 /AssetForge 内容和 Python 菜单入口加载。",
        ]
    )


def plan_install(project_path, source_plugin_dir=None):
    _ensure_project_root()
    from asset_forge.unreal.plugin_installer import plan_assetforge_plugin_install

    return plan_assetforge_plugin_install(project_path, source_plugin_dir)


def install(project_path, source_plugin_dir=None, enable_in_project=True, dry_run=False):
    _ensure_project_root()
    from asset_forge.unreal.plugin_installer import install_assetforge_plugin

    return install_assetforge_plugin(project_path, source_plugin_dir, enable_in_project, dry_run)


def _write_report(path, report):
    if not path:
        return
    directory = os.path.dirname(os.path.abspath(path))
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def main(argv=None):
    _configure_stdout()
    _ensure_project_root()
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        _write_text(sys.stdout, usage_text() + "\n")
        return 0

    args = [item for item in argv if item not in ("--dry-run", "--no-enable")]
    if not args:
        _write_text(sys.stderr, usage_text() + "\n")
        return 2

    report_path = args[1] if len(args) > 1 else None
    report = install(
        args[0],
        enable_in_project="--no-enable" not in argv,
        dry_run="--dry-run" in argv,
    )
    _write_report(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("status") in ("success", "skipped") else 2


if __name__ == "__main__":
    sys.exit(main())
