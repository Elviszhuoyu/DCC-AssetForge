"""Launch Unreal commandlets with Asset Forge-safe defaults."""

from __future__ import absolute_import

import json
import os
import subprocess


DEFAULT_DDC_MODE = "InstalledNoZenLocalFallback"


def run_accept_flow_commandlet(
    unreal_editor_cmd,
    uproject_path,
    package_dir,
    report_path,
    target_path="",
    log_path="",
    repo_root=None,
    ddc_mode=DEFAULT_DDC_MODE,
    null_rhi=True,
    runner=None,
):
    repo_root = repo_root or _repo_root()
    script_path = os.path.join(repo_root, "scripts", "ue_cleanup_accept_flow.py")
    log_path = log_path or _default_log_path(report_path)
    command = build_accept_flow_command(
        unreal_editor_cmd,
        uproject_path,
        script_path,
        package_dir,
        report_path,
        target_path,
        ddc_mode=ddc_mode,
        null_rhi=null_rhi,
    )
    completed = _run_process(command, runner=runner)
    _write_commandlet_log(log_path, command, completed)
    report = _read_report(report_path)
    summary = summarize_commandlet_result(completed.returncode, report, log_path, command)
    return summary


def run_accept_flow_with_material_evidence_commandlet(
    unreal_editor_cmd,
    uproject_path,
    package_dir,
    report_path,
    target_path="",
    log_path="",
    material_report_path="",
    material_log_path="",
    repo_root=None,
    ddc_mode=DEFAULT_DDC_MODE,
    null_rhi=True,
    runner=None,
):
    accept_summary = run_accept_flow_commandlet(
        unreal_editor_cmd,
        uproject_path,
        package_dir,
        report_path,
        target_path=target_path,
        log_path=log_path,
        repo_root=repo_root,
        ddc_mode=ddc_mode,
        null_rhi=null_rhi,
        runner=runner,
    )
    if accept_summary.get("status") != "success":
        accept_summary.update(
            {
                "stage": "ue_accept_flow_with_material_evidence_commandlet",
                "material_status": "skipped",
                "material_skip_reason": "accept_flow_failed",
            }
        )
        return accept_summary

    material_report_path = material_report_path or _default_material_report_path(report_path)
    material_summary = run_material_evidence_commandlet(
        unreal_editor_cmd,
        uproject_path,
        report_path,
        material_report_path,
        log_path=material_log_path,
        repo_root=repo_root,
        ddc_mode=ddc_mode,
        null_rhi=null_rhi,
        cold_start_readback=True,
        runner=runner,
    )
    combined = dict(accept_summary)
    combined.update(
        {
            "stage": "ue_accept_flow_with_material_evidence_commandlet",
            "status": "success" if material_summary.get("status") == "success" else "error",
            "accept_flow_status": accept_summary.get("status", ""),
            "material_status": material_summary.get("status", ""),
            "material_report_status": material_summary.get("report_status", ""),
            "material_graph_evidence_status": material_summary.get("material_graph_evidence_status", ""),
            "real_graph_status": material_summary.get("real_graph_status", ""),
            "comment_blocks_status": material_summary.get("comment_blocks_status", ""),
            "cold_start_readback_status": material_summary.get("cold_start_readback_status", ""),
            "material_report_path": material_summary.get("report_path", ""),
            "material_log_path": material_summary.get("log_path", ""),
            "material_process_exit_code": material_summary.get("process_exit_code"),
            "material_process_exit_code_trusted": material_summary.get("process_exit_code_trusted", False),
            "ta_visual_review_status": material_summary.get("ta_visual_review_status", ""),
            "screenshot_evidence_status": material_summary.get("screenshot_evidence_status", ""),
            "material_next_action": material_summary.get("next_action", ""),
        }
    )
    return combined


def run_material_evidence_commandlet(
    unreal_editor_cmd,
    uproject_path,
    import_report_path,
    material_report_path,
    log_path="",
    repo_root=None,
    ddc_mode=DEFAULT_DDC_MODE,
    null_rhi=True,
    cold_start_readback=True,
    runner=None,
):
    repo_root = repo_root or _repo_root()
    script_path = os.path.join(repo_root, "scripts", "unreal_collect_material_evidence.py")
    log_path = log_path or _default_log_path(material_report_path)
    command = build_material_evidence_command(
        unreal_editor_cmd,
        uproject_path,
        script_path,
        import_report_path,
        material_report_path,
        cold_start_readback=cold_start_readback,
        ddc_mode=ddc_mode,
        null_rhi=null_rhi,
    )
    completed = _run_process(command, runner=runner)
    _write_commandlet_log(log_path, command, completed)
    report = _read_report(material_report_path)
    summary = summarize_material_evidence_result(completed.returncode, report, log_path, command, cold_start_readback)
    summary["report_path"] = _ue_path(material_report_path)
    return summary


def build_accept_flow_command(
    unreal_editor_cmd,
    uproject_path,
    script_path,
    package_dir,
    report_path,
    target_path="",
    ddc_mode=DEFAULT_DDC_MODE,
    null_rhi=True,
):
    script_args = [
        _ue_path(script_path),
        _ue_path(package_dir),
        _ue_path(report_path),
    ]
    if target_path:
        script_args.append(str(target_path))
    command = [
        str(unreal_editor_cmd),
        _ue_path(uproject_path),
        "-run=pythonscript",
        "-script={0}".format(" ".join(script_args)),
        "-unattended",
        "-nop4",
        "-nosplash",
    ]
    if null_rhi:
        command.append("-NullRHI")
    if ddc_mode:
        command.append("-ddc={0}".format(ddc_mode))
    return command


def build_material_evidence_command(
    unreal_editor_cmd,
    uproject_path,
    script_path,
    import_report_path,
    material_report_path,
    cold_start_readback=True,
    ddc_mode=DEFAULT_DDC_MODE,
    null_rhi=True,
):
    script_args = [
        _ue_path(script_path),
        _ue_path(import_report_path),
        _ue_path(material_report_path),
    ]
    if cold_start_readback:
        script_args.append("--cold-start-readback")
    command = [
        str(unreal_editor_cmd),
        _ue_path(uproject_path),
        "-run=pythonscript",
        "-script={0}".format(" ".join(script_args)),
        "-unattended",
        "-nop4",
        "-nosplash",
    ]
    if null_rhi:
        command.append("-NullRHI")
    if ddc_mode:
        command.append("-ddc={0}".format(ddc_mode))
    return command


def summarize_commandlet_result(process_exit_code, report, log_path, command):
    report = report or {}
    summary = report.get("summary", {}) if isinstance(report.get("summary", {}), dict) else {}
    errors = report.get("errors", summary.get("errors", [])) or []
    gate_passed = bool(report.get("gate_passed"))
    can_accept = bool(report.get("can_accept", summary.get("can_accept", False)))
    import_report = report.get("import", {}) if isinstance(report.get("import", {}), dict) else {}
    post_import = report.get("post_import_validation") or import_report.get("post_import_validation") or {}
    success = bool(gate_passed and can_accept and not errors)
    return {
        "version": "0.1",
        "stage": "ue_accept_flow_commandlet",
        "status": "success" if success else "error",
        "process_exit_code": process_exit_code,
        "process_exit_code_trusted": process_exit_code == 0,
        "report_status": report.get("status", ""),
        "gate_status": report.get("gate_status", ""),
        "gate_passed": gate_passed,
        "can_accept": can_accept,
        "can_import": bool(report.get("can_import", summary.get("can_import", False))),
        "import_status": import_report.get("status", ""),
        "post_import_validation": post_import.get("status") or post_import.get("summary", {}).get("status", ""),
        "error_count": len(errors),
        "warning_count": len(report.get("warnings", summary.get("warnings", [])) or []),
        "report_path": report.get("report_path", ""),
        "log_path": _ue_path(log_path),
        "command": list(command or []),
        "next_action": report.get("next_action", summary.get("next_action", "")),
    }


def summarize_material_evidence_result(process_exit_code, report, log_path, command, cold_start_readback=True):
    report = report or {}
    import_report = report.get("import", report) if isinstance(report.get("import", report), dict) else {}
    graph = import_report.get("material_graph_evidence_report", {}) if isinstance(import_report, dict) else {}
    real_graph = import_report.get("real_ue_material_graph", {}) if isinstance(import_report, dict) else {}
    comment_blocks = _first_comment_blocks(real_graph)
    cold_start_status = comment_blocks.get("cold_start_readback_status", "")
    comment_status = comment_blocks.get("status", "")
    success = bool(
        report
        and process_exit_code == 0
        and real_graph.get("status") == "pass"
        and comment_status == "pass"
        and (not cold_start_readback or cold_start_status == "pass")
    )
    return {
        "version": "0.1",
        "stage": "ue_material_evidence_commandlet",
        "status": "success" if success else "error",
        "process_exit_code": process_exit_code,
        "process_exit_code_trusted": process_exit_code == 0,
        "report_status": report.get("status", ""),
        "import_status": import_report.get("status", ""),
        "material_graph_evidence_status": graph.get("status", ""),
        "real_graph_status": real_graph.get("status", ""),
        "comment_blocks_status": comment_status,
        "cold_start_readback_status": cold_start_status,
        "expected_af_comments": comment_blocks.get("expected_af_comments", 0),
        "linked_graph_comments": comment_blocks.get("linked_graph_comments", 0),
        "visible_graph_comments_with_size": comment_blocks.get("visible_graph_comments_with_size", 0),
        "invalid_graph_comment_dimensions": comment_blocks.get("invalid_graph_comment_dimensions", 0),
        "ta_visual_review_status": import_report.get("ta_visual_review_status", report.get("ta_visual_review_status", "")),
        "screenshot_evidence_status": import_report.get("screenshot_evidence_status", report.get("screenshot_evidence_status", "")),
        "report_path": _ue_path(report.get("report_path") or ""),
        "log_path": _ue_path(log_path),
        "command": list(command or []),
        "next_action": import_report.get("ta_visual_review_next_action", report.get("ta_visual_review_next_action", "")),
    }


def _run_process(command, runner=None):
    active_runner = runner or subprocess.run
    return active_runner(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _write_commandlet_log(log_path, command, completed):
    directory = os.path.dirname(os.path.abspath(log_path))
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    with open(log_path, "w", encoding="utf-8") as stream:
        stream.write("COMMAND:\n")
        stream.write(json.dumps(list(command or []), ensure_ascii=False, indent=2))
        stream.write("\n\nEXIT:\n{0}\n\nSTDOUT:\n".format(completed.returncode))
        stream.write(completed.stdout or "")
        stream.write("\n\nSTDERR:\n")
        stream.write(completed.stderr or "")


def _read_report(report_path):
    if not report_path or not os.path.exists(report_path):
        return {}
    with open(report_path, "r", encoding="utf-8") as stream:
        return json.load(stream)


def _default_log_path(report_path):
    root, _ext = os.path.splitext(report_path)
    return root + ".log"


def _default_material_report_path(report_path):
    root, ext = os.path.splitext(report_path)
    return root + "_material_cold_start" + (ext or ".json")


def _first_comment_blocks(real_graph):
    if not isinstance(real_graph, dict):
        return {}
    for material in real_graph.get("materials", []) or []:
        if isinstance(material, dict) and isinstance(material.get("comment_blocks"), dict):
            return material.get("comment_blocks")
    return {}


def _repo_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _ue_path(path):
    return str(path or "").replace("\\", "/")
