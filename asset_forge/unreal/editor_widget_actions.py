"""Callable actions for a future Unreal Editor Utility Widget."""

from __future__ import absolute_import

from asset_forge.unreal import pipeline as unreal_pipeline


ACTION_PLAN = (
    {
        "id": "select_manifest",
        "label": "Select Manifest",
        "description": "Let the widget choose one Asset Forge manifest path.",
        "callable": "",
    },
    {
        "id": "select_package",
        "label": "Select Package",
        "description": "Let the widget choose one Asset Forge package directory.",
        "callable": "",
    },
    {
        "id": "dry_run_manifest",
        "label": "Dry Run Manifest",
        "description": "Validate one manifest and resolve its import preset without importing.",
        "callable": "dry_run_selected_manifest",
    },
    {
        "id": "import_manifest",
        "label": "Import Manifest",
        "description": "Import one selected manifest.",
        "callable": "import_selected_manifest",
    },
    {
        "id": "dry_run_package",
        "label": "Dry Run Package",
        "description": "Validate the newest manifest in one Asset Forge package directory.",
        "callable": "dry_run_selected_package",
    },
    {
        "id": "import_package",
        "label": "Import Package",
        "description": "Import the newest manifest in one Asset Forge package directory.",
        "callable": "import_selected_package",
    },
    {
        "id": "import_latest",
        "label": "Import Latest",
        "description": "Find and import the newest manifest under an export root.",
        "callable": "import_latest_export",
    },
    {
        "id": "dry_run_all",
        "label": "Dry Run All",
        "description": "Dry-run every manifest under an export root.",
        "callable": "dry_run_all_exports",
    },
    {
        "id": "import_all",
        "label": "Import All",
        "description": "Import every manifest under an export root.",
        "callable": "import_all_exports",
    },
)


class UnrealEditorWidgetActions(object):
    """Small facade that a future Editor Utility Widget can call directly."""

    def __init__(self, pipeline_module=None):
        self.pipeline = pipeline_module or unreal_pipeline

    def action_plan(self):
        return [dict(item) for item in ACTION_PLAN]

    def dry_run_selected_manifest(self, manifest_path, log_path=None):
        return self.pipeline.dry_run_manifest(manifest_path, log_path)

    def import_selected_manifest(self, manifest_path, log_path=None):
        return self.pipeline.import_manifest(manifest_path, log_path)

    def dry_run_selected_package(self, package_dir, report_path=None):
        return self.pipeline.import_asset_forge_package(package_dir, dry_run=True, report_path=report_path)

    def import_selected_package(self, package_dir, report_path=None):
        return self.pipeline.import_asset_forge_package(package_dir, dry_run=False, report_path=report_path)

    def import_latest_export(self, export_root, log_path=None, dry_run=False):
        return self.pipeline.import_latest_manifest(export_root, log_path, dry_run)

    def dry_run_all_exports(self, export_root, report_path=None):
        return self.pipeline.import_all_manifests(export_root, report_path, dry_run=True)

    def import_all_exports(self, export_root, report_path=None):
        return self.pipeline.import_all_manifests(export_root, report_path, dry_run=False)


def get_action_plan():
    return UnrealEditorWidgetActions().action_plan()


def dry_run_selected_manifest(manifest_path, log_path=None):
    return UnrealEditorWidgetActions().dry_run_selected_manifest(manifest_path, log_path)


def import_selected_manifest(manifest_path, log_path=None):
    return UnrealEditorWidgetActions().import_selected_manifest(manifest_path, log_path)


def dry_run_selected_package(package_dir, report_path=None):
    return UnrealEditorWidgetActions().dry_run_selected_package(package_dir, report_path)


def import_selected_package(package_dir, report_path=None):
    return UnrealEditorWidgetActions().import_selected_package(package_dir, report_path)


def import_latest_export(export_root, log_path=None, dry_run=False):
    return UnrealEditorWidgetActions().import_latest_export(export_root, log_path, dry_run)


def dry_run_all_exports(export_root, report_path=None):
    return UnrealEditorWidgetActions().dry_run_all_exports(export_root, report_path)


def import_all_exports(export_root, report_path=None):
    return UnrealEditorWidgetActions().import_all_exports(export_root, report_path)
