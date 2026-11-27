using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Management;
using System.Runtime.InteropServices;
using System.Security;
using System.Text;
using System.Text.RegularExpressions;
using System.Web.Script.Serialization;
using Microsoft.Win32;

namespace AssetForge.Setup
{
    internal sealed class UnrealEngine
    {
        internal UnrealEngine(string root, Version version, string buildId)
        {
            Root = root;
            VersionNumber = version;
            BuildId = buildId;
        }

        internal string Root { get; private set; }
        internal Version VersionNumber { get; private set; }
        internal string Version { get { return VersionNumber.ToString(); } }
        internal string BuildId { get; private set; }
        internal string DisplayName { get { return "UE " + Version; } }
    }

    internal sealed class UnrealPlan
    {
        internal bool Ready { get; set; }
        internal bool CanUninstall { get; set; }
        internal bool SourceAvailable { get; set; }
        internal bool NeedsEngineRoot { get; set; }
        internal bool EngineLevelConflict { get; set; }
        internal string ConflictMessage { get; set; } = "";
        internal string Message { get; set; } = "";
        internal string TargetPath { get; set; } = "";
        internal string EngineRoot { get; set; } = "";
        internal string EngineVersion { get; set; } = "";
        internal string ProjectFile { get; set; } = "";
        internal string PayloadMode { get; set; } = "";
    }

    internal sealed class UnrealResult
    {
        internal bool Success { get; set; }
        internal bool PermissionRequired { get; set; }
        internal string Message { get; set; } = "";
        internal string BackupPath { get; set; } = "";
        internal string CleanupWarning { get; set; } = "";
    }

    internal sealed class UnrealInstaller
    {
        private const string ReleaseVersion = "0.2.0";
        private const string PluginName = "AssetForge";
        private const string PluginFile = "AssetForge.uplugin";
        private const string ModuleName = "AssetForgeEditor";
        private const string ModulesFile = "Binaries/Win64/UnrealEditor.modules";
        private const string ModuleBinary = "Binaries/Win64/UnrealEditor-AssetForgeEditor.dll";
        private const string SourceRules = "Source/AssetForgeEditor/AssetForgeEditor.Build.cs";
        private const string DuplicateMessage = "此工程关联的引擎已安装 DCC AssetForge。请在工程的「编辑 → 插件」中启用引擎副本。";
        private static readonly StringComparer Paths = StringComparer.OrdinalIgnoreCase;
        private static readonly UTF8Encoding Utf8 = new UTF8Encoding(false, true);
        private static readonly string[] SourceExtensions = { ".cs", ".cpp", ".h", ".inl" };
        private static readonly string[] ResourceExtensions = { ".png", ".html", ".css", ".js", ".txt" };
        private static readonly Regex NumericVersion = new Regex(@"^\d+\.\d+(?:\.\d+)?$");
        private static readonly Regex ProjectArguments = new Regex(@"(?:[^\s""]+|""[^""]*"")+");
        // Match the public payload contract maintained by distribution_installer.py.
        private static readonly string[] RequiredFiles =
        {
            PluginFile, ModulesFile, ModuleBinary,
            "Content/Python/init_unreal.py",
            "Content/Python/asset_forge/__init__.py",
            "Content/Python/asset_forge/unreal/editor_menu.py",
            "Content/Python/asset_forge/unreal/review_workbench.py",
            "Content/Python/asset_forge/shared/__init__.py",
            "Content/Python/config/import_presets.json",
            "Content/Python/config/material_profiles.json",
            "Content/Python/config/project_rules.json",
            "Content/Python/config/project_settings.example.json",
            "Resources/Workbench/brand/af_shelf.png", "LICENSE", "NOTICE.md",
            "THIRD_PARTY_NOTICES.md", "BRAND_ASSET_POLICY.md", "Config/FilterPlugin.ini",
            "Content/MaterialInstances/MI_AF_Character_Default.uasset",
            "Content/MaterialInstances/MI_AF_Character_SkinPreview.uasset",
            "Content/MaterialInstances/MI_AF_Environment_Default.uasset",
            "Content/MaterialInstances/MI_AF_Environment_Emissive.uasset",
            "Content/MaterialInstances/MI_AF_Environment_Masked.uasset",
            "Content/MaterialInstances/MI_AF_Environment_Masked_SeparateMask.uasset",
            "Content/MaterialInstances/MI_AF_Environment_TileFloor.uasset",
            "Content/MaterialInstances/MI_AF_Environment_WornWall.uasset",
            "Content/MaterialInstances/MI_AF_Props_Default.uasset",
            "Content/MaterialInstances/MI_AF_Props_DirtyWear.uasset",
            "Content/MaterialInstances/MI_AF_Props_Emissive.uasset",
            "Content/MaterialInstances/MI_AF_Props_Masked.uasset",
            "Content/MaterialInstances/MI_AF_Props_Masked_SeparateMask.uasset",
            "Content/MaterialInstances/MI_AF_Props_MetalPanel.uasset",
            "Content/MaterialInstances/MI_AF_Props_RubberMatte.uasset",
            "Content/Materials/M_AF_Character_Master.uasset",
            "Content/Materials/M_AF_Environment_Master.uasset",
            "Content/Materials/M_AF_Opaque_PBR.uasset",
            "Content/Materials/M_AF_Props_Master.uasset",
            "Content/Materials/M_AF_Props_Opaque_Master.uasset",
            "Content/Textures/T_AF_Default_ARM.uasset",
            "Content/Textures/T_AF_Default_BaseColor.uasset",
            "Content/Textures/T_AF_Default_Emissive.uasset",
            "Content/Textures/T_AF_Default_ImperfectionMask.uasset",
            "Content/Textures/T_AF_Default_Normal.uasset",
            "Content/Textures/T_AF_Default_OpacityMask.uasset",
            "Content/Textures/T_AF_Preview_ARM_Metal.uasset",
            "Content/Textures/T_AF_Preview_ARM_Rough.uasset",
            "Content/Textures/T_AF_Preview_BaseColor_AlphaGrid.uasset",
            "Content/Textures/T_AF_Preview_BaseColor_MetalPanel.uasset",
            "Content/Textures/T_AF_Preview_BaseColor_Rubber.uasset",
            "Content/Textures/T_AF_Preview_BaseColor_SkinWarm.uasset",
            "Content/Textures/T_AF_Preview_BaseColor_TileFloor.uasset",
            "Content/Textures/T_AF_Preview_Emissive_Panels.uasset",
            "Content/Textures/T_AF_Preview_Imperfection_Wear.uasset",
            "Content/Textures/T_AF_Preview_OpacityMask_Stripes.uasset"
        };

        private sealed class InstallProblem : Exception
        {
            internal bool NeedsEngineRoot { get; private set; }

            internal InstallProblem(string message, bool needsEngineRoot = false, Exception inner = null)
                : base(message, inner)
            {
                NeedsEngineRoot = needsEngineRoot;
            }
        }

        private sealed class Destination
        {
            internal string Project;
            internal string Folder;
            internal byte[] Original;
            internal byte[] Updated;
            internal Dictionary<string, object> Descriptor;
            internal UnrealEngine Engine;
            internal string BackupBase;
        }

        private readonly string payloadRoot;

        internal UnrealInstaller(string payloadRoot)
        {
            this.payloadRoot = FullPath(payloadRoot);
        }

        internal List<UnrealEngine> DiscoverEngines()
        {
            var engines = new Dictionary<string, UnrealEngine>(Paths);
            foreach (string path in EngineRegistrations().Values.Distinct(Paths))
            {
                try
                {
                    UnrealEngine engine = ReadEngine(path);
                    engines[engine.Root] = engine;
                }
                catch (Exception error) when (KnownError(error))
                {
                    // Stale registrations are omitted; the folder picker reports validation details.
                }
            }
            return engines.Values.OrderByDescending(engine => engine.VersionNumber)
                .ThenBy(engine => engine.Root, Paths).ToList();
        }

        internal List<string> DiscoverProjects(IEnumerable<UnrealEngine> engines)
        {
            var paths = new HashSet<string>(Paths);
            var roots = new HashSet<string>(Paths)
            {
                Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "Unreal Projects")
            };
            string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            string engineData = Path.Combine(local, "UnrealEngine");
            var config = new HashSet<string>(Paths)
            {
                Path.Combine(engineData, "Common", "Saved", "Config"),
                Path.Combine(local, "EpicGamesLauncher", "Saved", "Config")
            };
            foreach (UnrealEngine engine in engines)
                config.Add(Path.Combine(engineData, engine.VersionNumber.ToString(2), "Saved", "Config"));

            foreach (string folder in config)
            foreach (string windowsFolder in Directories(folder, "Windows*"))
            {
                try
                {
                    foreach (string file in Directory.GetFiles(windowsFolder, "*UserSettings.ini"))
                    {
                        string settings = File.ReadAllText(file, Utf8);
                        foreach (Match match in Regex.Matches(settings, @"(?im)^\+?CreatedProjectPaths\s*=\s*(.+)$"))
                            roots.Add(match.Groups[1].Value.Trim().Trim('"'));
                        foreach (Match match in Regex.Matches(settings, @"(?im)(?:ProjectName|LastProject)\s*=\s*[""']?([A-Z]:[^\r\n""']+?\.uproject)"))
                            paths.Add(match.Groups[1].Value);
                    }
                }
                catch (Exception error) when (KnownError(error))
                {
                    // Optional recent entries may be locked or unavailable.
                }
            }
            foreach (string root in roots.Where(IsFullyQualified))
            {
                foreach (string folder in new[] { root }.Concat(Directories(root, "*")))
                {
                    try
                    {
                        foreach (string candidate in Directory.GetFiles(folder, "*.uproject"))
                            paths.Add(candidate);
                    }
                    catch (Exception error) when (KnownError(error))
                    {
                        // An offline root does not stop browsing for a project manually.
                    }
                }
            }
            return paths.Where(path => IsFullyQualified(path) && File.Exists(path))
                .Select(FullPath).Distinct(Paths).OrderBy(path => path, Paths).ToList();
        }

        internal UnrealEngine ReadEngine(string path)
        {
            string root = NormalizeEngineRoot(path);
            string engine = Path.Combine(root, "Engine");
            RejectAncestors(engine);
            string editor = EditorExecutable(root);
            string build = Path.Combine(engine, "Build", "Build.version");
            if (!File.Exists(build) || !File.Exists(editor))
                throw new InstallProblem("请选择包含 Unreal Editor 的完整引擎文件夹。", true);
            RejectAncestors(editor);
            RejectAncestors(build);
            var version = ReadObject(build, "Unreal Engine 版本信息");
            object major = Value(version, "MajorVersion");
            object minor = Value(version, "MinorVersion");
            object patch = Value(version, "PatchVersion");
            if (!(major is int) || !(minor is int) || !(patch is int) ||
                (int)major != 5 || (int)minor < 3 || (int)minor > 8 || (int)patch < 0)
                throw new InstallProblem("此版本超出本发行包支持范围。请选择 Windows UE 5.3 至 5.8。");
            string modules = Path.Combine(Path.GetDirectoryName(editor), "UnrealEditor.modules");
            string buildId = File.Exists(modules) ? StringValue(ReadObject(modules, "Unreal Editor 构建信息"), "BuildId") : "";
            return new UnrealEngine(root, new Version((int)major, (int)minor, (int)patch), buildId);
        }

        internal UnrealPlan Plan(string projectFile = null, string engineRoot = null,
                                 bool engineInstall = false, bool source = false)
        {
            var plan = new UnrealPlan();
            try
            {
                Destination target = ReadDestination(projectFile, engineRoot, engineInstall, plan);
                FillInstallPlan(target, engineRoot, engineInstall, source, plan);
            }
            catch (Exception error) when (KnownError(error))
            {
                plan.Ready = false;
                plan.Message = Explain(error);
                plan.NeedsEngineRoot = (error as InstallProblem)?.NeedsEngineRoot ?? false;
            }
            return plan;
        }

        internal UnrealResult Install(string projectFile = null, string engineRoot = null,
                                      bool engineInstall = false, bool source = false)
        {
            var result = new UnrealResult();
            var plan = new UnrealPlan();
            try
            {
                Destination target = ReadDestination(projectFile, engineRoot, engineInstall, plan);
                RequireClosed(target.Project);
                Dictionary<string, string> files = FillInstallPlan(target, engineRoot, engineInstall, source, plan);
                Publish(target, files, target.Updated, plan.PayloadMode == "source", result);
                result.Success = true;
                result.Message = engineInstall
                    ? "安装完成。打开工程，在「编辑 → 插件」搜索 DCC AssetForge 并启用。"
                    : plan.PayloadMode == "source" ? "源码安装完成。打开工程后按 Unreal 提示编译插件。"
                    : "安装完成。重新打开此工程，点击工具栏的 AF 图标。";
            }
            catch (Exception error) when (KnownError(error)) { ResultError(result, error); }
            result.Message += result.CleanupWarning;
            return result;
        }

        internal UnrealResult Uninstall(string projectFile = null, string engineRoot = null,
                                        bool engineInstall = false)
        {
            var result = new UnrealResult();
            try
            {
                Destination target = ReadDestination(projectFile, engineRoot, engineInstall, new UnrealPlan());
                RequireClosed(target.Project);
                bool installed = Directory.Exists(target.Folder);
                if (installed && (!File.Exists(Path.Combine(target.Folder, PluginFile))
                                  || !OwnsPlugin(Path.Combine(target.Folder, PluginFile))))
                    throw new InstallProblem("该位置的插件归属无法确认，未移动原目录。");

                if (engineInstall)
                {
                    if (!installed)
                        throw new InstallProblem("此位置没有需要卸载的 DCC AssetForge。");
                    EnsureEngineReferencesDisabled(target.Engine);
                }
                else if (!installed)
                {
                    UnrealEngine linked = TryResolveEngine(target, engineRoot);
                    if (linked != null && HasEnginePlugin(linked.Root))
                        throw new InstallProblem("此工程使用引擎级插件。请在工程的插件列表中禁用，或切换到引擎安装模式。");
                }

                byte[] updated = target.Project == null ? null : EditProject(target, false);
                if (!installed && ReferenceEquals(updated, target.Original))
                    throw new InstallProblem("此位置没有需要卸载的 DCC AssetForge。");
                Publish(target, null, updated, false, result);
                result.Success = true;
                result.Message = "已卸载此位置的 DCC AssetForge，原文件已备份。";
            }
            catch (Exception error) when (KnownError(error)) { ResultError(result, error); }
            result.Message += result.CleanupWarning;
            return result;
        }

        internal string OccupancyMessage(string projectFile = null)
        {
            try
            {
                RequireClosed(string.IsNullOrWhiteSpace(projectFile) ? null : FullPath(projectFile));
                return "";
            }
            catch (Exception error) when (KnownError(error)) { return Explain(error); }
        }

        private Destination ReadDestination(string projectFile, string engineRoot, bool engineInstall, UnrealPlan plan)
        {
            var target = new Destination();
            if (engineInstall)
            {
                target.Engine = ReadEngine(engineRoot);
                target.Folder = MarketplacePath(target.Engine.Root);
                target.BackupBase = Path.Combine(target.Engine.Root, "Engine");
                plan.EngineRoot = target.Engine.Root;
                plan.EngineVersion = target.Engine.Version;
            }
            else
            {
                if (string.IsNullOrWhiteSpace(projectFile) || !File.Exists(projectFile) ||
                    !Paths.Equals(Path.GetExtension(projectFile), ".uproject"))
                    throw new InstallProblem("请选择 Unreal 工程文件（.uproject）。");
                target.Project = FullPath(projectFile);
                RejectAncestors(target.Project);
                target.Original = File.ReadAllBytes(target.Project);
                target.Descriptor = DecodeObject(target.Original, "UE 工程描述文件");
                target.BackupBase = Path.GetDirectoryName(target.Project);
                target.Folder = Path.Combine(target.BackupBase, "Plugins", PluginName);
                plan.ProjectFile = target.Project;
            }

            RejectAncestors(target.Folder);
            for (string folder = target.Folder; !Paths.Equals(target.BackupBase, folder); folder = Path.GetDirectoryName(folder))
            {
                if (File.Exists(folder))
                    throw new InstallProblem("插件安装路径被文件占用。请恢复目录后重试。");
            }
            plan.TargetPath = target.Folder;
            plan.CanUninstall = File.Exists(Path.Combine(target.Folder, PluginFile));
            if (!engineInstall && !plan.CanUninstall && !Directory.Exists(target.Folder))
                plan.CanUninstall = PluginEntries(target.Descriptor, false).Any(IsAssetForge);
            return target;
        }

        private Dictionary<string, string> FillInstallPlan(Destination target, string engineRoot,
                                                            bool engineInstall, bool source, UnrealPlan plan)
        {
            if (!engineInstall)
            {
                target.Engine = ResolveEngine(target, engineRoot);
                plan.EngineRoot = target.Engine.Root;
                plan.EngineVersion = target.Engine.Version;
                if (HasEnginePlugin(target.Engine.Root))
                {
                    plan.EngineLevelConflict = true;
                    plan.ConflictMessage = DuplicateMessage;
                    plan.CanUninstall = File.Exists(Path.Combine(target.Folder, PluginFile));
                    throw new InstallProblem(DuplicateMessage);
                }
                target.Updated = EditProject(target, true);
            }

            RejectAncestors(payloadRoot);
            bool sourceMode;
            string folder = SelectPayload(target.Engine, engineInstall, source, plan, out sourceMode);
            if (IsInside(folder, target.Folder) || IsInside(target.Folder, folder))
                throw new InstallProblem("安装来源与目标插件目录重叠。请从独立解压的发行包重新打开安装助手。");
            Dictionary<string, string> files = PayloadFiles(folder, target.Engine, sourceMode);
            plan.PayloadMode = sourceMode ? "source" : "binary";
            plan.Ready = true;
            plan.Message = sourceMode ? "可安装源码。打开工程后按 Unreal 提示编译插件。" : "已找到匹配的预编译插件，可以直接安装。";
            return files;
        }

        private string SelectPayload(UnrealEngine engine, bool engineInstall, bool source, UnrealPlan plan, out bool sourceMode)
        {
            sourceMode = false;
            if (File.Exists(Path.Combine(payloadRoot, PluginFile)))
            {
                if (engine.Version != "5.8.4" || engine.BuildId != "55116800")
                    throw new InstallProblem("此 Unreal 的版本或构建编号与单版本插件不匹配。请选择匹配的引擎。");
                if (source)
                    throw new InstallProblem("此发行目录只包含预编译插件。");
                return payloadRoot;
            }
            string binary = Path.Combine(payloadRoot, engine.Version, PluginName);
            string sourceRoot = Path.Combine(payloadRoot, "Source", PluginName);
            RejectAncestors(binary);
            RejectAncestors(sourceRoot);
            plan.SourceAvailable = File.Exists(Path.Combine(sourceRoot, PluginFile));
            if (source && engineInstall)
                throw new InstallProblem("引擎级安装需要匹配的预编译插件。源码安装适用于单个工程。");
            string modules = Path.Combine(binary, ModulesFile);
            if (!source && File.Exists(modules) && engine.BuildId.Length != 0 &&
                StringValue(ReadObject(modules, "插件构建信息"), "BuildId") == engine.BuildId)
                return binary;
            if (plan.SourceAvailable)
            {
                if (engineInstall)
                    throw new InstallProblem("此引擎没有匹配的预编译插件。切换到「安装到单个工程」后可选择源码安装。");
                if (!source)
                    throw new InstallProblem("此引擎没有匹配的预编译插件。可选择「源码安装」，由 Unreal 编译。");
                sourceMode = true;
                return sourceRoot;
            }
            throw new InstallProblem("未找到适用于此引擎的插件文件。请确认发行包已完整解压。");
        }

        private UnrealEngine ResolveEngine(Destination target, string overrideRoot, IDictionary<string, string> suppliedRegistrations = null)
        {
            string detected = null;
            object raw = Value(target.Descriptor, "EngineAssociation");
            if ((raw == null && target.Descriptor.ContainsKey("EngineAssociation")) || (raw != null && !(raw is string)))
                throw new InstallProblem("UE 工程的引擎关联无法识别。请在 Unreal 中检查此工程的引擎版本。");
            string association = (raw as string ?? "").Trim();
            var registered = suppliedRegistrations ?? EngineRegistrations();
            registered.TryGetValue(association, out detected);
            bool numeric = NumericVersion.IsMatch(association);
            if (detected == null && numeric)
                registered.TryGetValue(string.Join(".", association.Split('.').Take(2)), out detected);
            if (detected == null && association.Length == 0)
            {
                for (DirectoryInfo folder = new FileInfo(target.Project).Directory; folder != null; folder = folder.Parent)
                {
                    if (File.Exists(Path.Combine(folder.FullName, "Engine", "Build", "Build.version")))
                    {
                        detected = folder.FullName;
                        break;
                    }
                }
            }
            if (detected != null && !File.Exists(EditorExecutable(NormalizeEngineRoot(detected))))
                detected = null;
            string selected = string.IsNullOrWhiteSpace(overrideRoot) ? detected : overrideRoot;
            if (string.IsNullOrWhiteSpace(selected))
                throw new InstallProblem("未找到此工程关联的 Unreal。请选择工程实际使用的引擎目录。", true);
            string canonical = NormalizeEngineRoot(selected);
            if (detected != null && !Paths.Equals(canonical, NormalizeEngineRoot(detected)))
                throw new InstallProblem("此工程已关联另一处 Unreal 安装。请选择工程当前关联的引擎目录。");
            UnrealEngine engine = ReadEngine(canonical);
            if (numeric && engine.Version != association && engine.VersionNumber.ToString(2) != association)
                throw new InstallProblem("此工程关联 UE " + association + "。请选择对应的引擎目录。");
            return engine;
        }

        private UnrealEngine TryResolveEngine(Destination target, string overrideRoot)
        {
            try { return ResolveEngine(target, overrideRoot); }
            catch (InstallProblem error) when (error.NeedsEngineRoot)
            {
                // Stale project references can be removed without a registered engine.
                return null;
            }
        }

        private Dictionary<string, string> EngineRegistrations()
        {
            var found = new Dictionary<string, string>(Paths);
            string commonData = Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData);
            string index = Path.Combine(commonData, "Epic", "UnrealEngineLauncher", "LauncherInstalled.dat");
            if (File.Exists(index))
            {
                try
                {
                    var entries = Value(ReadObject(index, "Epic Launcher 安装列表"), "InstallationList") as object[];
                    if (entries != null)
                    foreach (var row in entries.OfType<Dictionary<string, object>>())
                    {
                        string name = StringValue(row, "AppName");
                        string location = StringValue(row, "InstallLocation");
                        if (name.StartsWith("UE_", StringComparison.OrdinalIgnoreCase) && IsFullyQualified(location))
                            found[name.Substring(3)] = location;
                    }
                }
                catch (Exception error) when (KnownError(error))
                {
                    // Invalid launcher metadata leaves registry and manual discovery available.
                }
            }
            try
            {
                using (RegistryKey user = Registry.CurrentUser.OpenSubKey(@"SOFTWARE\Epic Games\Unreal Engine\Builds"))
                {
                    if (user != null)
                    foreach (string name in user.GetValueNames())
                    {
                        string location = user.GetValue(name) as string;
                        if (IsFullyQualified(location) && !found.ContainsKey(name))
                            found[name] = location;
                    }
                }
            }
            catch (Exception error) when (KnownError(error))
            {
                // A restricted user registration leaves Launcher and manual discovery available.
            }
            for (int minor = 3; minor <= 8; minor++)
            {
                string version = "5." + minor;
                if (found.ContainsKey(version))
                    continue;
                try
                {
                    using (RegistryKey machine = Registry.LocalMachine.OpenSubKey(@"SOFTWARE\EpicGames\Unreal Engine\" + version))
                    {
                        string location = machine?.GetValue("InstalledDirectory") as string;
                        if (IsFullyQualified(location))
                            found[version] = location;
                    }
                }
                catch (Exception error) when (KnownError(error))
                {
                    // Launcher builds are not required to provide a registry key.
                }
            }
            return found;
        }

        private void EnsureEngineReferencesDisabled(UnrealEngine engine)
        {
            var registrations = EngineRegistrations();
            var pending = new List<string>();
            foreach (string project in DiscoverProjects(new[] { engine }))
            {
                if (File.Exists(Path.Combine(Path.GetDirectoryName(project), "Plugins", PluginName, PluginFile)))
                    continue;
                try
                {
                    Destination target = ReadDestination(project, null, false, new UnrealPlan());
                    if (!PluginEntries(target.Descriptor, false).Any(row => IsAssetForge(row) && IsTrue(Value(row, "Enabled"))))
                        continue;
                    if (Paths.Equals(ResolveEngine(target, null, registrations).Root, engine.Root))
                        pending.Add(Path.GetFileNameWithoutExtension(project));
                }
                catch (Exception error) when (KnownError(error))
                {
                    // Missing or unreadable recent entries cannot identify this engine.
                }
            }
            if (pending.Count > 0)
                throw new InstallProblem("请先在以下工程的「编辑 → 插件」禁用 DCC AssetForge 后再卸载。\n" +
                                         string.Join("\n", pending));
        }

        private static Dictionary<string, string> PayloadFiles(string folder, UnrealEngine engine, bool source)
        {
            if (!Directory.Exists(folder))
                throw new InstallProblem("缺少 UE 插件文件。请把发行包解压完整后重新打开安装助手。");
            var required = new HashSet<string>(RequiredFiles, StringComparer.Ordinal);
            if (source)
            {
                required.Remove(ModulesFile);
                required.Remove(ModuleBinary);
                required.Add(SourceRules);
            }
            var files = new Dictionary<string, string>(StringComparer.Ordinal);
            foreach (string file in WalkFiles(folder))
            {
                string relative = file.Substring(folder.Length + 1).Replace('\\', '/');
                string extension = Path.GetExtension(relative);
                bool supported = required.Contains(relative) ||
                    source && relative.StartsWith("Source/AssetForgeEditor/", StringComparison.Ordinal) && SourceExtensions.Contains(extension) ||
                    relative.StartsWith("Content/Python/asset_forge/", StringComparison.Ordinal) && extension == ".py" && !relative.Contains("/__pycache__/") ||
                    relative.StartsWith("Resources/", StringComparison.Ordinal) && ResourceExtensions.Contains(extension);
                if (!supported)
                    throw new InstallProblem("UE 安装包包含不受支持的文件。请重新解压完整发行包。");
                files.Add(relative, file);
            }
            if (!required.IsSubsetOf(files.Keys))
                throw new InstallProblem("UE 插件文件不完整。请重新解压完整发行包。");
            var descriptor = ReadObject(files[PluginFile], "AssetForge 插件描述");
            if (StringValue(descriptor, "VersionName") != ReleaseVersion || !Equals(Value(descriptor, "Version"), 2))
                throw new InstallProblem("AssetForge 插件版本与安装助手不匹配。请重新解压同一份发行包。");
            if (source)
            {
                if (StringValue(descriptor, "EngineVersion").Length != 0 || IsTrue(Value(descriptor, "Installed")))
                    throw new InstallProblem("源码插件包含预编译版本配置。请使用同一发行包附带的源码插件。");
            }
            else
            {
                if (StringValue(descriptor, "EngineVersion") != engine.VersionNumber.ToString(2) + ".0" ||
                    !IsTrue(Value(descriptor, "Installed")))
                    throw new InstallProblem("此插件版本与所选 Unreal 不匹配。请重新解压同一份发行包。");
                var modules = ReadObject(files[ModulesFile], "AssetForge 插件构建信息");
                var moduleMap = Value(modules, "Modules") as Dictionary<string, object>;
                if (StringValue(modules, "BuildId") != engine.BuildId || moduleMap == null || moduleMap.Count != 1 ||
                    StringValue(moduleMap, ModuleName) != Path.GetFileName(ModuleBinary))
                    throw new InstallProblem("此 AssetForge 插件的二进制不适用于所选 Unreal。请重新解压正确的发行包。");
            }
            return files;
        }

        private static byte[] EditProject(Destination target, bool enable)
        {
            var plugins = PluginEntries(target.Descriptor, enable);
            var entries = plugins.Where(IsAssetForge).ToList();
            if (enable)
            {
                if (entries.Count > 1)
                    throw new InstallProblem("工程中有重复的 AssetForge 插件设置。请先在 Unreal Editor 中修正。");
                if (entries.Count == 0)
                    plugins.Add(new Dictionary<string, object> { { "Name", PluginName }, { "Enabled", true } });
                else if (IsTrue(Value(entries[0], "Enabled")))
                    return target.Original;
                else
                    entries[0]["Enabled"] = true;
            }
            else
            {
                if (entries.Count == 0)
                    return target.Original;
                plugins.RemoveAll(IsAssetForge);
            }
            target.Descriptor["Plugins"] = plugins;
            return Utf8.GetBytes(Json().Serialize(target.Descriptor) + "\n");
        }

        private static List<Dictionary<string, object>> PluginEntries(Dictionary<string, object> descriptor, bool enable)
        {
            if (!descriptor.ContainsKey("Plugins"))
                return new List<Dictionary<string, object>>();
            var plugins = Value(descriptor, "Plugins") as IEnumerable<object>;
            if (plugins == null || plugins.Any(item => !(item is Dictionary<string, object>)))
                throw new InstallProblem(enable ? "工程的插件列表格式不受支持。请先在 Unreal Editor 中修正。"
                                                : "工程的插件列表格式无法识别。请先在 Unreal Editor 中修正。");
            return plugins.Cast<Dictionary<string, object>>().ToList();
        }

        private static void Publish(Destination target, Dictionary<string, string> files, byte[] updated,
                                    bool source, UnrealResult result)
        {
            string backupBase = Path.Combine(target.BackupBase, "Saved", "AssetForge", "InstallerBackups");
            RejectAncestors(backupBase);
            Directory.CreateDirectory(backupBase);
            string lockPath = Path.Combine(backupBase, "install.lock");
            RejectRedirect(lockPath);
            if (File.Exists(lockPath) || Directory.Exists(lockPath))
                throw new InstallProblem("此位置已有安装操作。请等待完成后再试。");

            FileStream operationLock;
            try { operationLock = new FileStream(lockPath, FileMode.CreateNew, FileAccess.Write, FileShare.None, 1, FileOptions.DeleteOnClose); }
            catch (IOException error) when (File.Exists(lockPath) || Directory.Exists(lockPath))
            {
                throw new InstallProblem("此位置已有安装操作。请等待完成后再试。", inner: error);
            }
            using (operationLock)
            {
                string stage = Path.Combine(Path.GetDirectoryName(backupBase), "af_" + Guid.NewGuid().ToString("N"));
                Directory.CreateDirectory(stage);
                try
                {
                    string stagedPlugin = null;
                    if (files != null)
                    {
                        stagedPlugin = Path.Combine(stage, PluginName);
                        foreach (var file in files)
                        {
                            RejectAncestors(file.Value);
                            string destination = Path.Combine(stagedPlugin, file.Key);
                            Directory.CreateDirectory(Path.GetDirectoryName(destination));
                            File.Copy(file.Value, destination);
                        }
                        PayloadFiles(stagedPlugin, target.Engine, source);
                        CarryPresets(target.Folder, stagedPlugin);
                    }
                    string stagedProject = null;
                    if (target.Project != null && !ReferenceEquals(updated, target.Original))
                    {
                        stagedProject = Path.Combine(stage, Path.GetFileName(target.Project));
                        DecodeObject(updated, "更新后的 UE 工程描述文件");
                        File.WriteAllBytes(stagedProject, updated);
                    }

                    RequireClosed(target.Project);
                    RejectAncestors(target.Folder);
                    if (target.Project != null)
                    {
                        RejectAncestors(target.Project);
                        if (!File.ReadAllBytes(target.Project).SequenceEqual(target.Original))
                            throw new InstallProblem("工程设置在操作过程中发生了变化。请重新选择工程后重试。");
                    }
                    string backup = Path.Combine(backupBase, "prior_" + Guid.NewGuid().ToString("N"));
                    Directory.CreateDirectory(backup);
                    result.BackupPath = backup;
                    if (target.Project != null)
                        File.WriteAllBytes(Path.Combine(backup, Path.GetFileName(target.Project)), target.Original);
                    if (stagedPlugin != null)
                        Directory.CreateDirectory(Path.GetDirectoryName(target.Folder));
                    Swap(target, stagedPlugin, stagedProject, backup);
                }
                finally
                {
                    try { Directory.Delete(stage, true); }
                    catch (Exception error) when (KnownError(error))
                    {
                        result.CleanupWarning = "\n未能清理暂存目录。暂存位置：" + stage;
                    }
                }
            }
        }

        private static void CarryPresets(string target, string stage)
        {
            if (!Directory.Exists(target))
                return;
            foreach (string preset in WalkFiles(target).Where(file => file.EndsWith(".assetforge.json", StringComparison.OrdinalIgnoreCase)))
            {
                string destination = Path.Combine(stage, preset.Substring(target.Length + 1));
                if (File.Exists(destination))
                    continue;
                Directory.CreateDirectory(Path.GetDirectoryName(destination));
                File.Copy(preset, destination);
            }
        }

        private static void Swap(Destination target, string stagedPlugin, string stagedProject, string backup)
        {
            string previous = Path.Combine(backup, PluginName);
            if (Directory.Exists(target.Folder))
                Directory.Move(target.Folder, previous);
            bool published = false;
            try
            {
                if (stagedPlugin != null)
                {
                    Directory.Move(stagedPlugin, target.Folder);
                    published = true;
                }
                if (stagedProject != null)
                    File.Replace(stagedProject, target.Project, null, true);
            }
            catch (Exception error) when (KnownError(error))
            {
                try
                {
                    if (published)
                        Directory.Move(target.Folder, stagedPlugin);
                    if (Directory.Exists(previous))
                        Directory.Move(previous, target.Folder);
                }
                catch (Exception rollback) when (KnownError(rollback))
                {
                    throw new InstallProblem("安装未完成，自动恢复遇到文件占用。原工程备份仍保存在安装报告所示目录。", inner: rollback);
                }
                if (error is UnauthorizedAccessException || error is SecurityException)
                    throw;
                throw new InstallProblem("安装未完成，已保留原工程和插件。请确认工程关闭且目录可写后重试。", inner: error);
            }
        }

        private static void RequireClosed(string project)
        {
            var running = new HashSet<int>();
            foreach (string name in new[] { "UnrealEditor", "UnrealEditor-Cmd" })
            foreach (Process process in Process.GetProcessesByName(name))
            {
                using (process) running.Add(process.Id);
            }
            if (running.Count == 0)
                return;
            if (project == null)
                throw new InstallProblem("请关闭 Unreal Editor 后重试。引擎插件更新期间请保持编辑器关闭。");

            string occupied = "请关闭目标工程的 Unreal Editor 后重试。";
            try
            {
                const string query = "SELECT ProcessId, CommandLine FROM Win32_Process WHERE Name='UnrealEditor.exe' OR Name='UnrealEditor-Cmd.exe'";
                var options = new EnumerationOptions { Timeout = TimeSpan.FromSeconds(3) };
                using (var search = new ManagementObjectSearcher(new ManagementScope(@"root\cimv2"), new ObjectQuery(query), options))
                using (ManagementObjectCollection rows = search.Get())
                foreach (ManagementBaseObject row in rows)
                {
                    using (row)
                    {
                        int id = Convert.ToInt32(row["ProcessId"]);
                        string opened = ProjectFromCommand(row["CommandLine"] as string);
                        if (!IsFullyQualified(opened) || Paths.Equals(FullPath(opened), project))
                            throw new InstallProblem(occupied);
                        running.Remove(id);
                    }
                }
            }
            catch (Exception error) when (error is ManagementException || error is COMException || error is UnauthorizedAccessException)
            {
                throw new InstallProblem(occupied + " 当前无法核实已打开的工程。", inner: error);
            }
            if (running.Count != 0)
                throw new InstallProblem(occupied + " 当前无法核实已打开的工程。");
        }

        private static string ProjectFromCommand(string command)
        {
            foreach (Match match in ProjectArguments.Matches(command ?? ""))
            {
                string value = match.Value.Replace("\"", "");
                if (value.StartsWith("-project=", StringComparison.OrdinalIgnoreCase))
                    value = value.Substring(9);
                if (value.EndsWith(".uproject", StringComparison.OrdinalIgnoreCase))
                    return value;
            }
            return "";
        }

        private static Dictionary<string, object> ReadObject(string path, string description)
        {
            RejectRedirect(path);
            return DecodeObject(File.ReadAllBytes(path), description);
        }

        private static Dictionary<string, object> DecodeObject(byte[] bytes, string description)
        {
            int offset = bytes.Length >= 3 && bytes[0] == 239 && bytes[1] == 187 && bytes[2] == 191 ? 3 : 0;
            Dictionary<string, object> decoded;
            try { decoded = Json().DeserializeObject(Utf8.GetString(bytes, offset, bytes.Length - offset)) as Dictionary<string, object>; }
            catch (Exception error) when (error is ArgumentException || error is InvalidOperationException)
            {
                throw new InstallProblem(description + "无法读取。请检查文件完整性。", inner: error);
            }
            if (decoded == null)
                throw new InstallProblem(description + "格式不受支持。");
            return decoded;
        }

        private static JavaScriptSerializer Json() { return new JavaScriptSerializer { MaxJsonLength = int.MaxValue }; }
        private static object Value(Dictionary<string, object> dictionary, string key)
        {
            object value;
            return dictionary.TryGetValue(key, out value) ? value : null;
        }
        private static string StringValue(Dictionary<string, object> dictionary, string key)
        {
            return Value(dictionary, key) as string ?? "";
        }
        private static bool IsTrue(object value) { return value is bool && (bool)value; }
        private static bool IsAssetForge(Dictionary<string, object> row) { return Paths.Equals(StringValue(row, "Name"), PluginName); }
        private static bool OwnsPlugin(string path) { return StringValue(ReadObject(path, "现有插件描述文件"), "FriendlyName") == "DCC AssetForge"; }

        private static string EditorExecutable(string root) { return Path.Combine(root, "Engine", "Binaries", "Win64", "UnrealEditor.exe"); }
        private static string MarketplacePath(string root) { return Path.Combine(root, "Engine", "Plugins", "Marketplace", PluginName); }
        private static bool HasEnginePlugin(string root)
        {
            return File.Exists(Path.Combine(MarketplacePath(root), PluginFile)) ||
                   File.Exists(Path.Combine(root, "Engine", "Plugins", PluginName, PluginFile));
        }
        private static string NormalizeEngineRoot(string path)
        {
            if (string.IsNullOrWhiteSpace(path))
                throw new InstallProblem("请选择要安装插件的 Unreal Engine。", true);
            string root = FullPath(path);
            return Paths.Equals(Path.GetFileName(root), "Engine") ? Path.GetDirectoryName(root) : root;
        }
        private static string FullPath(string path)
        {
            string full = Path.GetFullPath(path);
            return Paths.Equals(full, Path.GetPathRoot(full)) ? full : full.TrimEnd('\\', '/');
        }
        private static bool IsFullyQualified(string path)
        {
            return !string.IsNullOrEmpty(path) &&
                (path.Length >= 3 && path[1] == ':' && (path[2] == '\\' || path[2] == '/') || path.StartsWith(@"\\", StringComparison.Ordinal));
        }
        private static bool IsInside(string child, string parent)
        {
            return Paths.Equals(child, parent) ||
                child.StartsWith(parent.TrimEnd('\\', '/') + "\\", StringComparison.OrdinalIgnoreCase);
        }

        private static string[] Directories(string folder, string pattern)
        {
            try { return Directory.GetDirectories(folder, pattern); }
            catch (Exception error) when (KnownError(error)) { return new string[0]; }
        }

        private static IEnumerable<string> WalkFiles(string folder)
        {
            RejectRedirect(folder);
            foreach (string entry in Directory.EnumerateFileSystemEntries(folder))
            {
                FileAttributes flags = File.GetAttributes(entry);
                if ((flags & FileAttributes.ReparsePoint) != 0)
                    throw new InstallProblem("安装路径包含重定向目录或链接。请选择工程与安装包的实际路径。");
                if ((flags & FileAttributes.Directory) == 0)
                    yield return entry;
                else
                    foreach (string child in WalkFiles(entry))
                        yield return child;
            }
        }

        private static void RejectAncestors(string path)
        {
            for (string current = path; !string.IsNullOrEmpty(current); current = Path.GetDirectoryName(current))
                RejectRedirect(current);
        }

        private static void RejectRedirect(string path)
        {
            try
            {
                if ((File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0)
                    throw new InstallProblem("安装路径包含重定向目录或链接。请选择工程与安装包的实际路径。");
            }
            catch (FileNotFoundException) { }
            catch (DirectoryNotFoundException) { }
        }

        private static bool KnownError(Exception error)
        {
            return error is InstallProblem || error is IOException || error is ArgumentException ||
                   error is UnauthorizedAccessException || error is SecurityException || error is NotSupportedException;
        }

        private static string Explain(Exception error)
        {
            if (error is InstallProblem) return error.Message;
            if (error is UnauthorizedAccessException || error is SecurityException)
                return "无法读写插件目录。请关闭宿主软件并确认当前用户拥有目录权限。";
            if (error is PathTooLongException) return "安装路径过长。请将安装包或目标工程移到较短的目录后重试。";
            return "无法读取或写入安装所需文件。请检查工程、安装目录及剩余磁盘空间。";
        }

        private static void ResultError(UnrealResult result, Exception error)
        {
            result.Message = Explain(error);
            result.PermissionRequired = error is UnauthorizedAccessException || error is SecurityException;
        }
    }
}

