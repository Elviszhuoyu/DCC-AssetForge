"""DCC adapter contract.

Adapters hide DCC-specific APIs behind a small stable surface. The shared
pipeline can call this interface without knowing whether the scene came from
Maya, Blender, or a future DCC.
"""

from __future__ import absolute_import


class DccAdapter(object):
    """Base class for DCC integrations."""

    dcc_name = "unknown"

    def is_available(self):
        """Return True when the adapter can access its host DCC API."""
        return False

    def get_current_selection(self):
        """Return selected asset roots in the host DCC."""
        raise NotImplementedError

    def scan_asset(self, asset_root, rules=None):
        """Return a serializable scan result for one asset root."""
        raise NotImplementedError

    def export_fbx(self, asset_root, output_path, preset=None):
        """Export one asset root as FBX and return the exported file path."""
        raise NotImplementedError

