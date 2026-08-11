# -*- coding: utf-8 -*-
"""Local operation logging for Maya-side DCC AssetForge actions."""

from __future__ import absolute_import

import datetime
import io
import json
import os
from collections import deque

from asset_forge.shared.path_utils import normalize_path


LOG_ROOT_ENV = "ASSET_FORGE_LOG_ROOT"
LATEST_LOG_ENTRY_LIMIT = 200

try:
    text_type = unicode
    binary_type = str
except NameError:
    text_type = str
    binary_type = bytes


def repo_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))


def log_root(root=None):
    return os.path.abspath(root or os.environ.get(LOG_ROOT_ENV) or repo_root())


def logs_dir(root=None):
    return os.path.join(log_root(root), "AssetForgeReports", "logs")


def latest_log_path(root=None):
    return normalize_path(os.path.join(logs_dir(root), "latest_maya.log"))


def read_latest_log_tail(root=None, max_entries=30):
    """Return the newest Maya operation entries without rewriting the latest log."""
    return read_jsonl_tail(latest_log_path(root), max_entries)


def latest_log_summary(root=None, max_entries=10):
    entries = read_latest_log_tail(root, max_entries)
    return [_entry_summary(entry) for entry in entries]


class MayaOperationLogger(object):
    """Write daily jsonl logs plus a latest log mirror for user feedback."""

    def __init__(self, root=None):
        self.root = log_root(root)
        self.log_dir = logs_dir(self.root)

    def log(self, operation, status, inputs=None, outputs=None, errors=None, warnings=None, report_path=""):
        if not os.path.isdir(self.log_dir):
            os.makedirs(self.log_dir)
        timestamp = datetime.datetime.now().replace(microsecond=0).isoformat()
        entry = {
            "timestamp": timestamp,
            "operation": operation,
            "status": status,
            "inputs": normalize_log_value(inputs or {}),
            "outputs": normalize_log_value(outputs or {}),
            "errors": normalize_log_value(list(errors or [])),
            "warnings": normalize_log_value(list(warnings or [])),
            "report_path": normalize_path(report_path or ""),
        }
        line = json.dumps(entry, ensure_ascii=False, sort_keys=True)
        dated_path = os.path.join(self.log_dir, "asset_forge_maya_{0}.jsonl".format(timestamp[:10].replace("-", "")))
        with io.open(dated_path, "a", encoding="utf-8") as stream:
            stream.write(line + "\n")
        latest = latest_log_path(self.root)
        write_jsonl_tail_mirror(dated_path, latest, LATEST_LOG_ENTRY_LIMIT)
        entry["log_path"] = normalize_path(latest)
        return entry


def normalize_log_value(value):
    if isinstance(value, dict):
        return dict((normalize_log_value(key), normalize_log_value(item)) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return [normalize_log_value(item) for item in value]
    if isinstance(value, binary_type) and not isinstance(value, text_type):
        for encoding in ("utf-8", "mbcs"):
            try:
                return value.decode(encoding)
            except Exception:
                pass
        return value.decode("utf-8", "replace")
    if isinstance(value, text_type):
        return repair_mojibake(value)
    return value


def read_jsonl_tail(path, max_entries=30):
    if not path or not os.path.exists(path):
        return []
    try:
        with io.open(path, "r", encoding="utf-8") as stream:
            lines = list(deque((line for line in stream if line.strip()), maxlen=int(max_entries or 30)))
    except IOError:
        return []
    entries = []
    for line in lines[-int(max_entries or 30) :]:
        try:
            entries.append(json.loads(line))
        except ValueError:
            entries.append({"raw": line.strip()})
    return entries


def write_jsonl_tail_mirror(source_path, mirror_path, max_entries=LATEST_LOG_ENTRY_LIMIT):
    lines = []
    if os.path.exists(source_path):
        with io.open(source_path, "r", encoding="utf-8") as stream:
            lines = list(deque((line for line in stream if line.strip()), maxlen=int(max_entries or LATEST_LOG_ENTRY_LIMIT)))
    with io.open(mirror_path, "w", encoding="utf-8") as stream:
        for line in lines:
            stream.write(line if line.endswith("\n") else line + "\n")


def _entry_summary(entry):
    outputs = entry.get("outputs", {}) if isinstance(entry, dict) else {}
    details = []
    if outputs.get("asset_name"):
        details.append("asset={0}".format(outputs.get("asset_name")))
    if outputs.get("matched_count") is not None:
        details.append("matched={0}".format(outputs.get("matched_count")))
    if entry.get("report_path"):
        details.append("report={0}".format(entry.get("report_path")))
    if entry.get("errors"):
        details.append("error={0}".format(entry.get("errors")[0]))
    return {
        "timestamp": entry.get("timestamp", ""),
        "operation": entry.get("operation", ""),
        "status": entry.get("status", ""),
        "details": details,
    }


def repair_mojibake(value):
    """Repair common UTF-8-as-GBK mojibake seen in Maya console paths."""
    if not isinstance(value, text_type):
        return value
    markers = [
        u"\u5a34",
        u"\u5b2d",
        u"\u762f",
        u"\u6fee",
        u"\u9426",
        u"\u95b8",
        u"\u9420",
        u"\u95b9",
        u"\u940e",
    ]
    if not any(marker in value for marker in markers):
        return value
    try:
        repaired = value.encode("gbk").decode("utf-8")
    except Exception:
        return value
    return repaired or value
