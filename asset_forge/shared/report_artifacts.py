"""Stable report artifact paths and metadata."""

from __future__ import absolute_import

import datetime
import os

from asset_forge.shared.path_utils import normalize_path


REPORT_DIR_NAME = "AssetForgeReports"

REPORT_FILE_NAMES = {
    "package_acceptance": "package_acceptance_report.json",
    "batch_package_acceptance": "batch_package_acceptance_report.json",
    "package_acceptance_flow": "package_acceptance_flow_report.json",
    "batch_package_acceptance_flow": "batch_acceptance_flow_report.json",
    "stage_validation_bundle": "stage_validation_bundle.json",
    "offline_evidence_bundle": "offline_evidence_bundle_report.json",
    "asset_forge_doctor": "asset_forge_doctor_report.json",
}


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def report_artifacts_dir(base_dir):
    return normalize_path(os.path.join(os.path.abspath(base_dir), REPORT_DIR_NAME))


def default_report_path(base_dir, stage):
    return normalize_path(os.path.join(report_artifacts_dir(base_dir), REPORT_FILE_NAMES.get(stage, stage + ".json")))


def ensure_report_parent(path):
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    return path


def attach_report_artifact_metadata(report, report_path=None, command_args=None):
    active_report_path = normalize_path(report_path or report.get("report_path", ""))
    report["report_path"] = active_report_path
    report["created_at_utc"] = report.get("created_at_utc") or utc_now()
    report["command_args"] = list(command_args or report.get("command_args", []))
    report["report_artifact"] = {
        "stage": report.get("stage", ""),
        "path": active_report_path,
        "directory": normalize_path(os.path.dirname(active_report_path)) if active_report_path else "",
        "file_name": os.path.basename(active_report_path) if active_report_path else "",
    }
    return report
