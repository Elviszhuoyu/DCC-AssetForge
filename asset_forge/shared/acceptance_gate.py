"""Acceptance gate policy helpers for CI and stage validation."""

from __future__ import absolute_import


def create_gate_policy(strict=False, block_warnings=None, require_import=False):
    active_strict = bool(strict)
    return {
        "strict": active_strict,
        "block_warnings": active_strict if block_warnings is None else bool(block_warnings),
        "require_import": bool(require_import),
    }


PACKAGE_STAGES = ("package_acceptance", "package_acceptance_flow", "batch_package_acceptance", "batch_package_acceptance_flow")


def apply_acceptance_gate(report, policy=None):
    policy = policy or create_gate_policy()
    reasons = list(report.get("mandatory_blockers", []))
    summary = report.get("summary", {})

    package_gate = report.get("stage") in PACKAGE_STAGES
    if package_gate or policy.get("strict") or policy.get("block_warnings"):
        if summary.get("error_count", 0) or report.get("errors") or (package_gate and (
            summary.get("can_accept") is False or report.get("status") in ("failed", "error")
        )):
            reasons.append("存在阻断错误，当前门禁不通过")
            reasons.extend(_messages(report.get("errors", [])))
        if policy.get("block_warnings") and (summary.get("warning_count", 0) > 0 or report.get("warnings")):
            reasons.append("存在警告，当前 gate policy 配置为 warning 阻断")
            reasons.extend(_messages(report.get("warnings", [])))

    if package_gate:
        for child in report.get("reports", []):
            if child.get("gate_passed") is False:
                for reason in child.get("blocking_reasons") or ["资产包验收失败"]:
                    if reason not in reasons:
                        reasons.append(reason)

    if policy.get("require_import") and not _has_real_import_passed(report):
        reasons.append("当前 gate policy 要求真实 UE import 与导入后验收通过")

    gate_passed = not reasons
    if package_gate and not gate_passed:
        from asset_forge.shared.report_schema import attach_acceptance_summary, create_report_guidance
        policy_action = summary.get("next_action", "")
        if summary.get("can_accept") and not report.get("errors"):
            if policy.get("block_warnings") and summary.get("warning_count"):
                policy_action = "处理当前策略阻断的警告后重新验收"
            elif policy.get("require_import"):
                policy_action = "在目标 UE 工程运行真实导入及导入后校验"
        summary.update(can_accept=False, can_import=False, next_action=policy_action)
        summary.update(create_report_guidance("error", [], reasons, policy_action, False))
        attach_acceptance_summary(report, summary)
        if "user_guidance" in report:
            report["user_guidance"].update({key: summary[key] for key in ("decision", "decision_label", "can_import", "why", "next_steps")})
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
