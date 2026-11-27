using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web.Script.Serialization;
using Microsoft.Win32;

namespace AssetForge.Setup
{
    internal sealed class HostOption
    {
        public string Label { get; set; }
        public string Executable { get; set; }
        public string Version { get; set; }
        public string TargetPath { get; set; }
        public string Message { get; set; }
        public bool Ready { get; set; }
        public bool Installed { get; set; }
    }

    internal sealed class HostInstaller
    {
        private readonly string distribution;
        private readonly JavaScriptSerializer json = new JavaScriptSerializer();
        private static readonly Encoding Utf8 = new UTF8Encoding(false);

        public HostInstaller(string distribution)
        {
            this.distribution = distribution;
        }

        public string MayaEntry { get { return Path.Combine(distribution, "Install_DCC_AssetForge_Maya.py"); } }
        public string BlenderArchive { get { return Path.Combine(distribution, "Payload", "Blender", "DCC-AssetForge-Blender-v0.2.0.zip"); } }

        public List<HostOption> DiscoverMaya()
        {
            var options = new List<HostOption>();
            foreach (int year in new[] { 2026, 2025, 2024, 2023, 2022, 2020 })
            {
                string key = @"SOFTWARE\Autodesk\Maya\" + year + @"\Setup\InstallPath";
                var roots = new[] { Registry.LocalMachine, Registry.CurrentUser }
                    .Select(hive => RegistryString(hive, key, "MAYA_INSTALL_LOCATION"))
                    .Concat(ProgramDirectories().Select(root => Path.Combine(root, "Autodesk", "Maya" + year)));
                string executable = roots.Where(root => !string.IsNullOrWhiteSpace(root))
                    .Select(root => Path.Combine(root, "bin", "maya.exe")).FirstOrDefault(File.Exists);
                if (executable != null)
                    options.Add(MayaOption(executable, year));
            }
            return options;
        }

        public HostOption ReadMaya(string executable)
        {
            string full = Path.GetFullPath(executable);
            if (!string.Equals(Path.GetFileName(full), "maya.exe", StringComparison.OrdinalIgnoreCase) || !File.Exists(full))
                throw new InvalidOperationException("请选择 Maya 安装目录中的 maya.exe。");
            var version = FileVersionInfo.GetVersionInfo(full);
            var match = Regex.Match(version.ProductVersion + " " + full, @"\b(?:Maya\s*)?(202[02-6])\b", RegexOptions.IgnoreCase);
            if (!match.Success)
                throw new InvalidOperationException("无法识别此 Maya 的版本。请在 Maya 中使用拖放安装。");
            return MayaOption(full, int.Parse(match.Groups[1].Value, CultureInfo.InvariantCulture));
        }

        private static HostOption MayaOption(string executable, int year)
        {
            string user = Environment.GetEnvironmentVariable("MAYA_APP_DIR");
            if (string.IsNullOrWhiteSpace(user))
                user = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments), "maya");
            string target = Path.Combine(user, year.ToString(CultureInfo.InvariantCulture));
            bool ready = year >= 2022 && year <= 2026;
            return new HostOption
            {
                Label = "Maya " + year + "     " + Path.GetDirectoryName(Path.GetDirectoryName(executable)),
                Executable = executable,
                Version = year.ToString(CultureInfo.InvariantCulture),
                TargetPath = target,
                Message = ready ? "会打开此 Maya 更新工具架和模块。" : "Maya 2020 使用 Python 2。请选择 Maya 2022–2026。",
                Ready = ready,
                Installed = ready && File.Exists(Path.Combine(target, "modules", "DCC_AssetForge_Local.mod"))
            };
        }

        public List<HostOption> DiscoverBlender()
        {
            var paths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var hive in new[] { Registry.LocalMachine, Registry.CurrentUser })
            {
                foreach (string prefix in new[] { "SOFTWARE", @"SOFTWARE\WOW6432Node" })
                {
                    string uninstall = prefix + @"\Microsoft\Windows\CurrentVersion\Uninstall";
                    using (var key = hive.OpenSubKey(uninstall))
                    {
                        if (key == null) continue;
                        foreach (string name in key.GetSubKeyNames())
                        {
                            using (var item = key.OpenSubKey(name))
                            {
                                if (item == null || !Convert.ToString(item.GetValue("DisplayName")).StartsWith("Blender", StringComparison.OrdinalIgnoreCase))
                                    continue;
                                string root = Convert.ToString(item.GetValue("InstallLocation"));
                                if (!string.IsNullOrWhiteSpace(root)) paths.Add(Path.Combine(root.Trim('"'), "blender.exe"));
                            }
                        }
                    }
                }
                string appPath = RegistryString(hive, @"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\blender.exe", "");
                if (!string.IsNullOrWhiteSpace(appPath)) paths.Add(appPath.Trim('"'));
            }
            foreach (string root in ProgramDirectories())
            {
                foreach (string prefix in new[] { "Blender Foundation", @"Programs\Blender Foundation" })
                {
                    string folder = Path.Combine(root, prefix);
                    if (Directory.Exists(folder))
                        foreach (string item in Directory.EnumerateDirectories(folder))
                            paths.Add(Path.Combine(item, "blender.exe"));
                }
            }
            foreach (string folder in (Environment.GetEnvironmentVariable("PATH") ?? "").Split(';'))
                if (folder.Trim().Length > 0) paths.Add(Path.Combine(folder.Trim().Trim('"'), "blender.exe"));

            var found = new List<HostOption>();
            foreach (string file in paths.Where(File.Exists).OrderBy(path => path, StringComparer.OrdinalIgnoreCase))
            {
                try { found.Add(ReadBlender(file)); }
                catch (InvalidOperationException) { /* Unsupported or stale executable. */ }
            }
            return found;
        }

        public HostOption ReadBlender(string executable)
        {
            string full = Path.GetFullPath(executable);
            if (!string.Equals(Path.GetFileName(full), "blender.exe", StringComparison.OrdinalIgnoreCase) || !File.Exists(full))
                throw new InvalidOperationException("请选择 Blender 安装目录中的 blender.exe。");
            var output = Run(full, 10, "--version");
            var match = Regex.Match(output.Text, @"(?m)^Blender (\d+)\.(\d+)(?:\.(\d+))?");
            if (output.Code != 0 || !match.Success)
                throw new InvalidOperationException("无法确认 Blender 版本。请重新选择程序。");
            int major = int.Parse(match.Groups[1].Value, CultureInfo.InvariantCulture);
            int minor = int.Parse(match.Groups[2].Value, CultureInfo.InvariantCulture);
            string version = major + "." + minor + "." + (match.Groups[3].Success ? match.Groups[3].Value : "0");
            var option = new HostOption
            {
                Label = "Blender " + version + "     " + Path.GetDirectoryName(full),
                Executable = full,
                Version = version,
                Message = "此扩展需要 Blender 4.2 LTS 至 5.x。"
            };
            if (major == 5 || major == 4 && minor >= 2)
            {
                try
                {
                    var profile = BlenderProfile(full);
                    option.Ready = true;
                    option.TargetPath = Path.Combine(profile.Repository, "asset_forge");
                    option.Installed = File.Exists(Path.Combine(option.TargetPath, "blender_manifest.toml"));
                    option.Message = option.Installed ? "本地扩展已安装。" : "将写入 Blender 的本地扩展库。";
                }
                catch (InvalidOperationException error) { option.Message = error.Message; }
            }
            return option;
        }

        public string UpdateMaya(HostOption option, bool remove)
        {
            if (!option.Ready)
                throw new InvalidOperationException("请选择 Maya 2022–2026。");
            DemandClosed("maya", "请保存并关闭当前 Maya，再继续。");
            string payload = Path.Combine(distribution, "Payload", "Maya");
            if (!File.Exists(MayaEntry) || (!remove && !File.Exists(Path.Combine(payload, "_assetforge_payload.json"))))
                throw new InvalidOperationException("未找到 Maya 安装文件。请先完整解压发行 ZIP。");
            string temp = Path.Combine(Path.GetTempPath(), "AssetForge-Maya-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(temp);
            try
            {
                string receipt = Path.Combine(temp, "result.json");
                string command = "import runpy, json; from pathlib import Path; from maya import cmds\n"
                    + "out = Path(" + PythonLiteral(receipt) + ")\n"
                    + "try:\n    actions = runpy.run_path(" + PythonLiteral(MayaEntry) + ")\n"
                    + (remove ? "    result = actions['uninstall'](cmds)\n" : "    result = actions['install'](" + PythonLiteral(payload) + ", cmds)\n")
                    + "    cmds.savePrefs(general=True)\n    result['status'] = 'success'\n"
                    + "except (OSError, RuntimeError, ValueError) as error:\n    result = dict(status='error', message=str(error))\n"
                    + "temp = out.with_suffix('.tmp')\ntemp.write_text(json.dumps(result), encoding='utf-8')\ntemp.replace(out)\n";
                string script = Path.Combine(temp, "setup.mel");
                string deferred = "from maya.utils import executeDeferred; executeDeferred(" + PythonLiteral(command) + ")";
                File.WriteAllText(script, "python(\"" + deferred.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\");\n", Encoding.ASCII);
                using (var maya = Process.Start(new ProcessStartInfo(option.Executable, Arguments("-script", script)) { UseShellExecute = false }))
                {
                    var clock = Stopwatch.StartNew();
                    while (clock.Elapsed.TotalSeconds < 150)
                    {
                        if (File.Exists(receipt))
                        {
                            var row = json.Deserialize<Dictionary<string, object>>(File.ReadAllText(receipt, Utf8));
                            if (Field(row, "status") != "success")
                                throw new InvalidOperationException(Nonempty(Field(row, "message"), "Maya 未能完成操作。"));
                            return (remove ? "已移除 Maya 工具架按钮和模块入口。" : "Maya 安装完成。在 AssetForge 工具架点击 AF 图标。")
                                + BackupNote(Field(row, "backup"));
                        }
                        if (maya.HasExited)
                            throw new InvalidOperationException("Maya 在更新完成前已关闭。请确认它能正常打开。");
                        Thread.Sleep(250);
                    }
                }
                throw new InvalidOperationException("Maya 未返回安装结果。请检查许可或启动提示。");
            }
            finally
            {
                try { Directory.Delete(temp, true); }
                catch (IOException) { Trace.WriteLine("Could not remove the completed Maya setup receipt directory."); }
                catch (UnauthorizedAccessException) { Trace.WriteLine("Could not remove the completed Maya setup receipt directory."); }
            }
        }

        public string UpdateBlender(HostOption option, bool remove)
        {
            DemandClosed("blender", "请保存并关闭 Blender，再更新扩展。");
            if (!remove && !File.Exists(BlenderArchive))
                throw new InvalidOperationException("未找到 Blender 扩展 ZIP。请完整解压发行 ZIP。");
            var profile = BlenderProfile(option.Executable);
            string target = Path.Combine(Path.GetFullPath(profile.Repository), "asset_forge");
            string prefs = Path.GetFullPath(profile.Preferences);
            string preference = Path.Combine(prefs, "userpref.blend");
            RejectRedirect(target);
            RejectRedirect(preference);
            if (File.Exists(target))
                throw new InvalidOperationException("Blender 扩展目录已被文件占用。");
            string marker = Path.Combine(target, "blender_manifest.toml");
            bool installed = Directory.Exists(target);
            if (installed && (!File.Exists(marker) || !File.ReadLines(marker, Utf8).Contains("id = \"asset_forge\"")
                || !File.ReadLines(marker, Utf8).Contains("name = \"DCC AssetForge\"")))
                throw new InvalidOperationException("扩展目录已有同名文件。为保护现有内容，操作未执行。");
            if (remove && !installed)
                throw new InvalidOperationException("此 Blender 的默认扩展库中未安装 DCC AssetForge。");

            string backup = "";
            if (installed || File.Exists(preference))
            {
                backup = Path.Combine(prefs, "DCC AssetForge", "InstallerBackups", "prior-" + Guid.NewGuid().ToString("N"));
                RejectRedirect(Path.GetDirectoryName(backup));
                Directory.CreateDirectory(backup);
                if (installed) CopyDirectory(target, Path.Combine(backup, "asset_forge"));
                if (File.Exists(preference)) File.Copy(preference, Path.Combine(backup, "userpref.blend"));
            }
            DemandClosed("blender", "Blender 已打开。请保存并关闭后重试。");
            try
            {
                var action = remove ? Run(option.Executable, 90, "--offline-mode", "--command", "extension", "remove", "user_default.asset_forge")
                    : Run(option.Executable, 90, "--offline-mode", "--command", "extension", "install-file", "--repo", "user_default", "--enable", BlenderArchive);
                var after = BlenderProfile(option.Executable);
                if (action.Code != 0 || after.Enabled == remove || Directory.Exists(target) == remove)
                    throw new InvalidOperationException("Blender 未能完成扩展操作。也可以在偏好设置中从磁盘安装或卸载。");
            }
            catch (Exception error) when (error is IOException || error is InvalidOperationException || error is UnauthorizedAccessException)
            {
                try
                {
                    RejectRedirect(target);
                    RejectRedirect(preference);
                    if (Directory.Exists(target)) Directory.Delete(target, true);
                    if (backup.Length > 0 && Directory.Exists(Path.Combine(backup, "asset_forge")))
                        CopyDirectory(Path.Combine(backup, "asset_forge"), target);
                    if (backup.Length > 0 && File.Exists(Path.Combine(backup, "userpref.blend")))
                        ReplaceFile(Path.Combine(backup, "userpref.blend"), preference);
                    else if (File.Exists(preference))
                        File.Delete(preference);
                }
                catch (Exception rollback) when (rollback is IOException || rollback is InvalidOperationException || rollback is UnauthorizedAccessException)
                {
                    throw new InvalidOperationException("Blender 更新失败，自动恢复未完成。" + BackupNote(backup), rollback);
                }
                throw new InvalidOperationException(error.Message + BackupNote(backup), error);
            }
            return (remove ? "已卸载 Blender 扩展。" : "Blender 扩展已安装。在 3D 视图按 N 查找 DCC AssetForge。") + BackupNote(backup);
        }

        private sealed class Profile
        {
            public string Repository;
            public string Preferences;
            public bool Enabled;
        }

        private Profile BlenderProfile(string executable)
        {
            const string script = "import bpy,json; r=next((x for x in bpy.context.preferences.extensions.repos if x.module=='user_default'), None); "
                + "print('ASSETFORGE_PROFILE '+json.dumps(dict(repo=r.directory if r else '', "
                + "prefs=bpy.utils.user_resource('CONFIG'), enabled='bl_ext.user_default.asset_forge' in bpy.context.preferences.addons)))";
            var output = Run(executable, 20, "--background", "--offline-mode", "--disable-autoexec", "--python-expr", script);
            const string prefix = "ASSETFORGE_PROFILE ";
            string line = output.Text.Split('\n').FirstOrDefault(row => row.StartsWith(prefix, StringComparison.Ordinal));
            if (output.Code != 0 || line == null)
                throw new InvalidOperationException("无法读取 Blender 本地扩展库。可在偏好设置中从磁盘安装。");
            Dictionary<string, object> result;
            try { result = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(line.Substring(prefix.Length)); }
            catch (ArgumentException error) { throw new InvalidOperationException("Blender 返回的扩展库信息无法读取。", error); }
            var profile = new Profile { Repository = Field(result, "repo"), Preferences = Field(result, "prefs") };
            object enabled;
            profile.Enabled = result.TryGetValue("enabled", out enabled) && enabled is bool && (bool)enabled;
            if (profile.Repository.Length == 0 || profile.Preferences.Length == 0)
                throw new InvalidOperationException("未找到 Blender 的默认本地扩展库。请在偏好设置中检查。");
            return profile;
        }

        internal static bool Running(string image)
        {
            var processes = Process.GetProcessesByName(image);
            try { return processes.Length != 0; }
            finally { foreach (var process in processes) process.Dispose(); }
        }

        private static void DemandClosed(string image, string message)
        {
            if (Running(image)) throw new InvalidOperationException(message);
        }

        private static IEnumerable<string> ProgramDirectories()
        {
            return new[] { "ProgramW6432", "ProgramFiles", "LOCALAPPDATA" }
                .Select(Environment.GetEnvironmentVariable).Where(path => !string.IsNullOrWhiteSpace(path))
                .Distinct(StringComparer.OrdinalIgnoreCase);
        }

        private static string RegistryString(RegistryKey hive, string path, string name)
        {
            using (var key = hive.OpenSubKey(path))
                return key == null ? "" : Convert.ToString(key.GetValue(name));
        }

        private static void RejectRedirect(string path)
        {
            if ((File.Exists(path) || Directory.Exists(path)) && (File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0)
                throw new InvalidOperationException("扩展目录或配置使用目录链接。为保护现有内容，操作未执行。");
        }

        private static void CopyDirectory(string source, string destination)
        {
            RejectRedirect(source);
            Directory.CreateDirectory(destination);
            foreach (string file in Directory.EnumerateFiles(source))
            {
                RejectRedirect(file);
                File.Copy(file, Path.Combine(destination, Path.GetFileName(file)));
            }
            foreach (string folder in Directory.EnumerateDirectories(source))
                CopyDirectory(folder, Path.Combine(destination, Path.GetFileName(folder)));
        }

        private static void ReplaceFile(string source, string destination)
        {
            string stage = destination + ".AssetForge-" + Guid.NewGuid().ToString("N");
            File.Copy(source, stage);
            try
            {
                if (File.Exists(destination)) File.Replace(stage, destination, null);
                else File.Move(stage, destination);
            }
            finally { if (File.Exists(stage)) File.Delete(stage); }
        }

        private sealed class Output
        {
            public int Code;
            public string Text;
        }

        private static Output Run(string executable, int timeout, params string[] args)
        {
            try
            {
                using (var process = Process.Start(new ProcessStartInfo(executable, Arguments(args))
                {
                    UseShellExecute = false, CreateNoWindow = true,
                    RedirectStandardOutput = true, RedirectStandardError = true,
                    StandardOutputEncoding = Utf8, StandardErrorEncoding = Utf8
                }))
                {
                    var reading = process.StandardOutput.ReadToEndAsync();
                    var readingError = process.StandardError.ReadToEndAsync();
                    if (!process.WaitForExit(timeout * 1000))
                    {
                        if (!process.HasExited) process.Kill();
                        throw new InvalidOperationException("宿主软件响应超时。请确认它能够正常打开。");
                    }
                    return new Output { Code = process.ExitCode, Text = reading.GetAwaiter().GetResult() + "\n" + readingError.GetAwaiter().GetResult() };
                }
            }
            catch (Win32Exception error) { throw new InvalidOperationException("无法启动所选宿主。请重新选择程序。", error); }
        }

        internal static string Arguments(params string[] args)
        {
            return string.Join(" ", args.Select(argument =>
                "\"" + Regex.Replace(Regex.Replace(argument, @"(\\*)""", "$1$1\\\""), @"(\\+)$", "$1$1") + "\""));
        }

        private static string PythonLiteral(string value)
        {
            var literal = new StringBuilder("'");
            for (int index = 0; index < value.Length; index++)
            {
                char item = value[index];
                if (item == '\\' || item == '\'') literal.Append('\\').Append(item);
                else if (item < 32 || item > 126)
                {
                    if (char.IsSurrogatePair(value, index))
                    {
                        literal.Append("\\U").Append(char.ConvertToUtf32(value, index).ToString("X8", CultureInfo.InvariantCulture));
                        index++;
                    }
                    else literal.Append("\\u").Append(((int)item).ToString("X4", CultureInfo.InvariantCulture));
                }
                else literal.Append(item);
            }
            return literal.Append('\'').ToString();
        }

        private static string Field(Dictionary<string, object> values, string name)
        {
            object value;
            return values != null && values.TryGetValue(name, out value) ? Convert.ToString(value, CultureInfo.InvariantCulture) : "";
        }

        private static string Nonempty(string value, string fallback) { return string.IsNullOrWhiteSpace(value) ? fallback : value; }
        private static string BackupNote(string path) { return string.IsNullOrEmpty(path) ? "" : "  备份位置：" + path; }
    }
}
