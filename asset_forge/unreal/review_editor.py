# -*- coding: utf-8 -*-
"""Operate on the current Content Browser selection and its saved review history."""
import json
import os
from pathlib import Path

from asset_forge.unreal.asset_review import apply_fixes, scan_assets
from asset_forge.unreal.review_history import record_review
from asset_forge.unreal.unreal_bridge import get_unreal

ACTIONS = {
    "scan": "体检选中资产", "folders": "体检所选文件夹", "recheck": "复验选中资产",
    "fix": "预览并确认安全修复", "locate": "选择并定位问题对象", "report": "打开最近体检报告",
}


def selected_paths(ue, folders=False):
    utility = ue.EditorUtilityLibrary
    if folders:
        paths = utility.get_selected_folder_paths() or utility.get_selected_path_view_folder_paths()
        registry = ue.AssetRegistryHelpers.get_asset_registry()
        if registry.is_loading_assets():
            registry.wait_for_completion()
        entries = []
        for path in paths:
            path = str(path)
            if path.startswith("/All/"):
                item = ue.ContentBrowserItemPath()
                item.set_path(path, ue.ContentBrowserPathType.VIRTUAL)
                internal = str(item.get_internal_path())
                if internal in ("", "None") and (path == "/All/Game" or path.startswith("/All/Game/")):
                    internal = path[4:]
                path = internal
            if path in ("", "/", "/All", "None"):
                raise ValueError("请选择有实际包路径的资产文件夹。")
            entries.extend(registry.get_assets_by_path(path, recursive=True) or [])
    else:
        entries = utility.get_selected_asset_data()
    selected = sorted({str(entry.package_name) for entry in entries
                       if str(entry.asset_class_path.asset_name) in ("StaticMesh", "Texture2D")})
    if not selected:
        raise ValueError("选区中没有可体检的 Static Mesh 或 Texture2D。")
    return selected


def history_directory(ue):
    return Path(ue.Paths.convert_relative_path_to_full(ue.Paths.project_saved_dir())) / "AssetForge" / "Reviews"


def recent_review(history_dir, selected=(), choose_batch=None):
    selected = set(selected)
    matches = []
    for batch in Path(history_dir).glob("*"):
        path = max(batch.glob("r[0-9]*/review.json"), key=lambda p: int(p.parent.name[1:])
                   if p.parent.name[1:].isdigit() else -1, default=None)
        if not path:
            continue
        report = json.loads(path.read_text(encoding="utf-8"))
        if report["review_id"] == batch.name and selected.issubset(row["asset_path"] for row in report["assets"]):
            report["json_path"] = str(path.resolve())
            report["html_path"] = str(path.with_name("index.html").resolve())
            matches.append(report)
    if not matches:
        raise ValueError("请先为当前选区建立体检批次。")
    matches.sort(key=lambda item: item["created_at_utc"], reverse=True)
    if len(matches) == 1 or not selected:
        return matches[0]
    if choose_batch is None:
        raise ValueError("选区属于多个批次，请选择要继续的体检单。")
    chosen = choose_batch(matches)
    if chosen is not None and chosen not in matches:
        raise ValueError("所选批次不属于当前选区。")
    return chosen


def _choose_batch(ue, reports):
    for index, report in enumerate(reports, 1):
        text = "{} / {}\n批次：{}\n第 {} 轮　{}\n{}\n\n是：使用这张单　否：下一张　取消：结束".format(
            index, len(reports), report["review_id"], report["revision"], report["created_at_utc"],
            "\n".join(row["asset_path"] for row in report["assets"]))
        decision = ue.EditorDialog.show_message("选择要继续的体检批次", text, ue.AppMsgType.YES_NO_CANCEL)
        if decision == ue.AppReturnType.YES:
            return report
        if decision != ue.AppReturnType.NO:
            break
    return None


def locate_issue(ue, issue):
    path = issue["object_path"]
    if not ue.EditorAssetLibrary.does_asset_exist(path):
        raise ValueError("问题对象已不存在，请重新体检。")
    ue.EditorAssetLibrary.sync_browser_to_objects([path])
    return path


def _choose_issue(ue, issues):
    for index, item in enumerate(issues, 1):
        text = "{} / {}\n{}\n{}\n{}\n槽位：{}\n{}\n\n是：定位这项　否：下一项　取消：结束".format(
            index, len(issues), item["asset_path"], item["rule_id"], item["object_path"],
            item.get("slot", "—"), item["suggestion"])
        answer = ue.EditorDialog.show_message("选择并定位问题对象", text, ue.AppMsgType.YES_NO_CANCEL)
        if answer == ue.AppReturnType.YES:
            return item
        if answer != ue.AppReturnType.NO:
            break
    return None


def _fix_preview_text(plan):
    rows = []
    for item in plan:
        old, new = item["old"], item["new"]
        rows.append("{}\nsRGB {} → {}，压缩 {} → {}\n引用：{}\n网格：{}\n{}".format(
            item["texture_path"], old["srgb"], new["srgb"], old["compression"], new["compression"],
            ", ".join(item["referencers"]) or "无", ", ".join(item["mesh_owners"]) or "无",
            "可修复" if item["can_apply"] else "仅提示：" + item["reason"]))
    return "\n\n".join(rows)


def run_review_action(action, history_dir=None, policy=None, unreal_module=None, confirm=None, choose_issue=None, choose_batch=None):
    """Run a menu action against the live selection. Confirmation receives the complete displayed proposal."""
    ue = unreal_module or get_unreal()
    root = Path(history_dir) if history_dir else history_directory(ue)
    if action == "report":
        report = recent_review(root)
        os.startfile(report["html_path"])
        return {"status": "opened", "record": report}
    selected = selected_paths(ue, folders=action == "folders")
    if action in ("scan", "folders"):
        scan = scan_assets(selected, policy, ue)
        return {"status": "reviewed", "record": record_review(scan, root)}
    previous = recent_review(root, selected, choose_batch or (lambda items: _choose_batch(ue, items)))
    if previous is None:
        return {"status": "cancelled"}
    if action == "locate":
        issues = [issue for row in previous["assets"] if row["asset_path"] in selected for issue in row["issues"]]
        chosen = (choose_issue or (lambda items: _choose_issue(ue, items)))(issues) if issues else None
        if chosen is not None and chosen not in issues:
            raise ValueError("所选问题不在当前体检单中。")
        return {"status": "located" if chosen else ("cancelled" if issues else "no_issues"),
                "object_path": locate_issue(ue, chosen) if chosen else None}
    scan = scan_assets(selected, previous["policy"], ue)
    if action == "recheck":
        return {"status": "reviewed", "record": record_review(scan, root, previous=previous["json_path"])}
    if action != "fix":
        raise ValueError("未知体检操作。")
    plan = scan["fix_plan"]
    approved = [item["texture_path"] for item in plan if item["can_apply"]]
    text = _fix_preview_text(plan)
    if not approved:
        return {"status": "no_safe_fixes", "message": text or "所选资产没有可安全修复的问题。", "plan": plan}
    prompt = text + "\n\n确认保存上面可修复的贴图，并重新体检所选资产？"
    if confirm is None:
        accepted = ue.EditorDialog.show_message(ACTIONS[action], prompt, ue.AppMsgType.YES_NO,
                                                ue.AppReturnType.NO) == ue.AppReturnType.YES
    else:
        accepted = confirm(prompt)
    if not accepted:
        return {"status": "cancelled", "plan": plan}
    applied = apply_fixes(scan, approved, ue)
    record = record_review(applied["review"], root, previous=previous["json_path"])
    return {"status": "applied", "changed_count": applied["changed_count"], "changes": applied["changes"],
            "plan": plan, "record": record}


def menu_action(action):
    ue = get_unreal()
    try:
        result = run_review_action(action, unreal_module=ue)
        if result["status"] in ("opened", "located", "cancelled"):
            return
        if "record" in result:
            record = result["record"]
            counts = {}
            for row in record["assets"]:
                counts[row["status"]] = counts.get(row["status"], 0) + 1
            text = "第 {} 轮　通过 {}　退回 {}　待核 {}\n{}".format(
                record["revision"], counts.get("pass", 0), counts.get("blocked", 0),
                counts.get("needs_review", 0), record["html_path"])
            if "changes" in result:
                text += "\n" + "\n".join("{}：{}".format(row["texture_path"], row["reason"]) for row in result["changes"])
        else:
            text = result.get("message", "所选资产没有待定位的问题。")
    except (OSError, ValueError, RuntimeError) as exc:
        text = str(exc)
    ue.EditorDialog.show_message(ACTIONS[action], text, ue.AppMsgType.OK)


def register_review_menus(ue, menus, native_workbench=False):
    groups = (("ContentBrowser.AssetContextMenu", ("scan",) if native_workbench else ("scan", "recheck", "fix", "locate", "report")),
              ("ContentBrowser.FolderContextMenu", ("folders",)))
    if not native_workbench:
        groups += (("LevelEditor.MainMenu.Tools", tuple(ACTIONS)),)
    for name, actions in groups:
        menu = menus.extend_menu(name)
        if not menu or not hasattr(menu, "add_sub_menu"):
            continue
        sub = menu.add_sub_menu("AssetForge", "AssetForge", "AssetForgeAssetReview",
                                "DCC AssetForge 资产体检", "检查、定位和复验内容浏览器中的资产")
        for action in actions:
            entry = ue.ToolMenuEntry(name="AssetForge.Review." + action, type=ue.MultiBlockType.MENU_ENTRY)
            entry.set_label(ACTIONS[action])
            if native_workbench:
                command = "AssetForge.Review " + action
                entry.set_string_command(ue.ToolMenuStringCommandType.COMMAND, "", command)
            else:
                command = "from asset_forge.unreal.review_editor import menu_action; menu_action({!r})".format(action)
                entry.set_string_command(ue.ToolMenuStringCommandType.PYTHON, "", command)
            sub.add_menu_entry("Review", entry)
