# -*- coding: utf-8 -*-
"""Local operation logging for Unreal-side DCC AssetForge actions."""

from __future__ import absolute_import

import datetime
import io
import json
import os
import shutil

from asset_forge.shared.path_utils import normalize_path


LOG_ROOT_ENV = "ASSET_FORGE_LOG_ROOT"

# Keep these as code points so this source file never displays mojibake.
MOJIBAKE_MARKERS = tuple(
    chr(value)
    for value in [
        0x59DD,
        0x5A34,
        0x9365,
        0x74BA,
        0x93B5,
        0x7035,
        0x95C3,
        0x74A7,
        0x93C3,
        0x7D21,
    ]
)

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
    return normalize_path(os.path.join(logs_dir(root), "latest_unreal.log"))


def read_latest_log_tail(root=None, max_entries=30):
    """Return the newest Unreal operation entries without rewriting the latest log."""
    return read_jsonl_tail(latest_log_path(root), max_entries)


def latest_log_summary(root=None, max_entries=10):
    entries = read_latest_log_tail(root, max_entries)
    return [_entry_summary(entry) for entry in entries]


class UnrealOperationLogger(object):
    """Write daily Unreal jsonl logs plus a latest mirror."""

    def __init__(self, root=None):
        self.root = log_root(root)
        self.log_dir = logs_dir(self.root)

    def log(self, operation, status, inputs=None, outputs=None, errors=None, warnings=None, report_path=""):
        if not os.path.isdir(self.log_dir):
            os.makedirs(self.log_dir)
        timestamp = datetime.datetime.now().replace(microsecond=0).isoformat()
        latest = latest_log_path(self.root)
        entry = {
            "timestamp": timestamp,
            "source_app": "unreal",
            "source_dcc": "unreal",
            "operation": operation,
            "status": status,
            "inputs": normalize_log_value(inputs or {}),
            "outputs": normalize_log_value(outputs or {}),
            "errors": normalize_log_value(list(errors or [])),
            "warnings": normalize_log_value(list(warnings or [])),
            "report_path": normalize_path(report_path or ""),
            "log_path": latest,
        }
        line = json.dumps(entry, ensure_ascii=False, sort_keys=True)
        dated_path = os.path.join(self.log_dir, "asset_forge_unreal_{0}.jsonl".format(timestamp[:10].replace("-", "")))
        with io.open(dated_path, "a", encoding="utf-8") as stream:
            stream.write(line + "\n")
        shutil.copyfile(dated_path, latest)
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
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if hasattr(value, "name") and isinstance(getattr(value, "name"), text_type):
        return getattr(value, "name")
    return str(value)


def read_jsonl_tail(path, max_entries=30):
    if not path or not os.path.exists(path):
        return []
    try:
        with io.open(path, "r", encoding="utf-8") as stream:
            lines = [line for line in stream.readlines() if line.strip()]
    except IOError:
        return []
    entries = []
    for line in lines[-int(max_entries or 30) :]:
        try:
            entries.append(json.loads(line))
        except ValueError:
            entries.append({"raw": line.strip()})
    return entries


def _entry_summary(entry):
    outputs = entry.get("outputs", {}) if isinstance(entry, dict) else {}
    details = []
    if outputs.get("asset_name"):
        details.append("asset={0}".format(outputs.get("asset_name")))
    if outputs.get("manifest_path"):
        details.append("manifest={0}".format(outputs.get("manifest_path")))
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
    """Repair common UTF-8-as-GBK mojibake seen in Windows UE logs."""
    if not isinstance(value, text_type):
        return value
    if not any(marker in value for marker in MOJIBAKE_MARKERS):
        return value
    try:
        repaired = value.encode("gbk").decode("utf-8")
    except Exception:
        return value
    return repaired or value
