# Security Policy

## Supported versions

| Version | Supported |
| --- | --- |
| 0.1.x | Yes |
| Earlier or unreleased snapshots | No |

Security fixes target the latest `0.1.x` release and the current `main` branch.

## Reporting a vulnerability

Use GitHub Private Vulnerability Reporting from the repository **Security** tab.

If private reporting is unavailable:

1. Do not post a live credential, exploit payload, proprietary asset, or private path in a public issue.
2. Revoke or rotate any exposed credential immediately; removing it from the latest commit is not sufficient.
3. Open a redacted issue that states only the affected component and asks the maintainer to provide a private contact path.

Include the affected version or commit, impact, reproduction boundary, and whether Maya, Blender, Unreal, or an MCP bridge is required. Reports that involve localhost bridges should note the bind address, authentication configuration, and whether another local process can reach the port.

## Security boundaries

- MCP bridges are intended for localhost and expose fixed action allowlists. They are not designed as public network services.
- DCC AssetForge does not need cloud API keys for its core workflow.
- Generated packages and reports can contain asset names, source paths, project paths, or other production metadata. Review and redact them before sharing.
- Maya, Blender, Unreal Engine, plugins, and Python dependencies must be patched and licensed independently by the user.
