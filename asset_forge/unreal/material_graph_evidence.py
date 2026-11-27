"""Evidence gate for proving the UE material graph chain is really usable."""

from __future__ import absolute_import

from asset_forge.unreal.material_texture_binding_validator import is_official_texture_default, texture_binding_check_status

REQUIRED_TEXTURE_PARAMETERS = {
    "BaseColor": "color",
    "Normal": "normal",
    "ARM": "masks",
}


def build_material_graph_evidence_report(
    material_binding_plan=None,
    parent_material_validation=None,
    material_network_reports=None,
    material_parameter_report=None,
    material_assignment_report=None,
    material_sampler_policy_validation=None,
    compile_log_evidence=None,
    real_ue_material_graph=None,
    material_texture_binding_validation=None,
):
    """Build a report that links parent graph, MI overrides and slot binding."""
    material_binding_plan = material_binding_plan or {}
    parent_material_validation = parent_material_validation or {}
    material_network_reports = material_network_reports or []
    material_parameter_report = material_parameter_report or {}
    material_assignment_report = material_assignment_report or {}
    material_sampler_policy_validation = material_sampler_policy_validation or {}
    compile_log_evidence = compile_log_evidence or {}
    real_ue_material_graph = real_ue_material_graph or {}

    checks = []
    checks.extend(_parent_material_checks(material_binding_plan, parent_material_validation))
    checks.extend(_required_parameter_checks(material_binding_plan, material_network_reports))
    checks.extend(_sampler_policy_checks(material_sampler_policy_validation))
    texture_validation = material_texture_binding_validation or {}
    binding_checks = [dict(row, status=texture_binding_check_status(texture_validation, row))
                      for row in texture_validation.get("checks", [])
                      if row["id"] in {"required_texture_parameter_missing", "material_instance_texture_readback"}
                      and row["status"] != "pass"]
    failed_parameters = {(row["material_instance_path"], row["parameter"]) for row in binding_checks}
    checks.extend(row for row in _mi_texture_override_checks(material_binding_plan, material_parameter_report)
                  if row["status"] != "pass" or (row.get("material_instance_path"), row.get("parameter")) not in failed_parameters)
    checks.extend(binding_checks)
    checks.extend(_slot_binding_checks(material_binding_plan, material_assignment_report))
    checks.extend(_compile_log_checks(compile_log_evidence, real_ue_material_graph))

    errors = [item for item in checks if item.get("status") == "error"]
    warnings = [item for item in checks if item.get("status") == "warning"]
    manual_validation = []
    for item in checks:
        manual_validation.extend(item.get("manual_validation_required", []))
    visual_review = _ta_visual_review_summary(checks, real_ue_material_graph)

    return {
        "stage": "material_graph_evidence",
        "status": "error" if errors else ("warning" if warnings else "pass"),
        "real_ue_evidence": "provided" if _has_real_ue_evidence(compile_log_evidence, real_ue_material_graph) else "not_provided",
        "required_texture_parameters": sorted({
            parameter for parent, parameters in planned_parent_parameters(material_binding_plan).items()
            for parameter in (REQUIRED_TEXTURE_PARAMETERS if parent.startswith("/AssetForge/") else parameters)
        }),
        "ta_visual_review": visual_review,
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
        "manual_validation_required": sorted(set(manual_validation + visual_review.get("manual_validation_required", []))),
        "message": _report_message(errors, warnings),
    }


def _parent_material_checks(material_binding_plan, parent_material_validation):
    checks = []
    missing = set(parent_material_validation.get("missing_parent_materials", []) or [])
    for item in parent_material_validation.get("checks", []) or []:
        if item.get("status") != "error" or not item.get("parent_material"):
            continue
        if item.get("id") == "parent_texture_parameters":
            checks.append(_check("parent_texture_parameters", "error", item.get("message", ""),
                                 parent_material=item["parent_material"], missing_parameters=item.get("missing_parameters", [])))
        else:
            missing.add(item["parent_material"])

    parent_paths = planned_parent_parameters(material_binding_plan)
    if not parent_paths:
        return [
            _check(
                "parent_material_exists",
                "warning",
                "No parent material path was provided by the material binding plan.",
                evidence_status="not_provided",
                manual_validation_required=["material binding plan must select a parent material"],
            )
        ]

    validation_status = parent_material_validation.get("status", "")
    for parent_path in parent_paths:
        if parent_path in missing or (validation_status == "error" and not parent_material_validation.get("checks") and not missing):
            checks.append(_check("parent_material_exists", "error", "Missing parent material: {0}".format(parent_path), parent_material=parent_path))
        elif validation_status not in ("pass", "success", "error"):
            checks.append(
                _check(
                    "parent_material_exists",
                    "warning",
                    "Parent material validation report is not provided for {0}.".format(parent_path),
                    parent_material=parent_path,
                    evidence_status="not_provided",
                    manual_validation_required=["run parent material validation in UE"],
                )
            )
        else:
            checks.append(_check("parent_material_exists", "pass", "Parent material is available in the current validation report.", parent_material=parent_path))
    return checks


def _required_parameter_checks(material_binding_plan, material_network_reports):
    checks = []
    networks = _network_by_material_path(material_network_reports)
    for parent_path in planned_parent_parameters(material_binding_plan):
        if not parent_path.startswith("/AssetForge/"):
            continue
        network = networks.get(parent_path, {})
        if not network:
            checks.append(
                _check(
                    "parent_material_network_readback",
                    "warning",
                    "No material network report was provided for {0}.".format(parent_path),
                    parent_material=parent_path,
                    evidence_status="not_provided",
                    manual_validation_required=["read back material graph nodes in real UE or attach bootstrap network plan"],
                )
            )
            continue

        nodes = _nodes_by_parameter(network)
        for parameter, expected_sampler in sorted(REQUIRED_TEXTURE_PARAMETERS.items()):
            node = nodes.get(parameter)
            if not node:
                checks.append(
                    _check(
                        "required_texture_parameter",
                        "error",
                        "Parent material {0} is missing required texture parameter {1}.".format(parent_path, parameter),
                        parent_material=parent_path,
                        parameter=parameter,
                        expected_sampler_type=expected_sampler,
                    )
                )
                continue

            checks.append(
                _check(
                    "required_texture_parameter",
                    "pass",
                    "Parent material exposes required texture parameter {0}.".format(parameter),
                    parent_material=parent_path,
                    parameter=parameter,
                )
            )
            checks.append(_sampler_check(parent_path, parameter, expected_sampler, node.get("sampler_type", "")))
    return checks


def _sampler_policy_checks(material_sampler_policy_validation):
    status = material_sampler_policy_validation.get("status")
    if not status:
        return [
            _check(
                "material_sampler_policy_validation",
                "warning",
                "No sampler policy validation report was provided.",
                evidence_status="not_provided",
                manual_validation_required=["run material sampler policy validation after texture import"],
            )
        ]
    if status in ("pass", "success"):
        return [_check("material_sampler_policy_validation", "pass", "Sampler policy report is pass.")]
    if status in ("warning", "manual_validation_required", "skipped", "not_provided"):
        return [_check("material_sampler_policy_validation", "warning", "Sampler policy report has warnings.")]
    return [_check("material_sampler_policy_validation", "error", "Sampler policy report is {0}.".format(status))]


def _mi_texture_override_checks(material_binding_plan, material_parameter_report):
    planned = _planned_texture_overrides(material_binding_plan)
    if not planned:
        return [
            _check(
                "mi_texture_overrides",
                "warning",
                "No texture override is planned for this material instance.",
                evidence_status="not_provided",
                manual_validation_required=["import package with texture maps to validate MI overrides"],
            )
        ]

    applied = _applied_texture_overrides(material_parameter_report)
    if not material_parameter_report or material_parameter_report.get("status") in ("skipped", "not_provided") or not material_parameter_report.get("texture_parameters"):
        return [
            _check(
                "mi_texture_overrides",
                "warning",
                "Material instance texture parameter report is not provided.",
                planned_overrides=planned,
                evidence_status="not_provided",
                manual_validation_required=["run UE import and capture material_parameter_report"],
            )
        ]

    checks = []
    for item in planned:
        key = (item["material_instance_path"], item["parameter"])
        applied_item = applied.get(key)
        if applied_item:
            applied_path = _texture_path_from_parameter(applied_item)
            if not applied_path:
                checks.append(
                    _check(
                        "mi_texture_override_readback",
                        "warning",
                        "Material instance override was applied but the texture asset path was not captured: {0}.{1}".format(
                            item["material_instance_path"],
                            item["parameter"],
                        ),
                        parameter=item["parameter"],
                        material_instance_path=item["material_instance_path"],
                        texture_asset_path=item["texture_asset_path"],
                        evidence_status="not_provided",
                        manual_validation_required=["capture MI texture parameter asset_path readback after UE import"],
                    )
                )
                continue
            if _canonical_asset_path(applied_path) != _canonical_asset_path(item["texture_asset_path"]):
                checks.append(
                    _check(
                        "mi_texture_override_asset_path",
                        "error",
                        "Material instance override points to the wrong texture: {0}.{1}".format(
                            item["material_instance_path"],
                            item["parameter"],
                        ),
                        parameter=item["parameter"],
                        material_instance_path=item["material_instance_path"],
                        expected_texture_asset_path=item["texture_asset_path"],
                        actual_texture_asset_path=applied_path,
                    )
                )
                continue
            checks.append(
                _check(
                    "mi_texture_override_applied",
                    "pass",
                    "Material instance override applied: {0}.{1}".format(item["material_instance_path"], item["parameter"]),
                    parameter=item["parameter"],
                    material_instance_path=item["material_instance_path"],
                    texture_asset_path=item["texture_asset_path"],
                    actual_texture_asset_path=applied_path,
                )
            )
        else:
            checks.append(
                _check(
                    "mi_texture_override_applied",
                    "error",
                    "Planned material instance override was not applied: {0}.{1}".format(item["material_instance_path"], item["parameter"]),
                    parameter=item["parameter"],
                    material_instance_path=item["material_instance_path"],
                    texture_asset_path=item["texture_asset_path"],
                )
            )
    return checks


def _slot_binding_checks(material_binding_plan, material_assignment_report):
    planned_count = material_binding_plan.get("count", len(material_binding_plan.get("materials", []) or []))
    if not planned_count:
        return [_check("slot_binding", "warning", "No material slot binding plan was provided.", evidence_status="not_provided")]
    if not material_assignment_report:
        return [
            _check(
                "slot_binding",
                "warning",
                "Material assignment report is not provided.",
                evidence_status="not_provided",
                manual_validation_required=["run UE import and capture material_assignment_report"],
            )
        ]

    status = material_assignment_report.get("status", "")
    assigned = material_assignment_report.get("assigned", []) or []
    if assigned:
        checks = _slot_binding_match_checks(material_binding_plan, assigned)
        checks.extend(_slot_binding_readback_checks(assigned))
        if status in ("warning", "skipped"):
            checks.append(
                _check(
                    "slot_binding_report_status",
                    "warning",
                    "Material slot binding is {0}.".format(status or "not_provided"),
                    assigned_count=len(assigned),
                    evidence_status=status or "not_provided",
                    manual_validation_required=["open imported Static Mesh and verify slot material assignment"],
                )
            )
        return checks
    if status in ("warning", "skipped"):
        return [
            _check(
                "slot_binding",
                "warning",
                "Material slot binding is {0}.".format(status or "not_provided"),
                assigned_count=len(assigned),
                evidence_status=status or "not_provided",
                manual_validation_required=["open imported Static Mesh and verify slot material assignment"],
            )
        ]
    return [_check("slot_binding", "error", "Material slot binding failed: {0}.".format(status), assigned_count=len(assigned))]


def _slot_binding_match_checks(material_binding_plan, assigned):
    checks = []
    planned = material_binding_plan.get("materials", []) or []
    planned_by_name = {}
    planned_paths = []
    for item in planned:
        material_name = item.get("material_name", "")
        target_path = item.get("target_asset_path", "") or item.get("material_instance_path", "")
        if material_name and target_path:
            planned_by_name[material_name] = target_path
        if target_path and target_path not in planned_paths:
            planned_paths.append(target_path)

    assigned_names = set()
    assigned_paths = set()
    for item in assigned:
        material_name = item.get("material_name", "")
        material_instance = item.get("material_instance", "")
        if material_name:
            assigned_names.add(material_name)
        if material_instance:
            assigned_paths.add(_canonical_asset_path(material_instance))
        expected = planned_by_name.get(material_name)
        if expected and _canonical_asset_path(material_instance) != _canonical_asset_path(expected):
            checks.append(
                _check(
                    "slot_binding_material_instance",
                    "error",
                    "Static Mesh slot is bound to the wrong Material Instance: {0}::{1}".format(
                        item.get("static_mesh", ""),
                        material_name,
                    ),
                    static_mesh=item.get("static_mesh", ""),
                    slot_index=item.get("slot_index"),
                    material_name=material_name,
                    expected_material_instance=expected,
                    actual_material_instance=material_instance,
                )
            )

    missing_names = [name for name in sorted(planned_by_name.keys()) if name not in assigned_names]
    missing_paths = [path for path in planned_paths if _canonical_asset_path(path) not in assigned_paths]
    if missing_names or missing_paths:
        checks.append(
            _check(
                "slot_binding",
                "error",
                "Material slot binding report is missing planned Material Instances.",
                missing_material_names=missing_names,
                missing_material_instances=missing_paths,
                assigned_count=len(assigned),
            )
        )
        return checks

    checks.append(
        _check(
            "slot_binding",
            "pass",
            "Material instances match the planned Static Mesh slot bindings.",
            assigned_count=len(assigned),
        )
    )
    return checks


def _slot_binding_readback_checks(assigned):
    statuses = set(item.get("verification_status", "") for item in assigned if item.get("verification_status", ""))
    if "mismatch" in statuses or "error" in statuses:
        return [
            _check(
                "slot_binding_readback",
                "error",
                "Static Mesh slot readback does not match the assigned Material Instance.",
                assigned_count=len(assigned),
            )
        ]
    if statuses and all(status == "pass" for status in statuses):
        return [
            _check(
                "slot_binding_readback",
                "pass",
                "Static Mesh slot readback confirms the assigned Material Instances.",
                assigned_count=len(assigned),
            )
        ]
    return [
        _check(
            "slot_binding_readback",
            "warning",
            "Material assignment report does not include Static Mesh slot readback evidence.",
            assigned_count=len(assigned),
            evidence_status="not_provided",
            manual_validation_required=["capture Static Mesh slot material readback after UE import"],
        )
    ]


def _compile_log_checks(compile_log_evidence, real_ue_material_graph):
    checks = []
    compile_status = compile_log_evidence.get("status", "")
    if compile_status in ("pass", "success"):
        checks.append(_check("compile_log_evidence", "pass", "Material compile/log evidence is attached."))
    elif compile_status in ("error", "failed"):
        checks.append(_check("compile_log_evidence", "error", "Material compile/log evidence reports failure."))
    else:
        checks.append(
            _check(
                "compile_log_evidence",
                "warning",
                "Material compile/log evidence is not provided.",
                evidence_status="not_provided",
                manual_validation_required=["capture real UE material compile log after import"],
            )
        )

    graph_status = real_ue_material_graph.get("status", "")
    if graph_status in ("pass", "success"):
        checks.append(_check("real_ue_material_graph", "pass", "Real UE material graph readback is attached."))
    elif graph_status in ("error", "failed"):
        checks.append(_check("real_ue_material_graph", "error", "Real UE material graph readback reports failure."))
    else:
        checks.append(
            _check(
                "real_ue_material_graph",
                "warning",
                "Real UE material graph readback is not provided.",
                evidence_status="not_provided",
                manual_validation_required=["read back material graph nodes in real UE"],
            )
        )
    checks.extend(_material_comment_block_checks(real_ue_material_graph))
    checks.extend(_material_comment_box_persistence_checks(real_ue_material_graph))
    return checks


def _material_comment_block_checks(real_ue_material_graph):
    materials = real_ue_material_graph.get("materials", []) or []
    checks = []
    for material in materials:
        comment_blocks = material.get("comment_blocks", {}) or {}
        status = comment_blocks.get("status", "")
        if not status or status == "not_provided":
            checks.append(
                _check(
                    "material_comment_blocks",
                    "warning",
                    "Material comment block evidence is not provided for {0}.".format(material.get("material_path", "")),
                    parent_material=material.get("material_path", ""),
                    evidence_status="not_provided",
                    manual_validation_required=["read back DCC AssetForge material comment blocks in real UE"],
                )
            )
            continue
        if status == "not_applicable":
            continue
        if status == "error":
            expected = int(comment_blocks.get("expected_af_comments") or 0)
            expressions = int(comment_blocks.get("expression_comments") or 0)
            linked = int(comment_blocks.get("linked_graph_comments") or 0)
            orphan = int(comment_blocks.get("orphan_graph_comments") or 0)
            duplicate = int(comment_blocks.get("duplicate_comments") or 0)
            invalid_dimensions = int(comment_blocks.get("invalid_graph_comment_dimensions") or 0)
            visible_with_size = int(comment_blocks.get("visible_graph_comments_with_size") or 0)
            message = comment_blocks.get("message", "")
            if invalid_dimensions and not message:
                message = _comment_block_message(expected, expressions, linked, orphan, duplicate, invalid_dimensions, visible_with_size)
            checks.append(
                _check(
                    "material_comment_blocks",
                    "error",
                    message or "Material comment block evidence failed to read for {0}.".format(material.get("material_path", "")),
                    parent_material=material.get("material_path", ""),
                    evidence_status="error",
                    raw=comment_blocks.get("raw", ""),
                    expected_af_comments=expected,
                    expression_comments=expressions,
                    linked_graph_comments=linked,
                    orphan_graph_comments=orphan,
                    duplicate_comments=duplicate,
                    visible_graph_comments_with_size=visible_with_size,
                    invalid_graph_comment_dimensions=invalid_dimensions,
                    comment_block_summary=_comment_block_summary(expected, expressions, linked, orphan, duplicate, invalid_dimensions, visible_with_size),
                    visual_review_risk=_comment_block_visual_risk(expected, expressions, linked, orphan, duplicate, invalid_dimensions, visible_with_size),
                    next_action=_comment_block_next_action(linked, orphan, duplicate, invalid_dimensions),
                    manual_validation_required=["fix material comment evidence readback before accepting the material graph"],
                )
            )
            continue
        expected = int(comment_blocks.get("expected_af_comments") or 0)
        expressions = int(comment_blocks.get("expression_comments") or 0)
        linked = int(comment_blocks.get("linked_graph_comments") or 0)
        orphan = int(comment_blocks.get("orphan_graph_comments") or 0)
        duplicate = int(comment_blocks.get("duplicate_comments") or 0)
        invalid_dimensions = int(comment_blocks.get("invalid_graph_comment_dimensions") or 0)
        visible_with_size = int(comment_blocks.get("visible_graph_comments_with_size") or 0)
        has_dimension_readback = int(comment_blocks.get("graph_comment_dimension_rows") or 0) > 0
        has_visible_dimensions = not has_dimension_readback or visible_with_size >= expected
        if status == "pass" and linked >= expected and has_visible_dimensions and not invalid_dimensions and expected > 0:
            checks.append(
                _check(
                    "material_comment_blocks",
                    "pass",
                    "DCC AssetForge material comment blocks are linked to visible graph comments.",
                    parent_material=material.get("material_path", ""),
                    expected_af_comments=expected,
                    expression_comments=expressions,
                    linked_graph_comments=linked,
                    visible_graph_comments_with_size=visible_with_size,
                    invalid_graph_comment_dimensions=invalid_dimensions,
                    comment_block_summary=_comment_block_summary(expected, expressions, linked, orphan, duplicate, invalid_dimensions, visible_with_size),
                    visual_review_risk="low",
                    next_action="capture a material graph screenshot for TA visual review",
                )
            )
            continue
        check_status = "error" if expressions < expected or orphan or duplicate or invalid_dimensions else "warning"
        risk = _comment_block_visual_risk(expected, expressions, linked, orphan, duplicate, invalid_dimensions, visible_with_size)
        checks.append(
            _check(
                "material_comment_blocks",
                check_status,
                _comment_block_message(expected, expressions, linked, orphan, duplicate, invalid_dimensions, visible_with_size),
                parent_material=material.get("material_path", ""),
                expected_af_comments=expected,
                expression_comments=expressions,
                linked_graph_comments=linked,
                orphan_graph_comments=orphan,
                duplicate_comments=duplicate,
                visible_graph_comments_with_size=visible_with_size,
                invalid_graph_comment_dimensions=invalid_dimensions,
                comment_block_summary=_comment_block_summary(expected, expressions, linked, orphan, duplicate, invalid_dimensions, visible_with_size),
                visual_review_risk=risk,
                next_action=_comment_block_next_action(linked, orphan, duplicate, invalid_dimensions),
                manual_validation_required=["repair material comment graph links and reopen the material graph"],
            )
        )
    return checks


def _ta_visual_review_summary(checks, real_ue_material_graph):
    comment_checks = [item for item in checks if item.get("id") == "material_comment_blocks"]
    persistence_checks = [item for item in checks if item.get("id") == "material_comment_box_persistence"]
    screenshot_ready = _has_visual_screenshot_evidence(real_ue_material_graph)
    blocking_comments = [item for item in comment_checks if item.get("status") == "error"]
    risky_comments = [item for item in comment_checks if item.get("status") == "warning"]
    blocking_persistence = [item for item in persistence_checks if item.get("status") == "error"]
    risky_persistence = [item for item in persistence_checks if item.get("status") == "warning"]
    next_steps = []
    manual_validation = []

    materials = real_ue_material_graph.get("materials", []) or []
    project_only = bool(materials) and all(
        item.get("comment_blocks", {}).get("status") == "not_applicable" for item in materials
    )
    if project_only:
        status = "manual_validation_required"
        decision_label = "按项目标准复核材质外观"
    elif blocking_comments or blocking_persistence:
        status = "blocked"
        decision_label = "材质图注释结构需修复"
        next_steps.append("repair DCC AssetForge material comment blocks before TA visual review")
    elif risky_comments or risky_persistence:
        status = "manual_validation_required"
        decision_label = "材质图可读性需要人工复核"
        if risky_persistence:
            if any(item.get("cold_start_readback_required") for item in risky_persistence):
                next_steps.append("cold-start Unreal, reopen the material graph, and verify Comment Box persistence")
                manual_validation.append("cold-start Unreal and verify Comment Box persistence with real UE screenshot")
        else:
            next_steps.append("open the material graph and verify visible comment regions")
    elif not comment_checks:
        status = "manual_validation_required"
        decision_label = "缺少材质图可读性证据"
        next_steps.append("read back DCC AssetForge material comment blocks in real UE")
    else:
        status = "ready_for_visual_review" if screenshot_ready else "manual_validation_required"
        decision_label = "材质图结构证据可读，等待截图复核"

    if not screenshot_ready:
        next_steps.append("capture material graph screenshot or viewport evidence for TA review")
        manual_validation.append("capture material graph screenshot or viewport evidence for TA review")

    return {
        "status": status,
        "decision_label": decision_label,
        "api_readback_is_visual_pass": False,
        "screenshot_evidence": "provided" if screenshot_ready else "not_provided",
        "comment_block_checks": len(comment_checks),
        "comment_block_warnings": len(risky_comments),
        "comment_block_errors": len(blocking_comments),
        "comment_box_persistence_status": "not_applicable" if project_only else _comment_box_persistence_summary_status(persistence_checks),
        "comment_box_persistence_checks": len(persistence_checks),
        "comment_box_persistence_warnings": len(risky_persistence),
        "comment_box_persistence_errors": len(blocking_persistence),
        "cold_start_readback_required": any(item.get("cold_start_readback_required") for item in persistence_checks),
        "real_ue_screenshot_required": any(item.get("real_ue_screenshot_required") for item in persistence_checks) or not screenshot_ready,
        "next_action": next_steps[0] if next_steps else "perform TA visual review in Unreal Editor",
        "next_steps": next_steps or ["perform TA visual review in Unreal Editor"],
        "manual_validation_required": manual_validation,
    }


def _has_visual_screenshot_evidence(real_ue_material_graph):
    screenshot = real_ue_material_graph.get("screenshot_evidence", {}) or {}
    if screenshot.get("status") in ("pass", "success", "provided") and (
        screenshot.get("path") or screenshot.get("paths") or screenshot.get("count")
    ):
        return True
    if real_ue_material_graph.get("screenshots"):
        return True
    for material in real_ue_material_graph.get("materials", []) or []:
        if material.get("screenshot_path") or material.get("graph_screenshot"):
            return True
    return False


def _material_comment_box_persistence_checks(real_ue_material_graph):
    materials = real_ue_material_graph.get("materials", []) or []
    screenshot_ready = _has_visual_screenshot_evidence(real_ue_material_graph)
    checks = []
    for material in materials:
        comment_blocks = material.get("comment_blocks", {}) or {}
        status = comment_blocks.get("status", "")
        if not status or status in ("not_provided", "not_applicable"):
            continue
        cold_start_status = _comment_block_cold_start_status(comment_blocks)
        current_status = comment_blocks.get("current_session_readback_status") or ("provided" if status in ("pass", "warning") else "error")
        if status == "error":
            checks.append(
                _check(
                    "material_comment_box_persistence",
                    "error",
                    "Comment Box persistence cannot be evaluated until comment block readback succeeds.",
                    parent_material=material.get("material_path", ""),
                    current_session_readback_status=current_status,
                    cold_start_readback_status=cold_start_status,
                    real_ue_screenshot_status="provided" if screenshot_ready else "not_provided",
                    persistence_status="blocked_by_comment_readback",
                    cold_start_readback_required=True,
                    real_ue_screenshot_required=not screenshot_ready,
                    manual_validation_required=["fix comment block readback before checking Comment Box persistence"],
                    next_action="fix comment block readback before checking Comment Box persistence",
                )
            )
            continue
        if cold_start_status in ("pass", "success", "verified") and screenshot_ready:
            checks.append(
                _check(
                    "material_comment_box_persistence",
                    "pass",
                    "Comment Box persistence has cold-start readback and real UE screenshot evidence.",
                    parent_material=material.get("material_path", ""),
                    current_session_readback_status=current_status,
                    cold_start_readback_status=cold_start_status,
                    real_ue_screenshot_status="provided",
                    persistence_status="verified",
                    cold_start_readback_required=False,
                    real_ue_screenshot_required=False,
                    next_action="perform TA visual review in Unreal Editor",
                )
            )
            continue
        missing_steps = []
        if cold_start_status not in ("pass", "success", "verified"):
            missing_steps.append("restart Unreal Editor, reopen the material graph, and rerun comment readback")
        if not screenshot_ready:
            missing_steps.append("capture a real UE material graph screenshot")
        message = "Current-session Comment Box readback does not prove the boxes persist after closing and reopening Unreal."
        if cold_start_status in ("pass", "success", "verified") and not screenshot_ready:
            message = "Comment Box persistence has cold-start readback; real UE screenshot evidence is still required for TA visual review."
        checks.append(
            _check(
                "material_comment_box_persistence",
                "warning",
                message,
                parent_material=material.get("material_path", ""),
                current_session_readback_status=current_status,
                cold_start_readback_status=cold_start_status,
                real_ue_screenshot_status="provided" if screenshot_ready else "not_provided",
                persistence_status="needs_on_site_review",
                cold_start_readback_required=cold_start_status not in ("pass", "success", "verified"),
                real_ue_screenshot_required=not screenshot_ready,
                manual_validation_required=missing_steps,
                next_action=", then ".join(missing_steps),
            )
        )
    return checks


def _comment_block_cold_start_status(comment_blocks):
    return str(
        comment_blocks.get("cold_start_readback_status")
        or comment_blocks.get("cold_start_readback")
        or "not_verified"
    )


def _comment_box_persistence_summary_status(persistence_checks):
    if not persistence_checks:
        return "not_provided"
    if any(item.get("status") == "error" for item in persistence_checks):
        return "blocked"
    if any(item.get("status") == "warning" for item in persistence_checks):
        return "needs_on_site_review"
    return "verified"


def _comment_block_summary(expected, expressions, linked, orphan, duplicate, invalid_dimensions=0, visible_with_size=0):
    return (
        "expected={0}, expression_comments={1}, linked_graph_comments={2}, "
        "orphan_graph_comments={3}, duplicate_comments={4}, "
        "visible_graph_comments_with_size={5}, invalid_graph_comment_dimensions={6}"
    ).format(expected, expressions, linked, orphan, duplicate, visible_with_size, invalid_dimensions)


def _comment_block_visual_risk(expected, expressions, linked, orphan, duplicate, invalid_dimensions=0, visible_with_size=0):
    if orphan or duplicate or expressions < expected:
        return "high"
    if invalid_dimensions:
        return "high"
    if linked == 0 and expected > 0:
        return "high"
    if linked < expected or visible_with_size < expected:
        return "medium"
    return "low"


def _comment_block_message(expected, expressions, linked, orphan, duplicate, invalid_dimensions=0, visible_with_size=0):
    if invalid_dimensions:
        return "DCC AssetForge graph comment nodes are linked but have zero-size bounds; visible TA comment boxes are not actually readable."
    if linked == 0 and expected > 0:
        return "DCC AssetForge expression comments exist, but none are linked to visible graph comment nodes; TA graph readability is not proven."
    if orphan or duplicate:
        return "DCC AssetForge material comment nodes contain orphan or duplicate graph comments."
    if expressions < expected:
        return "DCC AssetForge material is missing expected expression comment markers."
    if visible_with_size < expected:
        return "DCC AssetForge material comments are linked, but not all graph comment boxes have visible dimensions."
    return "DCC AssetForge material comments are not fully linked to graph comment nodes."


def _comment_block_next_action(linked, orphan, duplicate, invalid_dimensions=0):
    if invalid_dimensions:
        return "repair zero-size material graph comment boxes, reopen the material editor, then capture a screenshot"
    if linked == 0:
        return "open the material graph, recreate visible comment boxes, then capture a screenshot for TA review"
    if orphan or duplicate:
        return "repair orphan or duplicate comment boxes, then rerun material evidence collection"
    return "open the material graph and confirm the remaining comment boxes are readable"


def _sampler_check(parent_path, parameter, expected_sampler, actual_sampler):
    accepted = {expected_sampler, "virtual_{0}".format(expected_sampler)}
    if actual_sampler in accepted:
        return _check(
            "sampler_type_expected",
            "pass",
            "Sampler type for {0} is {1}.".format(parameter, actual_sampler),
            parent_material=parent_path,
            parameter=parameter,
            expected_sampler_type=expected_sampler,
            actual_sampler_type=actual_sampler,
        )
    if not actual_sampler:
        return _check(
            "sampler_type_expected",
            "warning",
            "Sampler type for {0} is not provided.".format(parameter),
            parent_material=parent_path,
            parameter=parameter,
            expected_sampler_type=expected_sampler,
            actual_sampler_type="",
            evidence_status="not_provided",
            manual_validation_required=["read back sampler_type from real UE material expression"],
        )
    return _check(
        "sampler_type_expected",
        "error",
        "Sampler type for {0} is {1}, expected {2}.".format(parameter, actual_sampler, expected_sampler),
        parent_material=parent_path,
        parameter=parameter,
        expected_sampler_type=expected_sampler,
        actual_sampler_type=actual_sampler,
    )


def planned_parent_parameters(material_binding_plan):
    """Group texture parameters by the parent actually selected for each MI."""
    parents = {}
    for material in material_binding_plan.get("materials", []) or []:
        parent = material.get("parent_material") or material.get("parent_material_path")
        if parent:
            parents.setdefault(parent, set()).update(material.get("texture_parameters") or {})
    if not parents and material_binding_plan.get("master_material"):
        parents[material_binding_plan["master_material"]] = set()
    return parents


def _network_by_material_path(material_network_reports):
    networks = {}
    for item in material_network_reports or []:
        path = item.get("material_path") or item.get("parent_material") or item.get("path")
        if path and path not in networks:
            networks[path] = item
    return networks


def _nodes_by_parameter(network):
    nodes = {}
    for field in ("nodes", "created_nodes", "expressions"):
        for node in network.get(field, []) or []:
            parameter = node.get("parameter") or node.get("parameter_name") or node.get("name")
            if parameter and parameter not in nodes:
                nodes[parameter] = node
    return nodes


def _planned_texture_overrides(material_binding_plan):
    planned = []
    for material in material_binding_plan.get("materials", []) or []:
        material_path = material.get("target_asset_path", "") or material.get("material_instance_path", "")
        for parameter, texture_path in sorted((material.get("texture_parameters", {}) or {}).items()):
            if texture_path and not is_official_texture_default(texture_path):
                planned.append(
                    {
                        "material_instance_path": material_path,
                        "parameter": parameter,
                        "texture_asset_path": texture_path,
                    }
                )
    return planned


def _applied_texture_overrides(material_parameter_report):
    applied = {}
    for item in material_parameter_report.get("texture_parameters", []) or []:
        if item.get("applied"):
            applied[(item.get("material_instance_path", ""), item.get("name", ""))] = item
    return applied


def _texture_path_from_parameter(item):
    return item.get("texture_asset_path") or item.get("asset_path") or item.get("value") or ""


def _canonical_asset_path(path):
    normalized = str(path or "").replace("\\", "/")
    if "." in normalized.rsplit("/", 1)[-1]:
        normalized = normalized.rsplit(".", 1)[0]
    return normalized


def _has_real_ue_evidence(compile_log_evidence, real_ue_material_graph):
    return compile_log_evidence.get("status") in ("pass", "success") or real_ue_material_graph.get("status") in ("pass", "success")


def _report_message(errors, warnings):
    if errors:
        return "Material graph evidence has blocking errors."
    if warnings:
        return "Material graph evidence is incomplete; real UE validation is still required."
    return "Material graph evidence passed."


def _check(check_id, status, message, **extra):
    item = {
        "id": check_id,
        "status": status,
        "message": message,
    }
    item.update(extra)
    return item
