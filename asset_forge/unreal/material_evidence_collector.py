"""Real Unreal material evidence collector."""

from __future__ import absolute_import

from asset_forge.unreal.material_graph_evidence import planned_parent_parameters
from asset_forge.unreal.unreal_bridge import get_unreal


class UnrealMaterialEvidenceCollector(object):
    """Collect lightweight real-UE evidence for material graph acceptance."""

    def __init__(self, unreal_module=None):
        self.unreal = unreal_module if unreal_module is not None else get_unreal()

    def is_available(self):
        return self.unreal is not None

    def collect(self, report):
        if not self.is_available():
            return {}

        parents = planned_parent_parameters(report.get("material_binding_plan", {}))
        graph = self._collect_graph(parents)
        compile_log = self._collect_compile_log(list(parents))
        return {
            "material_compile_log_evidence": compile_log,
            "real_ue_material_graph": graph,
        }

    def _collect_graph(self, parents):
        materials = []
        issues = []
        for material_path, expected in parents.items():
            material_asset = self._load_asset(material_path)
            material = {
                "material_path": material_path,
                "exists": bool(material_asset),
                "class": _class_name(material_asset),
                "expressions": [],
                "required_parameters": {},
                "comment_blocks": {},
            }
            if not material_asset:
                issues.append("Missing material: {0}".format(material_path))
                materials.append(material)
                continue

            if not material_path.startswith("/AssetForge/"):
                material["comment_blocks"] = {"status": "not_applicable"}
                material["expected_texture_parameters"] = sorted(expected)
                try:
                    names = self.unreal.MaterialEditingLibrary.get_texture_parameter_names(material_asset)
                    declared = sorted(str(name) for name in names)
                    declared_lower = {name.lower() for name in declared}
                    missing = sorted(name for name in expected if name.lower() not in declared_lower)
                    material["declared_texture_parameters"] = declared
                    material["missing_texture_parameters"] = missing
                    if missing:
                        issues.append("{0} missing texture parameters: {1}".format(material_path, ", ".join(missing)))
                except (AttributeError, RuntimeError, TypeError) as exc:
                    issues.append("Cannot read texture parameters for {0}: {1}".format(material_path, exc))
                materials.append(material)
                continue

            expressions = self._material_expressions(material_asset)
            for expression in expressions:
                row = self._expression_row(expression)
                material["expressions"].append(row)
                parameter_name = row.get("parameter_name", "")
                if parameter_name:
                    material["required_parameters"][parameter_name] = row
            material["comment_blocks"] = self._comment_blocks_summary(material_asset)
            materials.append(material)

        required = ("BaseColor", "Normal", "ARM")
        for material in materials:
            if not material.get("exists") or not material["material_path"].startswith("/AssetForge/"):
                continue
            missing = [name for name in required if name not in material.get("required_parameters", {})]
            for name in missing:
                issues.append("{0} missing parameter {1}".format(material.get("material_path", ""), name))

        return {
            "status": "error" if issues else ("pass" if materials else "skipped"),
            "source": "Unreal Python material expression readback",
            "materials": materials,
            "material_count": len(materials),
            "issues": issues,
        }

    def _collect_compile_log(self, material_paths):
        issues = []
        readback = []
        unavailable = []
        library = _material_comment_library(self.unreal)
        read_errors = getattr(library, "try_read_asset_forge_material_compile_errors", None)
        for material_path in material_paths:
            if read_errors is None:
                unavailable.append(material_path)
                continue
            material_asset = self._load_asset(material_path)
            if not material_asset:
                issues.append("Missing material: {0}".format(material_path))
                continue
            try:
                errors = read_errors(material_asset)
            except (AttributeError, RuntimeError, TypeError) as exc:
                issues.append("{0}: {1}".format(material_path, exc))
                continue
            if errors is None:
                unavailable.append(material_path)
                continue
            readback.append(material_path)
            issues.extend("{0}: {1}".format(material_path, error) for error in errors)
        return {
            "status": "error" if issues else ("pass" if readback and not unavailable else "skipped"),
            "source": "Unreal cached material shader resource",
            "material_paths": list(material_paths),
            "recompiled_materials": [],
            "readback_materials": readback,
            "unavailable_materials": unavailable,
            "error_count": len(issues),
            "warning_count": len(unavailable),
            "messages": [{"severity": "error", "text": item} for item in issues] + [
                {"severity": "warning", "text": "Cached shader evidence unavailable: {0}".format(path)}
                for path in unavailable
            ],
        }

    def _load_asset(self, path):
        load_asset = getattr(self.unreal, "load_asset", None)
        if not load_asset:
            return None
        try:
            return load_asset(path)
        except Exception:
            return None

    def _material_expressions(self, material_asset):
        if hasattr(material_asset, "get_editor_property"):
            try:
                expressions = list(material_asset.get_editor_property("expressions") or [])
                if expressions:
                    return expressions
            except Exception:
                pass
        expressions = list(getattr(material_asset, "expressions", []) or [])
        if expressions:
            return expressions
        return self._material_expressions_from_object_iterator(material_asset)

    def _material_expressions_from_object_iterator(self, material_asset):
        object_iterator = getattr(self.unreal, "ObjectIterator", None)
        if object_iterator is None:
            return []
        material_name = _object_path_name(material_asset)
        expressions = []
        try:
            iterator = object_iterator()
        except Exception:
            return []
        for candidate in iterator:
            class_name = _class_name(candidate)
            if not class_name.startswith("MaterialExpression"):
                continue
            outer = getattr(candidate, "get_outer", lambda: None)()
            if _object_path_name(outer) == material_name:
                expressions.append(candidate)
        return expressions

    def _expression_row(self, expression):
        return {
            "expression_class": _class_name(expression),
            "parameter_name": str(_property(expression, "parameter_name", "") or ""),
            "sampler_type": str(_property(expression, "sampler_type", "")),
            "default_texture": _object_path_name(_property(expression, "texture", None)),
            "x": _property(expression, "material_expression_editor_x", 0),
            "y": _property(expression, "material_expression_editor_y", 0),
        }

    def _comment_blocks_summary(self, material_asset):
        library = _material_comment_library(self.unreal)
        describe = getattr(library, "read_asset_forge_comment_blocks", None)
        if describe is None:
            return {"status": "not_provided", "message": "DCC AssetForge material comment library is unavailable."}
        try:
            description = str(describe(material_asset) or "")
        except Exception as exc:
            return {"status": "error", "message": str(exc)}
        fields = _parse_comment_summary(description)
        status = "pass"
        expected = int(fields.get("expected_af_comments") or 0)
        linked = int(fields.get("linked_graph_comments") or 0)
        expressions = int(fields.get("expression_comments") or 0)
        orphan = int(fields.get("orphan_graph_comments") or 0)
        duplicate = int(fields.get("duplicate_comments") or 0)
        invalid_dimensions = int(fields.get("invalid_graph_comment_dimensions") or 0)
        visible_with_size = int(fields.get("visible_graph_comments_with_size") or 0)
        has_dimension_readback = int(fields.get("graph_comment_dimension_rows") or 0) > 0
        graph_available = bool(fields.get("graph_readback_available", 1))
        if not expected:
            status = "not_provided"
        elif expressions < expected or orphan or duplicate or invalid_dimensions:
            status = "error"
        elif not graph_available:
            status = "not_provided"
        elif linked < expected or (has_dimension_readback and visible_with_size < expected):
            status = "warning"
        cold_start_status = _cold_start_readback_status(fields)
        visible_for_risk = visible_with_size if has_dimension_readback else expected
        graph_not_open = not graph_available and status == "not_provided"
        visual_risk = _comment_block_visual_risk(expected, expressions, linked, orphan, duplicate, invalid_dimensions, visible_for_risk)
        next_action = _comment_block_next_action(status, linked, orphan, duplicate, invalid_dimensions)
        if graph_not_open:
            visual_risk = "unknown"
            next_action = "open the material graph and rerun comment readback"
        return dict(
            fields,
            status=status,
            raw=description,
            summary=_comment_block_summary(expected, expressions, linked, orphan, duplicate, invalid_dimensions, visible_with_size),
            visual_review_risk=visual_risk,
            next_action=next_action,
            current_session_readback_status="provided" if graph_available and status != "not_provided" else "not_provided",
            cold_start_readback_status=cold_start_status,
            cold_start_readback_required=cold_start_status not in ("pass", "success", "verified"),
            real_ue_screenshot_required=True,
            persistence_status=_comment_block_persistence_status(status, cold_start_status),
            persistence_boundary="current_session_readback_only",
            persistence_next_action=_comment_block_persistence_next_action(status, cold_start_status),
        )


def _material_comment_library(unreal_module):
    for name in ("AssetForgeEditorMaterialCommentLibrary", "AssetForgeMaterialCommentLibrary"):
        library = getattr(unreal_module, name, None)
        if library is not None:
            return library
    return None


def _class_name(obj):
    if obj is None:
        return ""
    try:
        return obj.get_class().get_name()
    except Exception:
        return obj.__class__.__name__


def _property(obj, name, default=None):
    if obj is None:
        return default
    if hasattr(obj, "get_editor_property"):
        try:
            return obj.get_editor_property(name)
        except Exception:
            pass
    return getattr(obj, name, default)


def _object_path_name(obj):
    if obj is None:
        return ""
    get_path_name = getattr(obj, "get_path_name", None)
    if get_path_name:
        try:
            return get_path_name()
        except Exception:
            pass
    return str(obj)


def _parse_comment_summary(description):
    prefix = "SUMMARY "
    result = {}
    for line in description.splitlines():
        if not line.startswith(prefix):
            continue
        for chunk in line[len(prefix) :].split("|"):
            if "=" not in chunk:
                continue
            key, value = chunk.split("=", 1)
            try:
                result[key] = int(value)
            except ValueError:
                result[key] = value
        break
    if not result:
        return {}
    graph_dimensions = _parse_graph_comment_dimensions(description)
    result.update(graph_dimensions)
    return result


def _parse_graph_comment_dimensions(description):
    graph_count = 0
    visible_with_size = 0
    invalid_dimensions = 0
    for line in description.splitlines():
        if not line.startswith("GRAPH AF "):
            continue
        graph_count += 1
        values = {}
        for chunk in line.split("|"):
            if "=" not in chunk:
                continue
            key, value = chunk.split("=", 1)
            try:
                values[key] = int(value)
            except ValueError:
                values[key] = value
        width = int(values.get("NodeWidth") or 0)
        height = int(values.get("NodeHeight") or 0)
        if width > 0 and height > 0:
            visible_with_size += 1
        else:
            invalid_dimensions += 1
    return {
        "graph_comment_dimension_rows": graph_count,
        "visible_graph_comments_with_size": visible_with_size,
        "invalid_graph_comment_dimensions": invalid_dimensions,
    }


def _comment_block_summary(expected, expressions, linked, orphan, duplicate, invalid_dimensions=0, visible_with_size=0):
    return (
        "expected={0}, expression_comments={1}, linked_graph_comments={2}, "
        "orphan_graph_comments={3}, duplicate_comments={4}, "
        "visible_graph_comments_with_size={5}, invalid_graph_comment_dimensions={6}"
    ).format(expected, expressions, linked, orphan, duplicate, visible_with_size, invalid_dimensions)


def _comment_block_visual_risk(expected, expressions, linked, orphan, duplicate, invalid_dimensions=0, visible_with_size=0):
    if not expected:
        return "unknown"
    if expressions < expected or orphan or duplicate or linked == 0 or invalid_dimensions:
        return "high"
    if linked < expected or visible_with_size < expected:
        return "medium"
    return "low"


def _comment_block_next_action(status, linked, orphan, duplicate, invalid_dimensions=0):
    if status == "not_provided":
        return "enable AssetForgeMaterialCommentLibrary and rerun real UE material evidence collection"
    if invalid_dimensions:
        return "repair visible material graph comment box dimensions and reopen the material graph before acceptance"
    if linked == 0:
        return "open the material graph, recreate visible comment boxes, then capture a screenshot for TA review"
    if orphan or duplicate:
        return "repair orphan or duplicate material graph comment boxes and rerun evidence collection"
    if status == "warning":
        return "open the material graph and verify remaining visible comment regions before import acceptance"
    return "capture a material graph screenshot for TA visual review"


def _cold_start_readback_status(fields):
    value = fields.get("cold_start_readback_status") or fields.get("cold_start_readback") or "not_verified"
    return str(value or "not_verified")


def _comment_block_persistence_status(status, cold_start_status):
    if status in ("error", "not_provided"):
        return "blocked_by_comment_readback"
    if cold_start_status in ("pass", "success", "verified"):
        return "cold_start_readback_provided"
    return "needs_cold_start_readback"


def _comment_block_persistence_next_action(status, cold_start_status):
    if status in ("error", "not_provided"):
        return "fix comment block readback before checking Comment Box persistence"
    if cold_start_status in ("pass", "success", "verified"):
        return "capture a real UE material graph screenshot after the cold-start readback"
    return "restart Unreal Editor, reopen the material graph, rerun comment readback, and capture a real UE screenshot"
