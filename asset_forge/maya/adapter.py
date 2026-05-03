"""Maya adapter implementation."""

from __future__ import absolute_import

from asset_forge.maya.scanner import MayaAssetScanner
from asset_forge.maya.fbx_exporter import MayaFbxExporter
from asset_forge.shared.constants import SOURCE_DCC_MAYA
from asset_forge.shared.dcc_adapter import DccAdapter


class MayaAdapter(DccAdapter):
    """Maya implementation of the DCC adapter contract."""

    dcc_name = SOURCE_DCC_MAYA

    def __init__(self, scanner=None, exporter=None):
        self.scanner = scanner or MayaAssetScanner()
        self.exporter = exporter or MayaFbxExporter()

    def is_available(self):
        return self.scanner.is_available()

    def get_current_selection(self):
        return self.scanner.get_current_selection()

    def scan_asset(self, asset_root, rules=None):
        return self.scanner.scan(asset_root)

    def export_fbx(self, asset_root, output_path, preset=None):
        return self.exporter.export_asset(asset_root, output_path, preset)
