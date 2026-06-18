"""Blender adapter placeholder.

The implementation will use bpy later while reusing shared rules and manifest
schemas.
"""

from __future__ import absolute_import

from asset_forge.shared.constants import SOURCE_DCC_BLENDER
from asset_forge.shared.dcc_adapter import DccAdapter, get_dcc_support_contract


class BlenderAdapter(DccAdapter):
    """Future Blender implementation of the DCC adapter contract."""

    dcc_name = SOURCE_DCC_BLENDER

    def support_contract(self):
        return get_dcc_support_contract(self.dcc_name)

    def is_available(self):
        try:
            import bpy  # noqa: F401
        except ImportError:
            return False
        return True

    def get_current_selection(self):
        raise NotImplementedError("Blender selection scanning is planned for Phase 5")

    def scan_asset(self, asset_root, rules=None):
        raise NotImplementedError("Blender asset scanning is planned for Phase 5")

    def export_fbx(self, asset_root, output_path, preset=None):
        raise NotImplementedError("Blender FBX export is planned for Phase 5")
