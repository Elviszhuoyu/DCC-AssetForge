"""State of the native Slate workbench for Content Browser asset reviews."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from asset_forge.shared.material_profile_schema import material_profile_names
from asset_forge.shared.rules_schema import get_project_rules
from asset_forge.unreal import review_annotations
from asset_forge.unreal.asset_review import _policy, apply_fixes, scan_assets
from asset_forge.unreal.asset_review_host import package_path
from asset_forge.unreal.review_editor import history_directory, locate_issue, selected_paths
from asset_forge.unreal.review_history import record_review
from asset_forge.unreal.review_diagnostics import ACTIONS, issue_diagnostic
from asset_forge.unreal.unreal_bridge import get_unreal


_LABELS = {"pass": "通过", "blocked": "退回", "fixable": "可修", "needs_review": "待核实"}
_DIFF = {"resolved": "已解决", "persisting": "仍存在", "new": "新增", "unverified": "待核实"}
_PLATFORMS = {"pc": "PC", "high_end_mobile": "高端移动端", "mobile": "移动端"}


def _status(row):
    if row["status"] == "pass" and row.get("incomplete"):
        return "needs_review"
    return "fixable" if row.get("fully_fixable") else row["status"]


def _value(value):
    if value is None:
        return "未能读取"
    if isinstance(value, bool):
        return "开启" if value else "关闭"
    if value == "":
        return "空"
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _local_stamp(stamp, compact=False):
    if not isinstance(stamp, str) or not stamp:
        return ""
    try:
        moment = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if len(stamp) == 10:
        return moment.strftime("%m-%d" if compact else "%Y-%m-%d")
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone().strftime("%m-%d %H:%M" if compact else "%Y-%m-%d %H:%M")


def _batch_summary(report):
    fields = ["{} 件资产".format(len(report["assets"])), "第 {} 轮".format(report["revision"])]
    stamp = _local_stamp(report.get("created_at_utc"), compact=True)
    if stamp:
        fields.append(stamp)
    return "  ·  ".join(fields)


def _scan_dates(directory, report):
    """A partial recheck updates the date of the scanned assets only."""
    missing = {row["asset_path"] for row in report["assets"]}
    dates = {}
    for revision in range(report["revision"], 0, -1):
        if revision == report["revision"]:
            current = report
        else:
            try:
                current = json.loads((directory / "r{:04d}".format(revision) / "review.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(current, dict) or current.get("review_id") != report["review_id"] or current.get("revision") != revision:
                continue
        scanned = current.get("scanned_paths", [])
        if revision == 1 and "scanned_paths" not in current:
            old_rows = current.get("assets")
            scanned = [row.get("asset_path") for row in old_rows if isinstance(row, dict)] if isinstance(old_rows, list) else []
        if not isinstance(scanned, list):
            continue
        for path in missing.intersection(path for path in scanned if isinstance(path, str)):
            dates[path] = _local_stamp(current.get("created_at_utc"))
            missing.remove(path)
        if not missing:
            break
    return dates


def _asset_directory(ue, asset_path):
    # /Game is the common case and can be resolved without loading the asset.
    try:
        if asset_path.startswith("/Game/"):
            content = Path(ue.Paths.convert_relative_path_to_full(ue.Paths.project_content_dir()))
            local = content / (asset_path[len("/Game/"):] + ".uasset")
            if local.is_file():
                return str(local.parent)
        asset = ue.EditorAssetLibrary.load_asset(asset_path)
        filename = ue.SystemLibrary.get_system_path(asset) if asset else ""
        if filename and Path(filename).is_file():
            return str(Path(filename).parent)
    except (OSError, AttributeError, RuntimeError):
        pass
    return ""


def _preview_feedback(plans):
    if not plans:
        return "当前没有可修复的贴图设置。"
    eligible = sum(bool(plan["can_apply"]) for plan in plans)
    if eligible == len(plans):
        return "请核对旧值、目标值及受影响引用后确认。"
    if eligible:
        return "本次可修改 {} / {} 张贴图。请核对可修改项的旧值、目标值及受影响引用后确认。".format(eligible, len(plans))
    reasons = "；".join(dict.fromkeys(reason for plan in plans for reason in plan["reason"].split("；") if reason))
    if "尚未保存的包" in reasons or "尚未登记到磁盘包" in reasons:
        next_step = "请保存相关改动后，重新预览修复影响。"
    elif "注册表尚未完成全项目扫描" in reasons:
        next_step = "请等待资产注册表完成扫描，然后重新预览修复影响。"
    else:
        next_step = "请人工核对贴图属性与引用范围，处理后重新预览修复影响。"
    return "当前无法自动修改。{}{}".format(reasons + "。" if reasons else "", next_step)


def _current_reading(issue):
    actual = issue.get("actual")
    if issue["rule_id"] == "texture.srgb" and isinstance(actual, bool):
        return "当前{} sRGB".format(_value(actual))
    if issue["rule_id"] == "mesh.slot_material" and actual in ("", []):
        return "当前未绑定材质"
    return "当前 " + _value(actual)


def _rounds(root):
    """Discover the actual most recent round at its current project-relative location."""
    latest = []
    for batch in root.glob("*"):
        paths = [p for p in batch.glob("r[0-9]*/review.json") if p.parent.name[1:].isdigit()]
        if not paths:
            continue
        path = max(paths, key=lambda p: int(p.parent.name[1:]))
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
            if report.get("schema") != "asset_forge.asset_review.v1" or report.get("review_id") != batch.name:
                continue
            report["json_path"] = str(path.resolve())
            report["html_path"] = str(path.with_name("index.html").resolve())
            latest.append(report)
        except (OSError, ValueError):
            continue
    return sorted(latest, key=lambda r: r.get("created_at_utc") or "", reverse=True)


class ReviewWorkbench:
    def __init__(self, ue, history_dir):
        self.ue = ue
        self.root = Path(history_dir)
        self.batches = []
        self.report = None
        self.selected = None
        self.preview = None
        self.message = ""
        self.import_receipt = None
        self.import_batch = None
        self.metadata = review_annotations.empty()
        self.metadata_error = ""
        self.asset_dirs = {}
        self.scan_dates = {}
        rules = get_project_rules()["static_prop"]
        self.platforms = [key for key, limit in rules["max_triangles"].items()
                          if limit is not None and rules["max_material_slots"].get(key) is not None]
        self.profiles = material_profile_names()
        self.stock_policy, _ = _policy(None)

    def _set_report(self, report, preferred=None):
        directory = (self.root / report["review_id"]).resolve()
        if directory.parent != self.root.resolve() or directory.name != report["review_id"]:
            raise ValueError("批次目录无效。")
        self.batch_dir = directory
        self.report = report
        self.scan_dates = _scan_dates(directory, report)
        self.asset_dirs = {}
        self.metadata_error = ""
        try:
            self.metadata = review_annotations.load(directory)
        except (OSError, ValueError) as exc:
            self.metadata = review_annotations.empty()
            self.metadata_error = str(exc)
        paths = [row["asset_path"] for row in report["assets"]]
        self.selected = preferred if preferred in paths else next(iter(paths), None)
        self.preview = None

    def _selected_row(self):
        if self.report:
            return next((row for row in self.report["assets"] if row["asset_path"] == self.selected), None)
        return None

    def _check_latest(self):
        latest = next((r for r in _rounds(self.root) if r["review_id"] == self.report["review_id"]), None)
        if not latest:
            self.preview = None
            raise ValueError("当前批次已移出项目。请从批次记录重选。")
        if latest["revision"] != self.report["revision"]:
            self._set_report(latest, self.selected)
            raise ValueError("该批次已有新一轮结果，已刷新。请重新核对当前资产。")

    def _apply_batch_budget(self, argument):
        if not self.report:
            raise ValueError("请先打开要调整预算的批次。")
        configured = json.loads(argument)
        fields = {"triangles": "max_triangles", "material_slots": "max_material_slots"}
        if not isinstance(configured, dict) or any(
            type(configured.get(key)) is not int or not 0 < configured[key] <= 2147483647 for key in fields
        ):
            raise ValueError("三角面与材质槽预算必须是大于 0 的整数。")
        self._check_latest()
        policy = dict(self.report["policy"])
        if all(configured[key] == policy.get(field) for key, field in fields.items()):
            return
        policy.update((field, configured[key]) for key, field in fields.items())
        if {key: configured[key] for key in fields} == policy.get("asset_budgets"):
            policy.pop("manual_budget", None)
        else:
            policy["manual_budget"] = True
        paths = [row["asset_path"] for row in self.report["assets"]]
        result = scan_assets(paths, policy, self.ue)
        saved = record_review(result, self.root, previous=self.report["json_path"], allow_budget_change=True)
        self._set_report(saved, self.selected)
        self.message = "已更新预算并复验本批次，原批审记录已保留。"

    def act(self, action, argument=""):
        if action == "rules_batch_budget":
            self._apply_batch_budget(argument)
            return
        budget_keys = {"rules_triangles": "max_triangles", "rules_material_slots": "max_material_slots"}
        if action in budget_keys:
            value = argument.strip()
            if not value.isdecimal() or int(value) <= 0:
                raise ValueError("预算必须是大于 0 的整数。")
            policy = dict(self.stock_policy)
            policy[budget_keys[action]] = int(value)
            self.stock_policy, _ = _policy(policy)
            self.message = "已更新下次存量检查的预算。"
            return
        if action in ("rules_platform", "rules_profile"):
            platform = action == "rules_platform"
            if argument not in (self.platforms if platform else self.profiles):
                raise ValueError("选定规则已不可用。")
            keys = ("platform", "material_profile")
            options = {name: self.stock_policy[name] for name in keys}
            options[keys[0] if platform else keys[1]] = argument
            if not platform or argument == self.stock_policy["platform"]:
                options.update(max_triangles=self.stock_policy["max_triangles"],
                               max_material_slots=self.stock_policy["max_material_slots"])
            self.stock_policy, _ = _policy(options)
            self.message = "已更新下次存量检查的规则。"
            return
        if action in ("open", "history", "batch"):
            self.batches = _rounds(self.root)
            if action == "batch":
                target = next((r for r in self.batches if r["review_id"] == argument), None)
                if target is None:
                    raise ValueError("找不到该批次，请刷新记录。")
                self._set_report(target, self.selected)
                self.message = "已打开选定批次。"
            elif action == "open" and self.batches:
                self._set_report(self.batches[0], self.selected)
                self.message = "已恢复最近一次审核。"
            return
        if action in ("scan", "folders", "imported"):
            if action == "imported":
                handoff = json.loads(argument)
                if not isinstance(handoff, dict) or not isinstance(handoff.get("receipt"), str) or not handoff["receipt"]:
                    raise ValueError("本次导入缺少有效回执。")
                paths = handoff.get("meshes")
                if not isinstance(paths, list) or not paths or not all(
                        isinstance(p, str) and p.startswith("/") and p.rsplit("/", 1)[-1] for p in paths):
                    raise ValueError("本次导入没有返回可批审的网格路径。")
                paths = list(dict.fromkeys(package_path(p) for p in paths))
                if handoff["receipt"] == self.import_receipt:
                    if not self.report or self.report["review_id"] != self.import_batch:
                        self.act("batch", self.import_batch)
                        self.act("select", paths[0])
                    return
            else:
                paths = selected_paths(self.ue, action == "folders")
            scan_options = {"unreal_module": self.ue}
            if action != "imported":
                scan_options["policy"] = self.stock_policy
            else:
                policy = handoff.get("policy")
                if policy is not None and not isinstance(policy, dict):
                    raise ValueError("本次导入未返回有效的材质规则。")
                policy = dict(policy or {})
                if "asset_budgets" in handoff:
                    policy["asset_budgets"] = handoff["asset_budgets"]
                if policy:
                    scan_options["policy"] = policy
            result = record_review(scan_assets(paths, **scan_options), self.root)
            self._set_report(result, paths[0])
            if action == "imported":
                self.import_receipt, self.import_batch = handoff["receipt"], result["review_id"]
            self.message = "首轮体检完成。原始返修单已保存。"
            return
        if not self.report:
            raise ValueError("请先检查内容浏览器选区或打开已有批次。")
        if action in review_annotations.ACTIONS:
            paths = {row["asset_path"] for row in self.report["assets"]}
            try:
                self.metadata = review_annotations.update(self.batch_dir, action, argument, paths)
            except ValueError:
                # Refresh the form choices after a conflicting edit in another editor.
                self.metadata = review_annotations.load(self.batch_dir)
                raise
            self.metadata_error = ""
            self.message = ""
            return
        if action in ("report", "open_report"):
            html = self._report_file()
            if not html.is_file():
                raise ValueError("当前轮次的 HTML 返修单不存在。")
            os.startfile(str(html))
            return
        if action == "select":
            if not any(row["asset_path"] == argument for row in self.report["assets"]):
                raise ValueError("此资产不属于当前批次。")
            if self.selected != argument:
                self.preview = None
            self.selected = argument
            self.message = ""
            return
        row = self._selected_row()
        if row is None:
            raise ValueError("请先从左侧选择资产。")
        if action in ("locate", "open_issue"):
            if not argument.isdecimal() or int(argument) >= len(row["issues"]):
                raise ValueError("问题已更新，请重新选择。")
            issue = row["issues"][int(argument)]
            if action == "locate":
                path = locate_issue(self.ue, issue)
                self.message = "内容浏览器已定位  " + path
            else:
                if not issue_diagnostic(issue)["action_kind"].startswith("open_"):
                    raise ValueError("此问题不对应可直接打开的资产。")
                asset = self.ue.EditorAssetLibrary.load_asset(issue["object_path"])
                editor = self.ue.get_editor_subsystem(self.ue.AssetEditorSubsystem)
                if asset is None or editor is None or not editor.open_editor_for_assets([asset]):
                    raise ValueError("未能打开资产编辑器，请在内容浏览器核对该资产。")
                self.message = "已打开资产编辑器。修改并保存后可返回复验。"
            return
        if action == "cancel":
            self.preview = None
            self.message = "已取消，本次未写入。"
            return
        self._check_latest()
        if action in ("recheck", "preview"):
            scan = scan_assets([self.selected], self.report["policy"], self.ue)
            if action == "preview":
                self.preview = scan
                self.message = _preview_feedback(scan["fix_plan"])
                return
            saved = record_review(scan, self.root, previous=self.report["json_path"])
            self._set_report(saved, self.selected)
            self.message = "已复验当前资产，其余资产保留上轮结果。"
            return
        if action == "apply":
            preview, self.preview = self.preview, None
            if preview is None or preview["asset_paths"] != [self.selected]:
                raise ValueError("请先预览当前资产的修复影响。")
            approved = [item["texture_path"] for item in preview["fix_plan"] if item["can_apply"]]
            if not approved:
                raise ValueError("没有已确认范围的安全修改。")
            result = apply_fixes(preview, approved, self.ue)
            saved = record_review(result["review"], self.root, previous=self.report["json_path"])
            self._set_report(saved, self.selected)
            notes = [c["reason"] for c in result["changes"] if c["status"] != "saved"]
            self.message = "已保存 {} 张贴图，当前资产已复扫。{}".format(result["changed_count"], " ".join(notes))
            return
        raise ValueError("无法识别的批审动作。")

    def _report_file(self):
        return self.batch_dir / "r{:04d}".format(self.report["revision"]) / "index.html"

    def view(self):
        report = self.report
        stock = self.stock_policy
        stock_policy = {
            "platform": stock["platform"], "profile": stock["material_profile"],
            "triangles": stock["max_triangles"], "material_slots": stock["max_material_slots"],
            "platforms": [{"id": key, "label": _PLATFORMS.get(key, key)} for key in self.platforms],
            "profiles": [{"id": name, "label": name} for name in self.profiles],
            "limits": "{} · LOD0 上限 {:,} 三角面 · 材质槽上限 {}".format(
                _PLATFORMS.get(stock["platform"], stock["platform"]), stock["max_triangles"], stock["max_material_slots"]),
        }
        view = {"stock_policy": stock_policy, "batches": [{"id": r["review_id"], "label": "{}  ·  {}".format(
            _batch_summary(r), r["review_id"][:8])}
                            for r in self.batches],
                "assets": [], "batch_id": report["review_id"] if report else "", "summary": "批次资产", "selected": self.selected or "",
                "name": "", "issues": [], "passed": [], "plans": [], "changes": [], "fix": "",
                "groups": self.metadata["groups"], "tags": self.metadata["tags"], "can_report": False,
                "path": "", "source_dir": "", "source_kind": "本地资产目录", "updated_kind": "最近扫描",
                "updated_at": "", "profile": "", "message": "  ".join(dict.fromkeys(filter(None, (self.message, self.metadata_error))))}
        if not report:
            return view
        rows = report["assets"]
        view["summary"] = _batch_summary(report)
        report_policy = report.get("policy") or {}
        profile = report_policy.get("material_profile")
        platform = report_policy.get("platform")
        view["platform"] = _PLATFORMS.get(platform, platform) if isinstance(platform, str) else ""
        view["can_report"] = self._report_file().is_file()
        view["profile"] = profile if isinstance(profile, str) else ""
        triangles = report_policy.get("max_triangles")
        slots = report_policy.get("max_material_slots")
        if type(triangles) is int and type(slots) is int:
            view["batch_budget"] = {"triangles": triangles, "material_slots": slots}
            view["budget_summary"] = "{:,} 三角面 / {} 个材质槽".format(triangles, slots)
            if report_policy.get("manual_budget"):
                view["budget_source"] = "手动调整"
            else:
                view["budget_source"] = "包体声明" if report_policy.get("asset_budgets") else "批审规则"
        annotations = self.metadata["assets"]
        view["assets"] = [{"path": r["asset_path"], "name": r["asset_path"].rsplit("/", 1)[-1],
                           "profile": view["profile"],
                           "group": annotations.get(r["asset_path"], {}).get("group", ""),
                           "tags": annotations.get(r["asset_path"], {}).get("tags", []),
                           "status": _status(r), "label": "{}   ·   {} 项问题".format(
                               _LABELS[_status(r)], len(r["issues"]))} for r in rows]
        row = self._selected_row()
        if not row:
            return view
        if self.selected not in self.asset_dirs:
            self.asset_dirs[self.selected] = _asset_directory(self.ue, self.selected)
        view.update(path=self.selected, source_dir=self.asset_dirs[self.selected],
                    updated_at=self.scan_dates.get(self.selected, ""))
        facts = row["facts"]
        view["name"] = self.selected.rsplit("/", 1)[-1]
        status = _status(row)
        counts = {severity: sum(issue.get("severity") == severity for issue in row["issues"])
                  for severity in ("error", "warning", "unknown")}
        active_count = counts.get({"fixable": "error", "blocked": "error", "needs_review": "unknown"}.get(status), 0)
        caption = _LABELS[status]
        if active_count:
            suffix = "{} 项待核实" if status == "needs_review" else "{} 项阻断"
            caption = "可修（{}）".format(suffix.format(active_count)) if status == "fixable" else suffix.format(active_count)
        view["facts"] = "   ·   ".join([caption, row["asset_type"]]
                                      + (["{:,} 三角面".format(facts["lod0_triangles"])]
                                         if isinstance(facts.get("lod0_triangles"), int) else [])
                                      + (["{} 个材质槽".format(len(facts["slots"]))] if facts.get("slots") is not None else []))
        view["empty_label"] = ("检查通过，无待处理问题" if row["status"] == "pass" and not row.get("incomplete")
                               else "检查结果尚未放行，请核实资产或重新检查")
        view["passed"] = row.get("passed", [])
        view["has_pass_evidence"] = "passed" in row
        for number, issue in enumerate(row["issues"]):
            diagnosis = issue_diagnostic(issue)
            action = diagnosis["action_kind"]
            view["issues"].append(dict(diagnosis, index=str(number), path=issue["object_path"],
                                       slot=str(issue.get("slot", "")), current=_current_reading(issue),
                                       action_label=ACTIONS[action]))
        if self.preview is None:
            if any(i["action_kind"] == "preview_fix" for i in view["issues"]):
                view["fix"] = "preview"
        else:
            for item in self.preview["fix_plan"]:
                old, new = item["old"], item["new"]
                view["plans"].append({"name": "修复影响  ·  " + item["texture_path"].rsplit("/", 1)[-1],
                                      "body": "sRGB  {} → {}     压缩  {} → {}\n纹理   {}\n引用   {}\n网格   {}{}".format(
                                          _value(old["srgb"]), _value(new["srgb"]), old["compression"], new["compression"],
                                          item["texture_path"], "\n        ".join(item["referencers"]) or "无",
                                          "\n        ".join(item["mesh_owners"]) or "无", "" if item["can_apply"] else "\n" + item["reason"])})
            if self.preview["fix_plan"]:
                view["fix"] = "confirm" if any(item["can_apply"] for item in self.preview["fix_plan"]) else "preview"
        if report["revision"] > 1:
            for kind, name in _DIFF.items():
                for change in report.get("changes_since_first", {}).get(kind, []):
                    if change["asset_path"] == self.selected:
                        issue = change["after"] or change["before"]
                        view["changes"].append({"text": "与首轮对照   {}   ·   {}   ·   {}".format(
                            name, issue_diagnostic(issue)["title"], issue.get("slot") or issue["object_path"].rsplit("/", 1)[-1])})
        return view


_session = None


def slate_dispatch(action, argument):
    global _session
    if _session is None:
        ue = get_unreal()
        _session = ReviewWorkbench(ue, history_directory(ue))
    try:
        _session.act(action, argument)
    except (OSError, RuntimeError, ValueError) as exc:
        _session.message = str(exc)
    return json.dumps(_session.view(), ensure_ascii=True, separators=(",", ":"))
