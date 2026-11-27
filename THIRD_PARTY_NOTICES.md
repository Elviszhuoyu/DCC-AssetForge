# Third-Party Notices

This file describes dependencies and host APIs used by DCC AssetForge. It is an inventory, not legal advice.

No Maya, Blender, Unreal Engine, Qt, or Pillow source code or binaries are intentionally vendored in this repository.

| Component | Use | Distribution boundary | License or terms |
| --- | --- | --- | --- |
| Autodesk Maya Python API (`maya.cmds`, `maya.mel`) | Maya UI, scene inspection, export, and local bridge | Supplied by the user's licensed Maya installation; not bundled | Autodesk terms and Maya developer documentation |
| Blender Python API (`bpy`, `addon_utils`) | Blender add-on UI, scene inspection, and export | Supplied by Blender; not bundled | Blender is GPL; DCC AssetForge code declares MIT, a GPL-compatible license. This is not an official Extensions Platform submission. |
| Unreal Engine Python/C++ APIs | Editor plugin, Gate, import, and evidence collection | Supplied by the user's licensed Unreal Engine installation; Engine Code and binaries are not bundled | Unreal Engine EULA and documentation |
| PySide2/PySide6 and Shiboken | Optional host UI binding detection | Supplied by the host application when available; not bundled | LGPLv3/GPLv3/commercial options apply to Qt for Python distributions |
| shadcn/ui New York Button, Badge and Select | Maya embedded workbench | Three official component sources from commit `c8c4027b6b192822ea2952b225ee4760cddedf0d` are compiled into the local page | MIT. [Upstream file manifest](tools/maya_workbench_web/upstream.json) |
| React, Radix Select and Slot, Lucide, class-variance-authority and UI dependencies | Local JavaScript and CSS bundle | The runtime and its notices ship beside the workbench HTML. Node.js is only needed to rebuild it. | [Bundled licenses](Plugins/AssetForge/Resources/Workbench/web/THIRD-PARTY.txt) |
| Pillow (`PIL`) | Test image inspection and optional Maya screenshot alpha flattening | Installed separately from `requirements-dev.txt`; not bundled | Pillow License (MIT-CMU/HPND style) |
| Python standard library | Core offline implementation and tests | Supplied by the development or host Python runtime. | Python Software Foundation License |
| `actions/checkout` (`v4.4.0` commit pinned) | GitHub Actions source checkout | Downloaded by GitHub Actions at CI runtime; not vendored | MIT License |
| `actions/setup-python` (`v5.6.0` commit pinned) | GitHub Actions Python toolchain setup | Downloaded by GitHub Actions at CI runtime; not vendored | MIT License |

## Windows installation assistant

The standalone x64 \`DCC-AssetForge-Setup.exe\` uses Windows Presentation Foundation and .NET Framework 4.8. The release ZIP ships the installer assembly and its own artwork. Windows supplies the WPF and .NET Framework libraries. See the [Microsoft .NET Framework requirements](https://learn.microsoft.com/en-us/dotnet/framework/get-started/system-requirements).

## Official references

- Autodesk Terms of Use: <https://www.autodesk.com/company/terms-of-use/en/general-terms>
- Maya Developer Help: <https://help.autodesk.com/cloudhelp/2022/ENU/Maya-SDK/Introduction.html>
- Blender Extensions: <https://docs.blender.org/manual/en/latest/advanced/extensions/getting_started.html>
- Blender Extensions licensing: <https://docs.blender.org/manual/en/latest/advanced/extensions/licenses.html>
- Unreal Engine EULA: <https://www.unrealengine.com/eula/unreal>
- Unreal Engine Plugins: <https://dev.epicgames.com/documentation/en-us/unreal-engine/plugins-in-unreal-engine>
- Qt for Python licensing: <https://doc.qt.io/qtforpython-6/licenses.html>
- Pillow license: <https://github.com/python-pillow/Pillow/blob/main/LICENSE>
- actions/checkout license: <https://github.com/actions/checkout/blob/main/LICENSE>
- actions/setup-python license: <https://github.com/actions/setup-python/blob/main/LICENSE>

Current-candidate provenance checks:

1. Full-history path/content review found no obvious copied marketplace, studio, client, tutorial, engine-sample, or vendored-library source in the candidate. This is an evidence statement, not a legal guarantee.
2. Re-run dependency and provenance review whenever a vendored library, binary, model, texture, scene, archive, generated source file, or new runtime dependency is added.

The original DCC AssetForge icons are first-party works, not third-party material. They are excluded from MIT and governed by `BRAND_ASSET_POLICY.md`.

The official Blender Extensions Platform currently requires add-on submissions to use GPL-3.0-or-later. The repository's direct/manual Blender installation remains MIT-licensed and is not presented as platform-ready. Publishing there would require a separate maintainer licensing and packaging decision.
