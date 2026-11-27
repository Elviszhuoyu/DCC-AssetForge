"""Immutable review rounds and offline HTML work orders for content-browser audits."""
import json
import os
from html import escape
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from asset_forge.shared.report_artifacts import utc_now


_STATUS = {"pass": "通过", "blocked": "退回", "needs_review": "待核实"}
_CHANGES = {"resolved": "已解决", "persisting": "仍存在", "new": "新增"}
_SCHEMA = "asset_forge.asset_review.v1"


def _issue_index(rows, include_unconfirmed=False):
    index = {}
    for asset in rows:
        issues = asset["issues"] + (asset.get("unconfirmed_issues", []) if include_unconfirmed else [])
        for issue in issues:
            key = (asset["asset_path"], issue["rule_id"], issue["object_path"],
                   str(issue.get("slot", "")), str(issue.get("subkey", "")))
            if key in index:
                raise ValueError("Duplicate issue identity: {}".format(key))
            index[key] = issue
    return index


def _compare(old_rows, new_rows, scanned):
    old, new = _issue_index(old_rows, include_unconfirmed=True), _issue_index(new_rows)
    incomplete = {row["asset_path"] for row in new_rows if row.get("incomplete")}
    changed = {key: [] for key in ("resolved", "persisting", "new", "unverified")}
    for key in sorted(old.keys() | new.keys()):
        if key[0] not in scanned:
            continue
        if key not in new:
            state = "unverified" if key[0] in incomplete else "resolved"
        elif key in old:
            state = "persisting"
        else:
            state = "new"
        changed[state].append({"asset_path": key[0], "before": old.get(key), "after": new.get(key)})
    return changed


def _text(value):
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return escape(str(value)) if value is not None else "—"


def _table(headings, rows):
    headings = "".join("<th>{}</th>".format(h) for h in headings)
    body = "".join("<tr>{}</tr>".format("".join("<td>{}</td>".format(_text(c)) for c in row)) for row in rows)
    return '<div class="table"><table><thead><tr>{}</tr></thead><tbody>{}</tbody></table></div>'.format(headings, body)


def _differences(title, changes):
    sections = ["<h2>{}</h2>".format(title)]
    for kind, label in list(_CHANGES.items()) + [("unverified", "本轮无法核实")]:
        entries = changes[kind]
        if kind == "unverified" and not entries:
            continue
        sections.append("<h3>{} · {}</h3>".format(label, len(entries)))
        if entries:
            rows = []
            for entry in entries:
                before, after = entry["before"], entry["after"]
                issue = after or before
                rows.append((entry["asset_path"], issue["rule_id"], issue["object_path"], issue.get("slot"),
                             before.get("actual") if before else None, after.get("actual") if after else None,
                             issue.get("expected"), issue.get("suggestion")))
            sections.append(_table(("资产", "规则", "问题对象", "槽", "此前实测", "当前实测", "期望", "处理建议"), rows))
    return "".join(sections)


def _html(report):
    seq = report["revision"]
    parts = ['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
             '<title>资产返修单 · 第 {} 轮</title>'.format(seq),
             '<style>*{box-sizing:border-box}body{font:15px/1.55 "Microsoft YaHei",sans-serif;color:#242e32;background:#fafaf8;margin:24px auto;max-width:1440px;padding:0 18px}h1{font-size:30px}h2{margin:26px 0 8px}h3{font-size:16px}.table{overflow-x:auto}table{border-collapse:collapse;width:100%;background:white}th,td{border-bottom:1px solid #d4d9d6;text-align:left;padding:7px 9px;vertical-align:top;overflow-wrap:anywhere}th{background:#e7ece9}p{color:#465451}a{color:#165c50}code{overflow-wrap:anywhere}</style>',
             '<h1>资产返修单 · 第 {} 轮</h1>'.format(seq),
             '<p>批次 <code>{}</code>　{} UTC</p>'.format(_text(report["review_id"]), _text(report["created_at_utc"]))]
    if seq > 1:
        links = '<a href="../r0001/index.html">打开首轮返修单</a>'
        if seq > 2:
            links += '　<a href="../r{:04d}/index.html">打开上一轮</a>'.format(seq - 1)
        parts.append("<p>{}</p>".format(links))
    parts.append(_table(("受审资产", "结论", "本轮检查", "问题数", "读回指纹"), [
        (a["asset_path"], "待修 · 可安全修复" if a.get("fully_fixable") else _STATUS.get(a["status"], a["status"]),
         ("已检查" if seq == 1 else "已复查") if a["asset_path"] in report["scanned_paths"] else "沿用上一轮",
         len(a["issues"]), (a.get("revision") or "")[:12]) for a in report["assets"]]))
    if report["fix_plan"]:
        parts.append("<h2>本轮纹理修复预览</h2>")
        parts.append(_table(("纹理", "当前值", "目标值", "引用包", "受影响网格", "处理方式"), [
            (p["texture_path"], p["old"], p["new"], p["referencers"], p["mesh_owners"],
             "可在编辑器确认" if p["can_apply"] else p["reason"]) for p in report["fix_plan"]]))
    if seq > 1:
        parts.append(_differences("与上一轮相比", report["changes"]))
    if seq > 2:
        parts.append(_differences("与首轮相比（含各资产最近实测）", report["changes_since_first"]))
    parts.append("<h2>各资产最近一次实测的问题</h2>")
    issues = [(a["asset_path"], i["rule_id"], i["object_path"], i.get("slot"), i.get("actual"),
               i.get("expected"), i.get("suggestion"), i.get("owner"))
              for a in report["assets"] for i in a["issues"]]
    parts.append(_table(("资产", "规则", "对象", "槽", "实测", "期望", "建议", "处理方"), issues)
                 if issues else "<p>本批资产的最近一次检查均未报告问题。</p>")
    parts.append('<p><a href="review.json">完整实测数据</a></p></html>')
    return "\n".join(parts)


def record_review(scan, history_dir, previous=None, allow_budget_change=False):
    """Save a new batch or reconcile a rescan with the named immutable prior round."""
    rows = scan["assets"]
    scanned = {row["asset_path"] for row in rows}
    if not scanned or len(scanned) != len(rows):
        raise ValueError("Select at least one asset; asset paths must be unique")
    _issue_index(rows)
    root = Path(history_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    policy = scan.get("policy", {})
    if previous:
        prev_path = Path(previous).resolve()
        if prev_path.parent.parent.parent != root or prev_path.name != "review.json":
            raise ValueError("Select a previous review from this project's history")
        old = json.loads(prev_path.read_text(encoding="utf-8"))
        batch = prev_path.parent.parent
        if (old.get("schema") != _SCHEMA or old.get("review_id") != batch.name
                or prev_path.parent.name != "r{:04d}".format(old["revision"])):
            raise ValueError("Invalid previous review document")
        seq, prior = old["revision"] + 1, old["assets"]
        if old["policy"] != policy:
            budget_fields = {"max_triangles", "max_material_slots", "manual_budget"}
            changes = {key for key in old["policy"].keys() | policy.keys() if old["policy"].get(key) != policy.get(key)}
            if not allow_budget_change or not changes <= budget_fields or scanned != {row["asset_path"] for row in prior}:
                raise ValueError("The review policy changed; start a new batch")
        baseline = prior if seq == 2 else json.loads((batch / "r0001" / "review.json").read_text(encoding="utf-8"))["assets"]
    else:
        batch = root / uuid4().hex
        batch.mkdir()
        seq, prior, baseline = 1, [], []
    merged = {row["asset_path"]: row for row in prior}
    previous_issues = _issue_index(prior, include_unconfirmed=True)
    current_issues = _issue_index(rows)
    for row in rows:
        row = dict(row)
        if row.get("incomplete"):
            row["unconfirmed_issues"] = [issue for key, issue in previous_issues.items()
                                         if key[0] == row["asset_path"] and key not in current_issues]
        merged[row["asset_path"]] = row
    assets = [merged[path] for path in sorted(merged)]
    dest = batch / "r{:04d}".format(seq)
    if dest.exists():
        raise FileExistsError("This round already has a successor; load the latest round or start a new batch")
    report = {"schema": _SCHEMA, "review_id": batch.name, "revision": seq, "created_at_utc": utc_now(),
              "scanned_paths": sorted(scanned), "policy": policy, "assets": assets, "fix_plan": scan.get("fix_plan", []),
              "changes": _compare(prior, assets, scanned),
              "changes_since_first": _compare(baseline, assets, set(merged)),
              "json_path": str(dest / "review.json"), "html_path": str(dest / "index.html")}
    with TemporaryDirectory(prefix=".pending-", dir=str(batch)) as scratch:
        staged = Path(scratch) / "round"
        staged.mkdir()
        (staged / "index.html").write_text(_html(report), encoding="utf-8")
        (staged / "review.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        os.rename(str(staged), str(dest))
    return report
