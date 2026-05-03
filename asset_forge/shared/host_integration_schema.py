"""Official host integration boundaries for Asset Forge."""

from __future__ import absolute_import

from asset_forge.shared.constants import SOURCE_DCC_BLENDER, SOURCE_DCC_MAYA, TARGET_ENGINE_UNREAL


HOST_INTEGRATION_VERSION = "0.1"


def get_host_integration_contracts():
    """Return official packaging and adapter boundaries for supported hosts."""
    return {
        "version": HOST_INTEGRATION_VERSION,
        "hosts": [
            {
                "host": SOURCE_DCC_MAYA,
                "package_type": "maya_module",
                "official_descriptor": ".mod",
                "runtime_api": ["maya.cmds", "maya.mel"],
                "expected_package_roots": ["scripts", "icons", "plug-ins"],
                "adapter_scope": ["selection", "scan_asset", "export_fbx"],
                "adapter_is_package": False,
                "status": "mvp",
            },
            {
                "host": SOURCE_DCC_BLENDER,
                "package_type": "blender_extension",
                "official_descriptor": "blender_manifest.toml",
                "runtime_api": ["bpy"],
                "expected_package_roots": ["__init__.py"],
                "adapter_scope": ["selection", "scan_asset", "export_fbx"],
                "adapter_is_package": False,
                "status": "planned",
            },
            {
                "host": TARGET_ENGINE_UNREAL,
                "package_type": "unreal_plugin",
                "official_descriptor": "Plugins/AssetForge/AssetForge.uplugin",
                "runtime_api": ["unreal"],
                "expected_package_roots": ["Content", "Content/Python"],
                "content_mount": "/AssetForge",
                "adapter_scope": ["read_manifest", "import_assets", "validate_plugin_content"],
                "adapter_is_package": False,
                "status": "mvp",
            },
        ],
    }


def validate_host_integration_contracts(contracts=None):
    """Return structural issues for host integration contracts."""
    active = contracts or get_host_integration_contracts()
    issues = []
    if not isinstance(active, dict):
        return ["host integration contracts must be a dict"]

    hosts = active.get("hosts", [])
    if not hosts:
        issues.append("missing hosts")

    seen_hosts = set()
    for index, host in enumerate(hosts):
        for field in ["host", "package_type", "official_descriptor", "runtime_api", "adapter_scope", "adapter_is_package"]:
            if field not in host:
                issues.append("hosts[{0}] missing field: {1}".format(index, field))
        host_name = host.get("host", "")
        if host_name in seen_hosts:
            issues.append("duplicate host: {0}".format(host_name))
        elif host_name:
            seen_hosts.add(host_name)
        if host.get("adapter_is_package") is not False:
            issues.append("host {0} adapter must not be treated as the official package".format(host_name))
    return issues


def get_host_integration_contract(host_name):
    for host in get_host_integration_contracts()["hosts"]:
        if host["host"] == host_name:
            return host
    raise KeyError("Unknown host integration contract: {0}".format(host_name))
