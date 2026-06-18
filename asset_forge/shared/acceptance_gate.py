"""Acceptance gate policy helpers for CI and stage validation."""

from __future__ import absolute_import


def create_gate_policy(strict=False, block_warnings=None, require_import=False):
    active_strict = bool(strict)
    return {
        "strict": active_strict,
        "block_warnings": active_strict if block_warnings is None else bool(block_warnings),
        "require_import": bool(require_import),
    }


def apply_acceptance_gate(report, policy=None):
    policy = policy or create_gate_policy()
    reasons = []
    summary = report.get("summary", {})

    if policy.get("strict"):
        if summary.get("error_count", 0) > 0 or report.get("errors"):
            reasons.append("存在阻断错误，strict gate 不通过")
            reasons.extend(_messages(report.get("errors", [])))
        if policy.get("block_warnings") and (summary.get("warning_count", 0) > 0 or report.get("warnings")):
            reasons.append("存在警告，当前 gate policy 配置为 warning 阻断")
            reasons.extend(_messages(report.get("warnings", [])))

    if policy.get("require_import") and not _has_real_import_passed(report):
        reasons.append("当前 gate policy 要求真实 UE import 与导入后验收通过")

    gate_passed = not reasons
    report["gate_policy"] = dict(policy)
    report["gate_status"] = "pass" if gate_passed else "failed"
    report["gate_passed"] = gate_passed
    report["blocking_reasons"] = reasons
    return report


def _has_real_import_passed(report):
    if report.get("stage") == "batch_package_acceptance_flow":
        return all(_has_real_import_passed(item) for item in report.get("reports", []))

    if report.get("stage") != "package_acceptance_flow":
        return False

    import_report = report.get("import", {})
    if not report.get("run_import", False):
        return False
    if import_report.get("status") != "success":
        return False
    post_import = report.get("post_import_validation") or import_report.get("post_import_validation", {})
    if post_import:
        return bool(post_import.get("can_accept", post_import.get("status") == "pass"))
    return True


def _messages(items):
    result = []
    for item in items or []:
        if isinstance(item, dict) and item.get("message"):
            result.append(item.get("message"))
        elif item:
            result.append(str(item))
    return result
