# DCC AssetForge v0.2.0

本版面向 Maya 或 Blender 到 Unreal Editor 的静态道具发布与验收。资产体检、Painter PBR/ARM 贴图匹配、增量材质复用、UE 入库批审和可共享的 JSON 项目预设，把命名、贴图通道和写入目标在导入前说明清楚，减少反复导出和人工核对。

**[下载 DCC-AssetForge-v0.2.0-Win64.zip](https://github.com/Elviszhuoyu/DCC-AssetForge/releases/download/v0.2.0/DCC-AssetForge-v0.2.0-Win64.zip)** · [SHA-256 校验文件](https://github.com/Elviszhuoyu/DCC-AssetForge/releases/download/v0.2.0/DCC-AssetForge-v0.2.0-Win64.zip.sha256) · [发行页](https://github.com/Elviszhuoyu/DCC-AssetForge/releases/tag/v0.2.0)

| 项目 | 内容 |
| --- | --- |
| 系统 | Windows x64，安装助手使用 .NET Framework 4.8 |
| 包大小 | 5,478,917 字节 |
| ZIP SHA-256 | `a517b4280d9b24d8a12d92b5d8b81e2e469148b8a6cf30f161cf3f3952d02c0e` |

右键 ZIP 选择「全部解压缩」，请解压至纯英文、无空格的本地目录，避开 OneDrive 同步目录。双击根目录的 **DCC-AssetForge-Setup.exe**，选择宿主和版本后安装。

安装程序未签名。确认从官方发行页下载后，如果 SmartScreen 出现「Windows 已保护你的电脑」，点「更多信息」→「仍要运行」。[图示和手动安装步骤](https://github.com/Elviszhuoyu/DCC-AssetForge/blob/v0.2.0/README.zh-CN.md#遇到-windows-smartscreen) · [安装指南](https://github.com/Elviszhuoyu/DCC-AssetForge/blob/v0.2.0/安装指南.md)

## 三步完成首次导入

1. 在 Maya 选中静态道具，从「AssetForge」工具架点 **AF**，检查后导出包体。Blender 的 Beta 导出入口位于 3D 视图的 N 侧栏。
2. 在 UE 工具栏点 **AF**，进入「包体导入」，选包体并点「检查包体」。核对目标后点「确认导入」。
3. 从导入结果前往「入库批审」，核对网格、材质槽和贴图，随后在 UE 视口确认外观。

## 本版功能

- **Maya 发布工作台。** 检查资产、匹配外部贴图、逐槽绑定贴图集，导出包含交换资产、贴图和报告的 AF 包体。项目预设以 UTF-8 JSON 保存，可供团队共用。
- **Unreal 导入和批审。** 导入前核对目标和写入策略，可复用兼容的材质实例和贴图。导入后进入「入库批审」，定位问题、预览可修贴图的影响并复验。
- **Windows 安装。** 提供原生 WPF 安装助手和 UE 5.8.4、5.6.1 Win64 预编译插件。支持引擎级或工程级安装，其他 UE 5.3–5.8 构建可选择工程级源码安装。ZIP 也提供 Maya 拖拽脚本、UE 插件文件夹和 Blender 扩展 ZIP。
- **UE 5.8.4 实机修复。** 修复引擎级安装后的门禁加载异常，实际资产已通过门禁检查并导入。

## 支持与验证范围

| 宿主 | 支持与验证范围 |
| --- | --- |
| Maya 2022–2026 | 使用 Python 3。2022–2024 用 PySide2，2025–2026 用 PySide6。Maya 2024.2 已验证拖拽安装、工作台重开、21 张贴图样例和 100% / 150% 缩放布局。其他版本未逐版实机验收。 |
| Unreal Editor 5.8.4 Win64 | 预编译版需匹配引擎补丁和构建编号。最终引擎级门禁已完成实际资产导入。v0.2.0 候选阶段也验证过引擎级、工程级安装、冷启动及卸载。 |
| Unreal Editor 5.6.1 Win64 | 预编译版需匹配引擎补丁和构建编号。早先的 v0.2.0 候选已验证工程级安装、工作台启动和读取 36 项内置资源。最终 WPF 安装路径未在该版本重测。 |
| UE 5.3–5.8 其他构建 | 可进行工程级源码安装，需要匹配的 Visual Studio C++ 工具和 Windows SDK。随包内置资源用 UE 5.6.1 保存。UE 5.3–5.5 即使编译成功也可能无法读取。源码安装及导入未逐版本实机验收。 |
| Blender 4.2 LTS–5.x | 基础导出支持（Beta，已在 Blender 5.2.1 LTS 冒烟验证）。独立配置下验证了安装、桌面侧栏打开与卸载，其他版本未逐版实测。 |
| 3ds Max | 暂不支持。 |

安装助手自动安装 Maya 和 Windows 管理员权限提示尚未实测。UE 引擎级卸载前，先在使用此插件的工程中禁用它。

开发者 **卓雨 (Elviszhuoyu)**。项目代码与文档采用 MIT License，许可范围见发行包根目录的 `LICENSE` 和 `NOTICE.md`。 [作者主页](https://work.zhuoyulabs.com)

---

# DCC AssetForge 0.1.0

Released on 2026-08-11 as the first tagged public version of DCC AssetForge.

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

## Verified for this release

- Python source compilation on Windows with Python 3.9 and 3.12.
- All 756 host-independent unit and contract tests in CI and an anonymous clean clone.
- UTF-8, U+FFFD, tracked private-path, forbidden binary, and tracked file-size checks.
- Offline generation of a small redacted static-prop package.
- Anonymous repository clone and public README rendering, including language links, CI badge, and Mermaid workflow diagram.
- Temporary Blender add-on installation and exact manual removal without opening Blender.
- Unreal plugin installation dry-run against an isolated fixture project without opening Unreal Editor.
- Repository whitespace checks.

## Host validation boundary

The repository contains prior local evidence for Maya 2026, Blender 5.1.2, and Unreal Engine 5.6. Those hosts were not reopened during the open-source preparation pass. A fresh clean-host install, UI path, import, material graph, and viewport review therefore remain `unverified` for the public Release.

Blender 4.2 is the manifest minimum, not a claim that every Blender version from 4.2 onward has been verified. Other Maya and Unreal versions are also unverified.

## Known limitations

- Static prop is the maintained product path; skeletal mesh and animation remain experimental.
- 3ds Max and a standalone desktop application are out of scope.
- Unreal material evidence does not replace final TA visual inspection.
- Automatic uninstall is not included; the README documents explicit per-host removal paths.
- No official screenshots or GIFs are included in this release.
- The DCC AssetForge name and six original AF icons are governed by `BRAND_ASSET_POLICY.md`, not the MIT License; modified public forks must follow that policy.
- The Blender add-on is prepared for direct/manual installation, not submission to the official Blender Extensions Platform; that platform has a separate GPL-3.0-or-later requirement.

## Upgrade and compatibility

This is the first public release. Internal identifiers remain `asset_forge`, `AssetForge`, `AssetForgeEditor`, `/AssetForge`, and existing `ASSET_FORGE_*`/schema keys. They are compatibility contracts and were not renamed with the public brand.

The GitHub Release contains the automatically generated source archives only. It does not bundle Maya, Blender, Unreal Engine, project binaries, scenes, models, or textures.

## License

Original repository code and documentation are available under the MIT License. Maya, Blender, Unreal Engine, Qt for Python, and Pillow are not bundled under that license; see `THIRD_PARTY_NOTICES.md`.
