"""Unreal Python entry point for importing one Asset Forge manifest."""

from __future__ import absolute_import

import os
import json
import sys


def _reload_asset_forge_modules():
    """UE keeps Python alive between runs, so discard stale repo modules."""
    for name in list(sys.modules):
        if name == "asset_forge" or name.startswith("asset_forge."):
            del sys.modules[name]


def _ensure_project_root():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    _reload_asset_forge_modules()
    return project_root


def _print_json(report):
    from asset_forge.shared.report_schema import normalize_report_value

    report = normalize_report_value(report)
    data = json.dumps(report, ensure_ascii=False, indent=2)
    _write_text(sys.stdout, data + "\n")


def _write_text(stream, text):
    if hasattr(stream, "buffer"):
        stream.buffer.write(text.encode("utf-8"))
    else:
        stream.write(text)


def _extract_import_options(argv):
    cleaned = []
    import_options = {}
    index = 0
    while index < len(argv):
        item = argv[index]
        if item == "--import-options-json":
            if index + 1 >= len(argv):
                raise RuntimeError("Usage: --import-options-json <json_object>")
            raw_json = argv[index + 1]
            try:
                parsed = json.loads(raw_json)
            except Exception as exc:
                raise RuntimeError("--import-options-json 不是有效 JSON：{0}".format(exc))
            if not isinstance(parsed, dict):
                raise RuntimeError("--import-options-json 必须是 JSON object，例如 {\"combine_meshes\": false}")
            import_options.update(parsed)
            index += 2
            continue
        cleaned.append(item)
        index += 1
    return cleaned, import_options


def import_manifest(manifest_path, log_path=None, dry_run=False, auto_bootstrap_material_assets=False):
    _ensure_project_root()
    from asset_forge.unreal.pipeline import UnrealStaticMeshImportPipeline, dry_run_manifest

    if dry_run:
        return dry_run_manifest(manifest_path, log_path)
    pipeline = UnrealStaticMeshImportPipeline(auto_bootstrap_material_assets=auto_bootstrap_material_assets)
    return pipeline.import_from_manifest(manifest_path, log_path)


def import_latest_manifest(export_root, log_path=None, dry_run=False):
    _ensure_project_root()
    from asset_forge.unreal.pipeline import import_latest_manifest as run_latest

    return run_latest(export_root, log_path, dry_run)


def import_asset_forge_package(package_dir, dry_run=False, report_path=None, auto_bootstrap_material_assets=False, import_options=None):
    _ensure_project_root()
    from asset_forge.unreal.manifest_finder import find_latest_manifest
    from asset_forge.unreal.pipeline import UnrealStaticMeshImportPipeline

    manifest_path = find_latest_manifest(package_dir)
    if not manifest_path:
        raise RuntimeError("资产包内未找到 Asset Forge manifest：{0}".format(package_dir))
    pipeline = UnrealStaticMeshImportPipeline(auto_bootstrap_material_assets=auto_bootstrap_material_assets, import_options=import_options)
    if dry_run:
        return pipeline.dry_run_manifest(manifest_path, report_path)
    return pipeline.import_from_manifest(manifest_path, report_path)


def validate_asset_forge_package(package_dir, report_path=None, strict=False, block_warnings=None, require_import=False, command_args=None):
    _ensure_project_root()
    from asset_forge.unreal.package_acceptance import validate_asset_forge_package as run_validation

    return run_validation(package_dir, report_path, strict, block_warnings, require_import, command_args)


def validate_all_asset_forge_packages(export_root, report_path=None, strict=False, block_warnings=None, require_import=False, command_args=None):
    _ensure_project_root()
    from asset_forge.unreal.package_acceptance import validate_all_asset_forge_packages as run_validation

    return run_validation(export_root, report_path, strict, block_warnings, require_import, command_args)


def run_asset_forge_package_acceptance(
    package_dir,
    report_path=None,
    run_import=False,
    auto_bootstrap_material_assets=False,
    strict=False,
    block_warnings=None,
    require_import=False,
    import_options=None,
    command_args=None,
):
    _ensure_project_root()
    from asset_forge.unreal.acceptance_runner import run_asset_forge_package_acceptance as run_flow

    return run_flow(package_dir, report_path, run_import, auto_bootstrap_material_assets, strict, block_warnings, require_import, import_options, command_args)


def run_all_asset_forge_package_acceptance(
    export_root,
    report_path=None,
    run_import=False,
    auto_bootstrap_material_assets=False,
    strict=False,
    block_warnings=None,
    require_import=False,
    import_options=None,
    command_args=None,
):
    _ensure_project_root()
    from asset_forge.unreal.acceptance_runner import run_all_asset_forge_package_acceptance as run_flow

    return run_flow(export_root, report_path, run_import, auto_bootstrap_material_assets, strict, block_warnings, require_import, import_options, command_args)


def run_asset_forge_doctor(repo_root=None, report_path=None, strict=False, block_warnings=None):
    _ensure_project_root()
    from asset_forge.unreal.doctor import run_asset_forge_doctor as run_doctor

    return run_doctor(repo_root, report_path, strict, block_warnings, sys.argv[1:])


def run_interface_contract_check(manifest_or_package_path, report_path=None):
    _ensure_project_root()
    from asset_forge.shared.interface_contract import validate_package_contract

    return validate_package_contract(manifest_or_package_path, report_path)


def run_stage_validation_bundle(package_dir, report_path=None, command_args=None):
    _ensure_project_root()
    from asset_forge.unreal.stage_validation_bundle import collect_stage_validation_bundle

    return collect_stage_validation_bundle(package_dir, report_path, command_args or [])


def run_offline_evidence_bundle(output_root=None, report_path=None, command_args=None):
    _ensure_project_root()
    from asset_forge.unreal.stage_validation_bundle import collect_offline_evidence_bundle

    return collect_offline_evidence_bundle(output_root, report_path, command_args or [])


def run_capability_matrix():
    _ensure_project_root()
    from asset_forge.unreal.capability_matrix import create_capability_matrix

    return create_capability_matrix()


def run_ue_validation_checklist(package_dir=""):
    _ensure_project_root()
    from asset_forge.unreal.ue_validation_checklist import create_ue_validation_checklist

    return create_ue_validation_checklist(package_dir)


def run_north_star_readiness(evidence_path=None):
    _ensure_project_root()
    from asset_forge.unreal.capability_matrix import create_capability_matrix
    from asset_forge.unreal.north_star_readiness import create_north_star_readiness
    from asset_forge.shared.report_artifacts import default_report_path
    from asset_forge.shared.report_schema import read_report

    evidence_bundle = _read_readiness_evidence(evidence_path, default_report_path, read_report)
    capability_matrix = {}
    if evidence_bundle:
        capability_matrix = evidence_bundle.get("stages", {}).get("capability_matrix", {})
    if not capability_matrix:
        capability_matrix = create_capability_matrix()

    return create_north_star_readiness(evidence_bundle, capability_matrix)


def run_portfolio_readiness(evidence_path=None):
    _ensure_project_root()
    from asset_forge.unreal.capability_matrix import create_capability_matrix
    from asset_forge.unreal.north_star_readiness import create_north_star_readiness
    from asset_forge.unreal.portfolio_readiness import create_portfolio_readiness
    from asset_forge.shared.report_artifacts import default_report_path
    from asset_forge.shared.report_schema import read_report

    evidence_bundle = _read_readiness_evidence(evidence_path, default_report_path, read_report)
    capability_matrix = {}
    if evidence_bundle:
        capability_matrix = evidence_bundle.get("stages", {}).get("capability_matrix", {})
    if not capability_matrix:
        capability_matrix = create_capability_matrix()
    north_star = create_north_star_readiness(evidence_bundle, capability_matrix)
    return create_portfolio_readiness(north_star, capability_matrix, evidence_bundle)


def run_portfolio_demo_pack(evidence_path=None, report_path=None, command_args=None):
    _ensure_project_root()
    from asset_forge.unreal.portfolio_demo_pack import create_portfolio_demo_pack
    from asset_forge.shared.report_artifacts import attach_report_artifact_metadata
    from asset_forge.shared.report_schema import write_report

    report = create_portfolio_demo_pack(evidence_path, None, command_args or [])
    if not report.get("evidence_stage"):
        report = _with_portfolio_cli_warning(
            report,
            "missing_offline_evidence_bundle",
            "缺少 portfolio demo pack 的上游离线证据包。",
            "先运行 --offline-evidence-bundle，再把生成的 report path 传给 --portfolio-demo-pack。",
        )
    if report_path:
        attach_report_artifact_metadata(report, report_path, command_args or ["--portfolio-demo-pack"])
        write_report(report_path, report)
    return report


def run_portfolio_evidence_manifest(demo_pack_path=None, evidence_root=None, report_path=None, command_args=None):
    _ensure_project_root()
    from asset_forge.shared.portfolio_evidence_manifest import create_portfolio_evidence_manifest
    from asset_forge.shared.report_artifacts import attach_report_artifact_metadata, default_report_path
    from asset_forge.shared.report_schema import read_report, write_report

    demo_pack = {}
    if demo_pack_path and os.path.exists(demo_pack_path):
        demo_pack = read_report(demo_pack_path)
    elif not demo_pack_path:
        candidate = default_report_path(os.getcwd(), "portfolio_demo_pack")
        if os.path.exists(candidate):
            demo_pack = read_report(candidate)
    report = create_portfolio_evidence_manifest(demo_pack, evidence_root)
    if not demo_pack.get("steps"):
        report = _with_portfolio_cli_warning(
            report,
            "missing_portfolio_demo_pack",
            "缺少截图清单的上游 portfolio demo pack。",
            "按顺序运行 --offline-evidence-bundle -> --portfolio-demo-pack -> --portfolio-evidence-manifest。",
        )
    if report_path:
        attach_report_artifact_metadata(report, report_path, command_args or ["--portfolio-evidence-manifest"])
        write_report(report_path, report)
    return report


def _with_portfolio_cli_warning(report, warning_id, message, next_action):
    from asset_forge.shared.report_schema import attach_acceptance_summary, create_acceptance_summary

    summary = report.get("summary", {}) if isinstance(report.get("summary", {}), dict) else {}
    warnings = list(summary.get("warnings", report.get("warnings", [])) or [])
    if not any(item.get("id") == warning_id for item in warnings if isinstance(item, dict)):
        warnings.insert(0, {"source": "portfolio_cli", "id": warning_id, "message": message})
    errors = list(summary.get("errors", report.get("errors", [])) or [])
    new_summary = create_acceptance_summary("warning", warnings, errors, next_action)
    report["status"] = "warning"
    report["summary"] = new_summary
    return attach_acceptance_summary(report, new_summary)


def _read_readiness_evidence(evidence_path, default_report_path_fn, read_report_fn):
    candidates = []
    if evidence_path:
        if os.path.isdir(evidence_path):
            candidates.append(default_report_path_fn(evidence_path, "offline_evidence_bundle"))
            candidates.append(default_report_path_fn(evidence_path, "stage_validation_bundle"))
        else:
            candidates.append(evidence_path)
    else:
        cwd = os.getcwd()
        candidates.append(default_report_path_fn(cwd, "offline_evidence_bundle"))
        candidates.append(default_report_path_fn(cwd, "stage_validation_bundle"))

    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            try:
                return read_report_fn(candidate)
            except Exception:
                continue
    return {}


def usage_text():
    return "\n".join(
        [
            "Usage:",
            "  unreal_import_manifest.py <manifest_path> [log_path] [--dry-run] [--auto-materials]",
            "  unreal_import_manifest.py --latest <export_root> [log_path] [--dry-run]",
            "  unreal_import_manifest.py --all <export_root> [report_path] [--dry-run]",
            "  unreal_import_manifest.py --package <package_dir> [report_path] [--dry-run] [--auto-materials]",
            "  unreal_import_manifest.py --validate-package <package_dir> [report_path] [--strict] [--block-warnings] [--require-import]",
            "  unreal_import_manifest.py --validate-all-packages <export_root> [report_path] [--strict] [--block-warnings] [--require-import]",
            "  unreal_import_manifest.py --accept-flow <package_dir> [report_path] [--run-import] [--auto-materials] [--strict] [--block-warnings] [--require-import]",
            "  unreal_import_manifest.py --accept-flow-all <export_root> [report_path] [--run-import] [--auto-materials] [--strict] [--block-warnings] [--require-import]",
            "  unreal_import_manifest.py --contract-check <manifest_or_package_dir> [report_path]",
            "  unreal_import_manifest.py --doctor [repo_root] [report_path] [--strict] [--block-warnings]",
            "  unreal_import_manifest.py --pretest-check [repo_root] [report_path] [--strict] [--block-warnings]",
            "  unreal_import_manifest.py --stage-bundle <package_dir> [report_path]",
            "  unreal_import_manifest.py --offline-evidence-bundle [output_root] [report_path]",
            "  unreal_import_manifest.py --capability-matrix",
            "  unreal_import_manifest.py --ue-checklist [package_dir]",
            "  unreal_import_manifest.py --north-star-readiness [offline_evidence_report]",
            "  unreal_import_manifest.py --portfolio-readiness [offline_evidence_report]",
            "  unreal_import_manifest.py --portfolio-demo-pack [offline_evidence_report] [report_path]",
            "  unreal_import_manifest.py --portfolio-evidence-manifest [portfolio_demo_pack_report] [evidence_root] [report_path]",
            "  unreal_import_manifest.py --ensure-gate-widget",
            "  unreal_import_manifest.py --read-gate-widget-tree",
            "  unreal_import_manifest.py --gate-ui",
            "",
            "Import options / 导入选项:",
            "  --import-options-json '{\"combine_meshes\":false,\"import_mesh_lods\":true}' 可用于 --package、--accept-flow、--accept-flow-all。",
            "",
            "Portfolio sprint chain / 作品集冲刺链路:",
            "  --offline-evidence-bundle -> --portfolio-demo-pack -> --portfolio-evidence-manifest",
            "  --portfolio-demo-pack 需要第一步生成的 offline evidence bundle report。",
            "  --portfolio-evidence-manifest 需要第二步生成的 portfolio demo pack report。",
            "",
            "Next action:",
            "  先用 --offline-evidence-bundle 或 --package --dry-run 生成离线证据；进入真实 UE 导入时再加 --run-import --auto-materials。",
        ]
    )


def import_all_manifests(export_root, report_path=None, dry_run=False):
    _ensure_project_root()
    from asset_forge.unreal.pipeline import import_all_manifests as run_all

    return run_all(export_root, report_path, dry_run)


def get_editor_widget_action_plan():
    _ensure_project_root()
    from asset_forge.unreal.editor_widget_actions import get_action_plan

    return get_action_plan()


def get_editor_widget_package_history(export_root="", latest_maya_log_path=None, latest_unreal_log_path=None, limit=20):
    _ensure_project_root()
    from asset_forge.unreal.editor_widget_actions import refresh_package_history

    return refresh_package_history(export_root, latest_maya_log_path, latest_unreal_log_path, limit)


def get_editor_widget_gate_panel_state(package_dir="", export_root="", latest_maya_log_path=None, latest_unreal_log_path=None, report_path=None):
    _ensure_project_root()
    from asset_forge.unreal.editor_widget_actions import build_editor_widget_gate_panel_state

    return build_editor_widget_gate_panel_state(package_dir, export_root, latest_maya_log_path, latest_unreal_log_path, report_path)


def ensure_editor_widget_asset():
    _ensure_project_root()
    from asset_forge.unreal.editor_widget_actions import ensure_widget_asset

    return ensure_widget_asset()


def read_editor_widget_tree():
    _ensure_project_root()
    from asset_forge.unreal.editor_widget_actions import read_widget_tree

    return read_widget_tree()


def preview_editor_widget_package_gate(package_dir, report_path=None):
    _ensure_project_root()
    from asset_forge.unreal.editor_widget_actions import preview_selected_package_gate

    return preview_selected_package_gate(package_dir, report_path)


def get_editor_widget_launch_plan():
    _ensure_project_root()
    from asset_forge.unreal.editor_widget_launcher import get_widget_launch_plan

    return get_widget_launch_plan()


def launch_asset_forge_widget():
    _ensure_project_root()
    from asset_forge.unreal.editor_widget_launcher import launch_asset_forge_widget as run_launch

    return run_launch()


def main(argv=None):
    _ensure_project_root()
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        _write_text(sys.stdout, usage_text() + "\n")
        return 0
    original_argv = list(argv)
    try:
        argv, import_options = _extract_import_options(argv)
    except Exception as exc:
        _print_cli_error(str(exc), "检查 --import-options-json 后面的 JSON object。")
        return 2
    flags = {
        "--dry-run",
        "--latest",
        "--all",
        "--package",
        "--auto-materials",
        "--validate-package",
        "--validate-all-packages",
        "--accept-flow",
        "--accept-flow-all",
        "--run-import",
        "--strict",
        "--block-warnings",
        "--require-import",
        "--doctor",
        "--pretest-check",
        "--contract-check",
        "--stage-bundle",
        "--offline-evidence-bundle",
        "--capability-matrix",
        "--ue-checklist",
        "--north-star-readiness",
        "--portfolio-readiness",
        "--portfolio-demo-pack",
        "--portfolio-evidence-manifest",
        "--ensure-gate-widget",
        "--read-gate-widget-tree",
        "--gate-ui",
    }
    unknown_flags = [item for item in argv if item.startswith("-") and item not in flags and item not in ("--help", "-h")]
    if unknown_flags:
        _print_cli_error(
            "未知参数：{0}".format(", ".join(unknown_flags)),
            "检查命令拼写，或运行 --help 查看当前支持的模式。",
        )
        return 2
    args = [item for item in argv if item not in flags]
    dry_run = "--dry-run" in argv
    latest = "--latest" in argv
    import_all = "--all" in argv
    package = "--package" in argv
    auto_materials = "--auto-materials" in argv
    validate_package = "--validate-package" in argv
    validate_all_packages = "--validate-all-packages" in argv
    accept_flow = "--accept-flow" in argv
    accept_flow_all = "--accept-flow-all" in argv
    run_import = "--run-import" in argv
    strict = "--strict" in argv
    block_warnings = True if "--block-warnings" in argv else None
    require_import = "--require-import" in argv
    doctor = "--doctor" in argv
    pretest_check = "--pretest-check" in argv
    contract_check = "--contract-check" in argv
    stage_bundle = "--stage-bundle" in argv
    offline_evidence_bundle = "--offline-evidence-bundle" in argv
    capability_matrix = "--capability-matrix" in argv
    ue_checklist = "--ue-checklist" in argv
    north_star_readiness = "--north-star-readiness" in argv
    portfolio_readiness = "--portfolio-readiness" in argv
    portfolio_demo_pack = "--portfolio-demo-pack" in argv
    portfolio_evidence_manifest = "--portfolio-evidence-manifest" in argv
    ensure_gate_widget = "--ensure-gate-widget" in argv
    read_gate_widget_tree = "--read-gate-widget-tree" in argv
    gate_ui = "--gate-ui" in argv
    mode_flags = _mode_flags(original_argv)
    _log_cli("unreal_cli_start", "started", original_argv, mode_flags, args=args)
    try:
        if ensure_gate_widget:
            report = ensure_editor_widget_asset()
        elif read_gate_widget_tree:
            report = read_editor_widget_tree()
        elif gate_ui:
            report = launch_asset_forge_widget()
        elif capability_matrix:
            report = run_capability_matrix()
        elif ue_checklist:
            report = run_ue_validation_checklist(args[0] if len(args) > 0 else "")
        elif north_star_readiness:
            report = run_north_star_readiness(args[0] if len(args) > 0 else None)
        elif portfolio_readiness:
            report = run_portfolio_readiness(args[0] if len(args) > 0 else None)
        elif portfolio_demo_pack:
            report = run_portfolio_demo_pack(args[0] if len(args) > 0 else None, args[1] if len(args) > 1 else None, argv)
        elif portfolio_evidence_manifest:
            report = run_portfolio_evidence_manifest(
                args[0] if len(args) > 0 else None,
                args[1] if len(args) > 1 else None,
                args[2] if len(args) > 2 else None,
                argv,
            )
        elif contract_check:
            if len(args) < 1:
                raise RuntimeError("Usage: unreal_import_manifest.py --contract-check <manifest_or_package_dir> [report_path]")
            report = run_interface_contract_check(args[0], args[1] if len(args) > 1 else None)
        elif doctor or pretest_check:
            report = run_asset_forge_doctor(args[0] if len(args) > 0 else _ensure_project_root(), args[1] if len(args) > 1 else None, strict, block_warnings)
        elif stage_bundle:
            if len(args) < 1:
                raise RuntimeError("Usage: unreal_import_manifest.py --stage-bundle <package_dir> [report_path]")
            report = run_stage_validation_bundle(args[0], args[1] if len(args) > 1 else None, argv)
        elif offline_evidence_bundle:
            report = run_offline_evidence_bundle(args[0] if len(args) > 0 else None, args[1] if len(args) > 1 else None, argv)
        else:
            if len(args) < 1:
                raise RuntimeError("Usage: unreal_import_manifest.py <manifest_path_or_export_root> [log_path] [--dry-run] [--latest] [--all] [--package] [--accept-flow] [--accept-flow-all] [--run-import]")
            if accept_flow_all:
                report = run_all_asset_forge_package_acceptance(args[0], args[1] if len(args) > 1 else None, run_import, auto_materials, strict, block_warnings, require_import, import_options, original_argv)
            elif accept_flow:
                report = run_asset_forge_package_acceptance(args[0], args[1] if len(args) > 1 else None, run_import, auto_materials, strict, block_warnings, require_import, import_options, original_argv)
            elif validate_all_packages:
                report = validate_all_asset_forge_packages(args[0], args[1] if len(args) > 1 else None, strict, block_warnings, require_import, argv)
            elif validate_package:
                report = validate_asset_forge_package(args[0], args[1] if len(args) > 1 else None, strict, block_warnings, require_import, argv)
            elif import_all:
                report = import_all_manifests(args[0], args[1] if len(args) > 1 else None, dry_run)
            elif package:
                report = import_asset_forge_package(args[0], dry_run, args[1] if len(args) > 1 else None, auto_materials, import_options)
            elif latest:
                report = import_latest_manifest(args[0], args[1] if len(args) > 1 else None, dry_run)
            else:
                report = import_manifest(args[0], args[1] if len(args) > 1 else None, dry_run, auto_materials)
    except Exception as exc:
        _log_cli("unreal_cli_failed", "error", original_argv, mode_flags, args=args, errors=[str(exc)])
        _print_cli_error(str(exc), _next_action_for_cli_error(str(exc)))
        return 2
    _print_json(report)
    _print_cli_report_guidance(report, mode_flags)
    _log_report_operation(report, original_argv, mode_flags, args)
    exit_code = 2 if (strict or block_warnings or require_import) and not report.get("gate_passed", True) else 0
    _log_cli(
        "unreal_cli_success",
        "success" if exit_code == 0 else "gate_failed",
        original_argv,
        mode_flags,
        args=args,
        outputs=_report_outputs(report),
        report_path=_report_path(report, args),
    )
    return exit_code


def _print_cli_error(message, next_action=""):
    text = "Error: {0}\n".format(message)
    if next_action:
        text += "Next action: {0}\n".format(next_action)
    text += "\n"
    text += usage_text() + "\n"
    _write_text(sys.stderr, text)


def _next_action_for_cli_error(message):
    if "Usage:" in message:
        return "按 usage 补齐必需路径参数后重新执行。"
    if "manifest" in message:
        return "确认传入的是 manifest 文件、资产包目录，或包含 manifest 的导出根目录。"
    return "检查路径和参数后重新执行；需要模式说明时运行 --help。"


def _print_cli_report_guidance(report, mode_flags):
    if not _should_print_report_guidance(mode_flags) or not isinstance(report, dict):
        return
    guidance = _cli_report_guidance(report)
    if not guidance:
        return

    lines = [
        "",
        "Asset Forge guidance:",
        "  decision_label: {0}".format(guidance.get("decision_label", "")),
        "  decision: {0}".format(guidance.get("decision", "")),
        "  can_import: {0}".format("true" if guidance.get("can_import") else "false"),
    ]
    if guidance.get("next_action"):
        lines.append("  next_action: {0}".format(guidance.get("next_action", "")))
    if guidance.get("why"):
        lines.append("  why: {0}".format("; ".join(guidance.get("why", [])[:3])))
    if guidance.get("next_steps"):
        lines.append("  next_steps:")
        for step in guidance.get("next_steps", [])[:3]:
            lines.append("    - {0}".format(step))
    _write_text(sys.stderr, "\n".join(lines) + "\n")


def _should_print_report_guidance(mode_flags):
    return bool(
        mode_flags.get("accept_flow")
        or mode_flags.get("accept_flow_all")
        or mode_flags.get("dry_run")
        or _is_import_mode(mode_flags)
    )


def _cli_report_guidance(report):
    try:
        from asset_forge.shared.report_schema import normalize_report_value

        report = normalize_report_value(report)
    except Exception:
        pass

    summary = report.get("summary", {}) if isinstance(report.get("summary", {}), dict) else {}
    user_guidance = report.get("user_guidance", {}) if isinstance(report.get("user_guidance", {}), dict) else {}
    source = user_guidance or summary or report
    next_action = (
        report.get("next_action", "")
        or summary.get("next_action", "")
        or _first_next_step_detail(user_guidance.get("next_steps", []))
    )
    guidance = {
        "decision_label": source.get("decision_label", report.get("decision_label", "")),
        "decision": source.get("decision", report.get("decision", "")),
        "can_import": source.get("can_import", report.get("can_import", summary.get("can_accept", False))),
        "next_action": next_action,
        "why": [_guidance_text(item) for item in source.get("why", [])],
        "next_steps": [_guidance_step_text(item) for item in source.get("next_steps", [])],
    }
    guidance["why"] = [item for item in guidance["why"] if item]
    guidance["next_steps"] = [item for item in guidance["next_steps"] if item]
    if not any([guidance["decision_label"], guidance["decision"], guidance["next_action"], guidance["why"], guidance["next_steps"]]):
        return {}
    return guidance


def _first_next_step_detail(steps):
    for step in steps or []:
        if isinstance(step, dict) and step.get("detail"):
            return step.get("detail", "")
        if step:
            return str(step)
    return ""


def _guidance_text(item):
    if isinstance(item, dict):
        return item.get("message") or item.get("detail") or item.get("label") or ""
    return str(item)


def _guidance_step_text(item):
    if isinstance(item, dict):
        label = item.get("label", "")
        detail = item.get("detail", "")
        if label and detail:
            return "{0}: {1}".format(label, detail)
        return label or detail
    return str(item)


def _mode_flags(argv):
    names = [
        "--dry-run",
        "--latest",
        "--all",
        "--package",
        "--auto-materials",
        "--validate-package",
        "--validate-all-packages",
        "--accept-flow",
        "--accept-flow-all",
        "--run-import",
        "--strict",
        "--block-warnings",
        "--require-import",
        "--doctor",
        "--pretest-check",
        "--contract-check",
        "--stage-bundle",
        "--offline-evidence-bundle",
        "--capability-matrix",
        "--ue-checklist",
        "--north-star-readiness",
        "--portfolio-readiness",
        "--portfolio-demo-pack",
        "--portfolio-evidence-manifest",
        "--ensure-gate-widget",
        "--read-gate-widget-tree",
        "--gate-ui",
        "--import-options-json",
    ]
    return dict((name.lstrip("-").replace("-", "_"), name in argv) for name in names)


def _log_cli(operation, status, argv, mode_flags, args=None, outputs=None, errors=None, warnings=None, report_path=""):
    try:
        from asset_forge.unreal.operation_logger import UnrealOperationLogger

        return UnrealOperationLogger().log(
            operation,
            status,
            inputs={"argv": list(argv), "args": list(args or []), "mode_flags": dict(mode_flags or {})},
            outputs=outputs or {},
            errors=errors or [],
            warnings=warnings or [],
            report_path=report_path,
        )
    except Exception:
        return {}


def _log_report_operation(report, argv, mode_flags, args):
    if mode_flags.get("accept_flow") or mode_flags.get("accept_flow_all"):
        _log_cli("unreal_accept_flow", report.get("status", ""), argv, mode_flags, args=args, outputs=_accept_flow_outputs(report), report_path=_report_path(report, args))
    elif mode_flags.get("dry_run"):
        _log_cli("unreal_dry_run", report.get("status", ""), argv, mode_flags, args=args, outputs=_dry_run_outputs(report, args), report_path=_report_path(report, args))
    elif _is_import_mode(mode_flags):
        _log_cli("unreal_import", report.get("status", ""), argv, mode_flags, args=args, outputs=_import_outputs(report, args), errors=report.get("errors", []) or report.get("issues", []), warnings=report.get("warnings", []), report_path=_report_path(report, args))
        _log_import_substeps(report, argv, mode_flags, args)


def _log_import_substeps(report, argv, mode_flags, args):
    material_bootstrap = report.get("material_asset_bootstrap_report", {})
    if material_bootstrap:
        _log_cli(
            "unreal_material_bootstrap",
            material_bootstrap.get("status", "skipped"),
            argv,
            mode_flags,
            args=args,
            outputs={
                "created_count": len(material_bootstrap.get("created_assets", [])),
                "updated_count": len(material_bootstrap.get("updated_assets", [])),
                "existing_count": len(material_bootstrap.get("existing_assets", [])),
                "material_network_status": material_bootstrap.get("material_network_status", ""),
            },
            warnings=material_bootstrap.get("issues", []),
            report_path=_report_path(report, args),
        )

    material_plan = report.get("material_binding_plan", {})
    if material_plan or report.get("created_material_instances") is not None:
        _log_cli(
            "unreal_material_instance_creation",
            "warning" if report.get("material_instance_issues") else "success",
            argv,
            mode_flags,
            args=args,
            outputs={
                "planned_count": material_plan.get("count", 0),
                "created_count": len(report.get("created_material_instances", [])),
                "materials": [
                    {
                        "maya_material_name": item.get("maya_material_name", item.get("source_material", "")),
                        "material_instance_name": item.get("material_instance_name", ""),
                        "material_instance_path": item.get("material_instance_path", item.get("target_asset_path", "")),
                        "parent_material_path": item.get("parent_material_path", item.get("parent_material", "")),
                    }
                    for item in material_plan.get("materials", [])
                ],
            },
            warnings=report.get("material_instance_issues", []),
            report_path=_report_path(report, args),
        )

    post_validation = report.get("post_import_validation", {})
    if post_validation:
        _log_cli(
            "unreal_post_import_validation",
            post_validation.get("status", "skipped"),
            argv,
            mode_flags,
            args=args,
            outputs={
                "can_accept": post_validation.get("can_accept", None),
                "check_count": len(post_validation.get("checks", [])),
            },
            warnings=[item for item in post_validation.get("checks", []) if item.get("status") == "warning"],
            errors=[item for item in post_validation.get("checks", []) if item.get("status") == "error"],
            report_path=_report_path(report, args),
        )


def _is_import_mode(mode_flags):
    return bool(mode_flags.get("latest") or mode_flags.get("all") or mode_flags.get("package") or not any([
        mode_flags.get("validate_package"),
        mode_flags.get("validate_all_packages"),
        mode_flags.get("doctor"),
        mode_flags.get("pretest_check"),
        mode_flags.get("contract_check"),
        mode_flags.get("stage_bundle"),
        mode_flags.get("offline_evidence_bundle"),
        mode_flags.get("capability_matrix"),
        mode_flags.get("ue_checklist"),
        mode_flags.get("north_star_readiness"),
        mode_flags.get("portfolio_readiness"),
        mode_flags.get("portfolio_demo_pack"),
        mode_flags.get("portfolio_evidence_manifest"),
        mode_flags.get("ensure_gate_widget"),
        mode_flags.get("read_gate_widget_tree"),
    ]))


def _report_path(report, args):
    return report.get("report_path", "") or (args[1] if len(args or []) > 1 else "")


def _report_outputs(report):
    return {
        "stage": report.get("stage", ""),
        "status": report.get("status", ""),
        "asset_name": report.get("asset_name", ""),
        "package_dir": report.get("package_dir", ""),
        "manifest_path": report.get("manifest_path", ""),
        "report_path": report.get("report_path", ""),
        "gate_passed": report.get("gate_passed", None),
    }


def _dry_run_outputs(report, args):
    return {
        "manifest_path": report.get("manifest_path", args[0] if args else ""),
        "status": report.get("status", ""),
        "can_accept": report.get("can_accept", report.get("summary", {}).get("can_accept", None)),
        "can_import": report.get("status", "") != "failed",
        "report_path": _report_path(report, args),
    }


def _import_outputs(report, args):
    return {
        "asset_name": report.get("asset_name", ""),
        "manifest_path": report.get("manifest_path", args[0] if args else ""),
        "target_path": report.get("target_path", ""),
        "imported_assets_count": len(report.get("imported_assets", [])),
        "imported_textures_count": len(report.get("imported_textures", [])),
        "created_material_instances_count": len(report.get("created_material_instances", [])),
        "status": report.get("status", ""),
        "report_path": _report_path(report, args),
    }


def _accept_flow_outputs(report):
    return {
        "package_dir": report.get("package_dir", ""),
        "run_import": report.get("run_import", False),
        "auto_materials": report.get("auto_bootstrap_material_assets", False),
        "status": report.get("status", ""),
        "gate_passed": report.get("gate_passed", None),
        "report_path": report.get("report_path", ""),
    }


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
