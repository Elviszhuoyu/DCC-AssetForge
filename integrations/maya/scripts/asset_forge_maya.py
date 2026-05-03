"""Maya module entry points for Asset Forge."""

from __future__ import absolute_import

from asset_forge.maya.pipeline import MayaStaticPropPipeline
from asset_forge.maya.ui import show as show_ui
from asset_forge.shared.constants import TARGET_PLATFORM_HIGH_END_MOBILE


def show():
    """Open the Asset Forge Maya UI."""
    return show_ui()


def scan_selection():
    """Scan the current Maya selection."""
    return MayaStaticPropPipeline().scan_selection()


def export_selected(output_dir, target_platform=TARGET_PLATFORM_HIGH_END_MOBILE, target_path="/Game/Props"):
    """Export the current Maya selection as an Asset Forge package."""
    pipeline = MayaStaticPropPipeline()
    selection = pipeline.adapter.get_current_selection()
    if not selection:
        raise RuntimeError("No selected asset")
    return pipeline.export_asset(selection[0], output_dir, target_platform, target_path)
