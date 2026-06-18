"""DCC adapter contract.

Adapters hide DCC-specific business APIs behind a small stable surface. This
contract is not a Maya module, Blender extension, or Unreal plugin package.
Official host packaging is tracked separately in host_integration_schema.
"""

from __future__ import absolute_import

from asset_forge.shared.constants import SOURCE_DCC_3DS_MAX, SOURCE_DCC_BLENDER, SOURCE_DCC_MAYA


DCC_SUPPORT_CONTRACTS = {
    SOURCE_DCC_MAYA: {
        "dcc": SOURCE_DCC_MAYA,
        "display_name": "Maya",
        "support": "implemented",
        "adapter_status": "implemented",
        "real_exporter": True,
        "scope": ["selection", "scan_asset", "export_fbx", "manifest"],
        "automation_transport": ["maya_mcp", "maya.cmds"],
        "mcp_status": "implemented",
        "workbench_strategy": "implemented_host_workbench",
        "start_phase": "landed",
        "portfolio_mvp": True,
        "roadmap": "Maya static prop export is the landed TA portfolio MVP path.",
    },
    SOURCE_DCC_BLENDER: {
        "dcc": SOURCE_DCC_BLENDER,
        "display_name": "Blender",
        "support": "roadmap",
        "adapter_status": "contract_only",
        "real_exporter": False,
        "scope": ["selection", "scan_asset", "export_fbx"],
        "automation_transport": ["blender_mcp", "bpy"],
        "mcp_status": "external_required",
        "workbench_strategy": "port_maya_export_workbench_flow_to_blender_extension",
        "start_phase": "next_after_static_prop_stabilization",
        "portfolio_mvp": False,
        "next_slice": "Blender P0 should export one selected static prop package that UE accept-flow can import.",
        "roadmap": "Compatibility contract and extension package shape only; no real Blender exporter is implemented.",
    },
    SOURCE_DCC_3DS_MAX: {
        "dcc": SOURCE_DCC_3DS_MAX,
        "display_name": "3ds Max",
        "support": "roadmap",
        "adapter_status": "contract_only",
        "real_exporter": False,
        "scope": ["selection", "scan_asset", "export_fbx"],
        "automation_transport": ["pymxs"],
        "mcp_status": "not_integrated",
        "workbench_strategy": "reuse_package_protocol_then_build_host_native_ui",
        "start_phase": "after_blender_vertical_slice",
        "portfolio_mvp": False,
        "next_slice": "3ds Max should start with adapter/package contract before any UI workbench.",
        "roadmap": "Compatibility contract only; no 3ds Max package or real exporter is implemented.",
    },
}


def get_dcc_support_contracts():
    """Return DCC support status without implying future exporters are live."""
    return dict((name, dict(contract)) for name, contract in DCC_SUPPORT_CONTRACTS.items())


def get_dcc_support_contract(dcc_name):
    contract = DCC_SUPPORT_CONTRACTS.get(dcc_name)
    if not contract:
        raise KeyError("Unknown DCC support contract: {0}".format(dcc_name))
    return dict(contract)


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
