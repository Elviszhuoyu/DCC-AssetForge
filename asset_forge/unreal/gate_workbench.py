"""Read-only gate preview and single-use confirmation for the native workbench."""

from collections import OrderedDict
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import time
from uuid import uuid4

from asset_forge.shared.material_profile_schema import default_material_profiles_path
from asset_forge.shared.report_schema import attach_acceptance_summary, create_acceptance_summary, read_report
from asset_forge.unreal.acceptance_runner import UnrealPackageAcceptanceFlow, _timed
from asset_forge.unreal.gate_handoff import canonical_path as _canonical, handoff_path, invalidate_handoff, read_handoff, save_handoff
from asset_forge.unreal.gate_operator_messages import localized_message, operator_messages as _operator_messages
from asset_forge.unreal.manifest_finder import find_latest_manifest
from asset_forge.unreal.material_asset_bootstrap import UnrealMaterialAssetBootstrap
from asset_forge.unreal.unreal_bridge import get_unreal


def _stat_identity(path):
    try:
        stat = os.stat(path)
        return (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino, stat.st_mode)
    except FileNotFoundError:
        return None


def _hash_file(path):
    if not os.path.isfile(path):
        return ""
    try:
        digest = sha256()
        with open(path, "rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
    except FileNotFoundError:
        return ""


def _package_inputs(package_dir, import_options):
    path = find_latest_manifest(package_dir)
    raw = Path(path).read_bytes() if path else b""
    try:
        manifest = json.loads(raw) if raw else {}
    except (UnicodeError, ValueError):
        manifest = {}
    if not isinstance(manifest, dict):
        manifest = {}
    sources = set()
    fbx = manifest.get("fbx_path")
    if isinstance(fbx, str) and fbx:
        sources.add(_canonical(fbx))
    textures = manifest.get("textures")
    for texture in textures if isinstance(textures, list) else ():
        packaged = texture.get("package_path") if isinstance(texture, dict) else None
        if isinstance(packaged, str) and packaged:
            sources.add(_canonical(packaged))

    defaults = _canonical(default_material_profiles_path())
    profile_hashes = [(defaults, _hash_file(defaults))]
    snapshot = manifest.get("material_profiles_snapshot_path")
    if isinstance(snapshot, str) and snapshot:
        declared = Path(snapshot)
        adjacent = Path(path).parent / (declared.name if declared.is_absolute() else declared)
        for candidate in dict.fromkeys([_canonical(adjacent), _canonical(declared)]):
            profile_hashes.append((candidate, _hash_file(candidate)))
    options_key = json.dumps(import_options, sort_keys=True, allow_nan=False, separators=(",", ":"))
    stamp = (path, sha256(raw).digest(), options_key, tuple(profile_hashes),
             tuple((name, _stat_identity(name)) for name in sorted(sources)))
    return stamp, tuple(sorted(sources))


def _binary_fingerprint(sources):
    return tuple((path, _hash_file(path)) for path in sources)


def _project_identity(unreal):
    getter = getattr(getattr(unreal, "Paths", None), "get_project_file_path", None)
    path = getter() if getter else ""
    return _canonical(path).replace("\\", "/") if path else ""


def _target_assets(target_path, unreal):
    if not target_path:
        raise RuntimeError("包体未声明有效的 UE 目标路径。")
    library = getattr(unreal, "EditorAssetLibrary", None)
    if not library or not hasattr(library, "list_assets"):
        raise RuntimeError("当前 UE 编辑器无法读取目标路径中的资产。")
    if hasattr(library, "does_directory_exist") and not library.does_directory_exist(target_path):
        return ()
    return tuple(sorted(set(str(asset) for asset in library.list_assets(target_path, True, False) or [])))


def _live_conflicts(report, unreal):
    acceptance = report.get("package_acceptance", {})
    target = acceptance.get("target_path", "")
    dry_run = report.get("dry_run", {})
    folders = [target]
    for plan in ("texture_import_plan", "material_binding_plan"):
        folder = dry_run.get(plan, {}).get("target_dir", "")
        if folder and not folder.casefold().startswith(target.casefold().rstrip("/") + "/") and folder.casefold() != target.casefold():
            folders.append(folder)
    return {folder: _target_assets(folder, unreal) for folder in dict.fromkeys(folders)}


def _confirmation_values(report):
    acceptance = report["package_acceptance"]
    manifest = acceptance["manifest_validation"]["manifest"]
    dry_run = report["dry_run"]
    content = dry_run.get("import_policy_summary", {}).get("content_import_policy", {})
    labels = {"overwrite": "同名覆盖", "reuse": "同名复用", "skip": "同名跳过", "error": "同名阻断"}
    enabled = {key: content.get("import_" + key, {}).get("enabled", True) for key in ("mesh", "textures", "materials")}
    policies = []
    for key, label, fallback, plan_name, values_name, strategy_key in (
            ("mesh", "网格", "overwrite", "", "", "existing_mesh_strategy"),
            ("textures", "贴图", "overwrite", "texture_import_plan", "textures", "existing_texture_strategy"),
            ("materials", "材质实例", "reuse", "material_binding_plan", "materials", "existing_material_strategy")):
        plan = dry_run.get(plan_name, {})
        strategy = plan.get(strategy_key, manifest.get(strategy_key, fallback))
        strategies = {row.get(strategy_key, strategy) for row in plan.get(values_name, [])} or {strategy}
        description = "、".join(labels.get(value, "按包体策略") for value in sorted(strategies))
        policies.append(label + "：" + (description if enabled[key] else "本次跳过"))
    return {
        "asset_name": acceptance.get("asset_name", ""),
        "target_path": acceptance.get("target_path", ""),
        "mesh_count": int(manifest.get("mesh_count") or manifest.get("asset_count") or 1) if enabled["mesh"] else 0,
        "texture_count": len(dry_run.get("texture_import_plan", {}).get("textures", [])) if enabled["textures"] else 0,
        "material_count": len(dry_run.get("material_binding_plan", {}).get("materials", [])) if enabled["materials"] else 0,
        "warning_count": len(_operator_messages(report, "warnings")),
        "error_count": 0,
        "policy_summary": " · ".join(policies),
    }


def _parent_issue(report, unreal):
    checked = report.get("package_acceptance", {})
    previously = checked.get("parent_material_validation", {})
    if previously.get("status") not in ("pass", "warning"):
        return ""
    plan = checked.get("material_binding_plan", {})
    if not plan.get("materials"):
        return ""
    fresh = UnrealMaterialAssetBootstrap(unreal_module=unreal).validate_parent_materials(plan)
    if fresh.get("status") in ("error", "failed") or fresh.get("missing_parent_materials"):
        return "目标工程的母材质已变化，请重新检查包体和材质。"
    return ""


@dataclass
class CheckedPackage:
    stamp: tuple
    sources: tuple
    binaries: tuple
    report: dict
    token: str = ""
    conflicts: dict = None


class GateWorkbench:
    """Keep one matching check per package and consume each confirmation once."""

    def __init__(self, flow=None):
        self.flow = flow or UnrealPackageAcceptanceFlow()
        self.checked = OrderedDict()

    def _remember(self, package, checked):
        self.checked[package] = checked
        self.checked.move_to_end(package)
        if len(self.checked) > 12:
            self.checked.popitem(last=False)

    def _read_report(self, package, report_path=None):
        selected = _canonical(report_path or self.flow._default_report_path(package))
        if not Path(selected).is_relative_to(package):
            return "", {}
        try:
            report = read_report(selected)
        except (OSError, ValueError):
            report = {}
        return selected, report if isinstance(report, dict) else {}

    def read_reports(self, package_dir, report_path=None, unreal_module=None):
        package = _canonical(package_dir)
        selected, report = self._read_report(package, report_path)
        unreal = unreal_module or get_unreal()
        receipt = {}
        try:
            manifest = find_latest_manifest(package)
            receipt = read_handoff(
                package, _project_identity(unreal), manifest, _hash_file(manifest) if manifest else "", unreal,
                legacy_report=report,
            )
        except (OSError, TypeError, ValueError, RuntimeError):
            pass
        return {
            "report_path": selected,
            "operator_warnings": _operator_messages(report, "warnings"),
            "operator_errors": _operator_messages(report, "errors"),
            "handoff_receipt": receipt,
        }

    def _check(self, package, key, options, inputs, timings, action):
        self.checked.pop(key, None)
        stamp, sources = inputs
        before = _timed(timings, "binary_fingerprint", _binary_fingerprint, sources)
        report = _timed(
            timings, "full_preflight",
            lambda: self.flow.run(package, import_options=options, command_args=["ue_gate_workbench", action, package]),
        )
        checked = CheckedPackage(stamp, sources, before, report)
        if _timed(timings, "fingerprint", _package_inputs, package, options)[0] != stamp:
            raise RuntimeError("检查期间包体文件发生变化，请重新检查。")
        self._remember(key, checked)
        # Include the components of the measured full-preflight wall time.
        timings.update({name: value for name, value in report.get("timings_ms", {}).items() if name != "flow"})
        return checked

    def execute(self, action, package_dir, import_options=None, confirmation_token="", unreal_module=None):
        started = time.perf_counter()
        timings = {}
        package = _canonical(package_dir)
        options = dict(import_options or {})
        unreal = unreal_module or get_unreal()
        error = ""
        confirmation = None
        report = {}
        receipt = None
        handoff_warning = ""
        try:
            project_file = _project_identity(unreal)
            key = (package, project_file)
            checked = self.checked.get(key)
            report = checked.report if checked else {}
            if action == "apply":
                if not checked or not confirmation_token or checked.token != confirmation_token:
                    raise RuntimeError("导入确认已失效，请重新检查并确认。")
                checked.token = ""
            inputs = _timed(timings, "fingerprint", _package_inputs, package, options)
            if action in ("check", "dry_run", "prepare"):
                cache_hit = bool(action != "check" and checked and inputs[0] == checked.stamp)
                if not cache_hit:
                    manifest, digest = inputs[0][:2]
                    path = handoff_path(package, project_file)
                    if path:
                        # A later preflight can replace the old flow report. Recover its confirmed write first.
                        legacy = self._read_report(package)[1] if not path.is_file() else None
                        try:
                            receipt = read_handoff(package, project_file, manifest, digest.hex(), unreal,
                                                   legacy_report=legacy, validate_assets=False)
                        except (OSError, TypeError, ValueError, RuntimeError):
                            receipt = {}
                    checked = self._check(package, key, options, inputs, timings, action)
                report = checked.report
                if action == "prepare" and report.get("gate_passed"):
                    checked.token = ""
                    checked.conflicts = _timed(timings, "target_conflicts", _live_conflicts, report, unreal)
                    confirmation = _confirmation_values(report)
                    target = confirmation["target_path"]
                    existing = checked.conflicts[target]
                    checked.token = uuid4().hex
                    confirmation.update(token=checked.token, existing_count=len(existing), existing_assets=list(existing))
                    confirmation["duplicate_hint"] = ("目标路径已有资产，将按下列策略处理同名项。"
                                                      if existing else "目标路径尚无现有资产。")
            elif action == "apply":
                cache_hit = True
                self.checked.pop(key, None)
                if inputs[0] != checked.stamp:
                    raise RuntimeError("包体文件或导入选项已变化，请重新检查并确认。")
                current = _timed(timings, "binary_fingerprint", _binary_fingerprint, checked.sources)
                if current != checked.binaries:
                    raise RuntimeError("FBX 或贴图内容已变化，请重新检查并确认。")
                live = _timed(timings, "target_conflicts", _live_conflicts, report, unreal)
                if live != checked.conflicts:
                    raise RuntimeError("目标路径中的资产已变化，请重新确认。")
                problem = _timed(timings, "parent_materials", _parent_issue, report, unreal)
                if problem:
                    raise RuntimeError(problem)
                if _timed(timings, "fingerprint", _package_inputs, package, options)[0] != checked.stamp:
                    raise RuntimeError("确认期间包体文件发生变化，请重新检查。")
                timings["confirm_revalidation"] = round((time.perf_counter() - started) * 1000.0, 2)
                receipt = {}
                try:
                    invalidate_handoff(package, project_file)
                except OSError:
                    handoff_warning = "无法更新本地入库回执，请确认该工程的 Saved 目录可以写入。"
                report = _timed(
                    timings, "write_and_verify",
                    lambda: self.flow.run_checked_import(
                        package, checked.report, options, project_file=project_file, timings_ms=timings,
                        command_args=["ue_gate_workbench", "apply", package],
                    ),
                )
                timings.update(report.get("timings_ms", {}))
                manifest, digest = checked.stamp[:2]
                try:
                    receipt = _timed(timings, "handoff_receipt", save_handoff, report, package, project_file,
                                     manifest, digest.hex(), unreal)
                except (OSError, TypeError, ValueError, RuntimeError):
                    handoff_warning = "无法保存本地入库回执，请确认该工程的 Saved 目录可以写入。"
            else:
                raise ValueError("未知的门禁工作台操作。")
        except (OSError, TypeError, ValueError, RuntimeError, KeyError) as exc:
            error = str(exc)
            cache_hit = False
        timings["total"] = round((time.perf_counter() - started) * 1000.0, 2)
        passed = bool(not error and report.get("gate_passed"))
        result = dict(report)
        result.update(
            cache_hit=cache_hit, timings_ms=timings, gate_passed=passed, can_import=passed,
            import_succeeded=bool(action == "apply" and passed and report.get("import", {}).get("status") == "success"),
            operator_warnings=_operator_messages(report, "warnings"),
            operator_errors=[localized_message(error, severity="error")] if error else _operator_messages(report, "errors"),
        )
        if receipt is not None:
            result["handoff_receipt"] = receipt
        if handoff_warning:
            result["operator_warnings"].append(handoff_warning)
        if error:
            summary = create_acceptance_summary("error", [], [{"message": error}], "重新检查包体并确认。")
            attach_acceptance_summary(result, summary)
            result.update(status="error", message=result["operator_errors"][0], run_import=False,
                          gate_status="failed", blocking_reasons=[error])
        if confirmation:
            result["confirmation"] = confirmation
        if not error:
            if action == "apply":
                result["message"] = "导入完成。" if result["import_succeeded"] else "导入未通过验收，请查看报告。"
            elif confirmation:
                result["message"] = "已核对目标，等待确认写入。"
            elif not passed:
                result["message"] = "包体未放行，请处理阻断项。"
            elif action == "dry_run":
                result["message"] = "不写入验证完成，请核对导入计划。"
            elif result["operator_warnings"]:
                result["message"] = "检查完成，可导入。请核对非阻断提醒。"
            else:
                result["message"] = "检查完成，当前包体可以导入。"
        return result
