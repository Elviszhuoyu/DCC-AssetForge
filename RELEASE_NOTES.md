# DCC AssetForge 0.1.0 — Release Candidate Notes

This is a draft for the first public GitHub Release. It does not mean a tag or Release has been created.

## What this release is

DCC AssetForge 0.1.0 establishes an auditable static-prop path from Maya or Blender to an Unreal Editor review gate. The release focuses on explicit contracts, reports, and operator decisions rather than promising a one-click production pipeline across every host version.

## Highlights

- Shared JSON project preset, currently schema `0.3`, for paths, naming, budgets, materials, texture matching, target platform, and package versioning.
- Maya and Blender static-prop workbenches that scan, check, and export versioned packages.
- Packages containing FBX, textures, manifest, preset snapshot, export report, and material/texture binding evidence.
- Unreal Gate for package discovery, check-before-import, import history, cleanup preview, and validation reporting.
- Naming modes `overwrite` and `auto_increment`, with asset identity separated from package folder identity.
- Fixed-action localhost MCP bridges for Maya and Blender; arbitrary Python execution is not the default production boundary.
- English and Simplified Chinese documentation, security policy, contribution guide, third-party inventory, issue/PR templates, and host-independent CI.

## Verified for this release-candidate preparation

- Python source compilation.
- Host-independent unit and contract tests.
- UTF-8, U+FFFD, tracked private-path, forbidden binary, and tracked file-size checks.
- Offline generation of a small redacted static-prop package.
- Repository whitespace checks.

## Host validation boundary

The repository contains prior local evidence for Maya 2026, Blender 5.1.2, and Unreal Engine 5.6. Those hosts were not reopened during the open-source preparation pass. A fresh clean-host install, UI path, import, material graph, and viewport review therefore remain `unverified` for the public Release.

Blender 4.2 is the manifest minimum, not a claim that every Blender version from 4.2 onward has been verified. Other Maya and Unreal versions are also unverified.

## Known limitations

- Static prop is the maintained product path; skeletal mesh and animation remain experimental.
- 3ds Max and a standalone desktop application are out of scope.
- Unreal material evidence does not replace final TA visual inspection.
- Automatic uninstall is not included; the README documents explicit per-host removal paths.
- No official screenshots or GIFs are included in this candidate.
- The DCC AssetForge name and six original AF icons are governed by `BRAND_ASSET_POLICY.md`, not the MIT License; modified public forks must follow that policy.
- The Blender add-on is prepared for direct/manual installation, not submission to the official Blender Extensions Platform; that platform has a separate GPL-3.0-or-later requirement.

## Upgrade and compatibility

This is the first proposed public release. Internal identifiers remain `asset_forge`, `AssetForge`, `AssetForgeEditor`, `/AssetForge`, and existing `ASSET_FORGE_*`/schema keys. They are compatibility contracts and were not renamed with the public brand.

## License

Original repository code and documentation are available under the MIT License. Maya, Blender, Unreal Engine, Qt for Python, and Pillow are not bundled under that license; see `THIRD_PARTY_NOTICES.md`.
