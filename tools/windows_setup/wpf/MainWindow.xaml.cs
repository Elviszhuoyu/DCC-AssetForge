using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using Microsoft.Win32;
using Forms = System.Windows.Forms;

namespace AssetForge.Setup
{
    public partial class MainWindow : Window
    {
        private readonly string distribution = App.Distribution;
        private HostInstaller hosts;
        private UnrealInstaller unreal;
        private readonly Dictionary<string, ProjectOption> manualProjects = new Dictionary<string, ProjectOption>(StringComparer.OrdinalIgnoreCase);
        private readonly Dictionary<string, UnrealEngine> manualEngines = new Dictionary<string, UnrealEngine>(StringComparer.OrdinalIgnoreCase);
        private readonly Dictionary<string, string> projectOverrides = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        private readonly List<string> mayaExecutables = new List<string>();
        private readonly List<string> blenderExecutables = new List<string>();
        private List<EngineOption> engines = new List<EngineOption>();
        private List<ProjectOption> projects = new List<ProjectOption>();
        private List<HostOption> mayas = new List<HostOption>();
        private List<HostOption> blenders = new List<HostOption>();
        private bool initialized;
        private bool busy = true;
        private bool changingSystem;
        private bool mayaRunning;
        private bool blenderRunning;
        private string unrealOccupancy = "";
        private string busyMessage = "正在查找本机软件…";
        private string notice = "";
        private string extractionNotice;
        private bool holdSelections;
        private BitmapFrame[] headerBadgeFrames;
        private IntPtr startupWindow;
        private DispatcherTimer revealTimeout;

        public MainWindow()
        {
            InitializeComponent();
            initialized = true;
            extractionNotice = ExtractionNotice(distribution);
            SourceInitialized += (_, __) =>
            {
                PrepareFirstFrame();
                var source = (HwndSource)PresentationSource.FromVisual(this);
                if (source != null && source.CompositionTarget != null)
                    source.CompositionTarget.BackgroundColor = Color.FromRgb(20, 20, 20);
                ApplyDarkCaption(this);
                SetHeaderBadge(VisualTreeHelper.GetDpi(this));
            };
            DpiChanged += (_, args) => SetHeaderBadge(args.NewDpi);
            ContentRendered += FirstRender;
            Closing += (_, args) => { args.Cancel = changingSystem; };
            RenderSelection();
        }

        private void SetHeaderBadge(DpiScale dpi)
        {
            if (headerBadgeFrames == null)
            {
                // Image's default ICO converter chooses the smallest frame regardless of its display size.
                var image = new IconBitmapDecoder(new Uri("pack://application:,,,/AssetForge.ico"),
                    BitmapCreateOptions.PreservePixelFormat, BitmapCacheOption.OnLoad);
                headerBadgeFrames = image.Frames.OrderBy(frame => frame.PixelWidth).ToArray();
            }

            int pixels = (int)Math.Ceiling(HeaderBadge.Width * dpi.DpiScaleX);
            HeaderBadge.Source = headerBadgeFrames.FirstOrDefault(frame => frame.PixelWidth >= pixels)
                ?? headerBadgeFrames[headerBadgeFrames.Length - 1];
        }

        private void PrepareFirstFrame()
        {
            const int cloakAttribute = 13;
            IntPtr handle = new WindowInteropHelper(this).Handle;
            int cloak = 1;
            // Compose the first WPF frame before exposing the native window's default client background.
            if (DwmSetWindowAttribute(handle, cloakAttribute, ref cloak, sizeof(int)) != 0)
                return;
            startupWindow = handle;
            revealTimeout = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1) };
            revealTimeout.Tick += (_, __) => RevealFirstFrame();
            revealTimeout.Start();
        }

        private void RevealFirstFrame()
        {
            if (revealTimeout != null)
                revealTimeout.Stop();
            if (startupWindow == IntPtr.Zero)
                return;
            const int cloakAttribute = 13;
            int cloak = 0;
            DwmSetWindowAttribute(startupWindow, cloakAttribute, ref cloak, sizeof(int));
            startupWindow = IntPtr.Zero;
        }

        private async void FirstRender(object sender, EventArgs e)
        {
            ContentRendered -= FirstRender;
            AutomationProperties.SetHelpText(this, "WPF Render Tier " + (RenderCapability.Tier >> 16));
            await Dispatcher.Yield(DispatcherPriority.ApplicationIdle);
            if (startupWindow != IntPtr.Zero)
                DwmFlush();
            RevealFirstFrame();
            await Work(busyMessage, false, ProbeAll);
        }

        private sealed class EngineOption
        {
            public UnrealEngine Engine { get; set; }
            public UnrealPlan Plan { get; set; }
            public string Name { get { return "UE " + Engine.Version; } }
            public string Path { get { return Engine.Root; } }
            public string Badge { get { return Plan.Ready ? "预编译直装" : Plan.SourceAvailable ? "源码安装" : "暂无匹配"; } }
            public bool IsSelected { get; set; }
            public bool IsEnabled { get { return Plan.Ready || Plan.CanUninstall; } }
        }

        private sealed class ProjectOption
        {
            public string File;
            public string Override;
            public UnrealPlan Binary;
            public UnrealPlan Source;
            public string Label { get { return Path.GetFileNameWithoutExtension(File) + "     " + Path.GetDirectoryName(File); } }
        }

        private sealed class UnrealSnapshot
        {
            public List<EngineOption> Engines;
            public List<ProjectOption> Projects;
            public string Occupancy;
        }

        private ProjectOption ReadProject(string file, string engine = null)
        {
            var plan = unreal.Plan(file, engine);
            return new ProjectOption
            {
                File = file, Override = engine, Binary = plan,
                Source = plan.Ready || plan.SourceAvailable ? unreal.Plan(file, engine, source: true) : plan
            };
        }

        private async Task Refresh()
        {
            if (busy) return;
            await Work("正在查找本机软件…", false, ProbeAll);
        }

        private async Task ProbeAll()
        {
            if (hosts == null)
            {
                var services = await Task.Run(() => Tuple.Create(new HostInstaller(distribution), App.Unreal()));
                hosts = services.Item1;
                unreal = services.Item2;
            }
            string selectedProject = (ProjectCombo.SelectedItem as ProjectOption)?.File;
            string selectedMaya = (MayaCombo.SelectedItem as HostOption)?.Executable;
            string selectedBlender = (BlenderCombo.SelectedItem as HostOption)?.Executable;
            var selectedEngines = new HashSet<string>(engines.Where(item => item.IsSelected).Select(item => item.Path), StringComparer.OrdinalIgnoreCase);
            var extraEngines = manualEngines.Values.ToArray();
            var extraProjects = manualProjects.Keys.ToArray();
            var overrides = projectOverrides.ToDictionary(item => item.Key, item => item.Value, StringComparer.OrdinalIgnoreCase);
            var externalMaya = mayaExecutables.ToArray();
            var externalBlender = blenderExecutables.ToArray();

            var ueTask = Task.Run(() =>
            {
                var detected = unreal.DiscoverEngines().Concat(extraEngines)
                    .GroupBy(item => item.Root, StringComparer.OrdinalIgnoreCase).Select(group => group.First()).ToList();
                var engineRows = detected.Select(engine => new EngineOption
                {
                    Engine = engine, Plan = unreal.Plan(engineRoot: engine.Root, engineInstall: true),
                    IsSelected = selectedEngines.Contains(engine.Root)
                }).ToList();
                if (!engineRows.Any(row => row.IsSelected))
                {
                    var first = engineRows.FirstOrDefault(row => row.IsEnabled);
                    if (first != null) first.IsSelected = true;
                }
                var projectRows = unreal.DiscoverProjects(detected).Concat(extraProjects)
                    .Distinct(StringComparer.OrdinalIgnoreCase).Select(file =>
                    {
                        string engine;
                        return ReadProject(file, overrides.TryGetValue(file, out engine) ? engine : null);
                    }).ToList();
                return new UnrealSnapshot { Engines = engineRows, Projects = projectRows, Occupancy = unreal.OccupancyMessage() };
            });
            var mayaTask = Task.Run(() =>
            {
                var found = hosts.DiscoverMaya();
                foreach (string executable in externalMaya.Where(item => !found.Any(option => Same(option.Executable, item))))
                    if (File.Exists(executable)) found.Add(hosts.ReadMaya(executable));
                return Tuple.Create(found, HostInstaller.Running("maya"));
            });
            var blenderTask = Task.Run(() =>
            {
                var found = hosts.DiscoverBlender();
                foreach (string executable in externalBlender.Where(item => !found.Any(option => Same(option.Executable, item))))
                    if (File.Exists(executable)) found.Add(hosts.ReadBlender(executable));
                return Tuple.Create(found, HostInstaller.Running("blender"));
            });

            await Task.WhenAll(ueTask, mayaTask, blenderTask);
            engines = ueTask.Result.Engines;
            projects = ueTask.Result.Projects;
            unrealOccupancy = ueTask.Result.Occupancy ?? "";
            mayas = mayaTask.Result.Item1;
            mayaRunning = mayaTask.Result.Item2;
            blenders = blenderTask.Result.Item1;
            blenderRunning = blenderTask.Result.Item2;

            holdSelections = true;
            try
            {
                EngineList.ItemsSource = engines;
                ProjectCombo.ItemsSource = projects;
                ProjectCombo.SelectedItem = projects.FirstOrDefault(item => Same(item.File, selectedProject));
                MayaCombo.ItemsSource = mayas;
                MayaCombo.SelectedItem = mayas.FirstOrDefault(item => Same(item.Executable, selectedMaya))
                    ?? mayas.FirstOrDefault(item => item.Ready) ?? mayas.FirstOrDefault();
                BlenderCombo.ItemsSource = blenders;
                BlenderCombo.SelectedItem = blenders.FirstOrDefault(item => Same(item.Executable, selectedBlender))
                    ?? blenders.FirstOrDefault(item => item.Ready) ?? blenders.FirstOrDefault();
            }
            finally { holdSelections = false; }
        }

        private void SelectionChanged(object sender, RoutedEventArgs e)
        {
            if (!initialized || holdSelections) return;
            if (ReferenceEquals(sender, ProjectCombo))
            {
                holdSelections = true;
                SourceCheck.IsChecked = false;
                holdSelections = false;
            }
            notice = "";
            RenderSelection();
        }

        private void RenderSelection()
        {
            if (!initialized) return;
            bool install = false;
            bool remove = false;
            string issue = extractionNotice;
            var project = ProjectCombo.SelectedItem as ProjectOption;
            UnrealPlan plan = project == null ? null : SourceCheck.IsChecked == true ? project.Source : project.Binary;

            if (TabUnreal.IsChecked == true)
            {
                bool isProject = ModeProject.IsChecked == true;
                if (!isProject)
                {
                    var selected = engines.Where(item => item.IsSelected).ToArray();
                    SetText(UeTargetText, selected.Length == 0 ? "请选择要安装或卸载的引擎。"
                        : string.Join("  ·  ", selected.Select(item => item.Plan.TargetPath)));
                    install = selected.Length > 0 && selected.All(item => item.Plan.Ready);
                    remove = selected.Any(item => item.Plan.CanUninstall);
                    if (!string.IsNullOrWhiteSpace(unrealOccupancy))
                        issue = unrealOccupancy;
                    else if (!install && selected.Length > 0)
                        issue = selected[0].Plan.Message;
                    else if (engines.Count == 0 && !busy)
                        issue = "暂未检测到 UE。可使用「查找引擎文件夹」。";
                }
                else
                {
                    SetText(UeTargetText, plan == null || string.IsNullOrEmpty(plan.TargetPath)
                        ? "请选择 .uproject 工程文件。" : plan.TargetPath);
                    if (plan != null)
                    {
                        install = plan.Ready && !plan.EngineLevelConflict;
                        remove = plan.CanUninstall;
                        if (plan.EngineLevelConflict)
                            issue = plan.ConflictMessage;
                        else if (!string.IsNullOrWhiteSpace(unrealOccupancy))
                            issue = unrealOccupancy;
                        else if (!plan.Ready)
                            issue = plan.Message;
                        else if (string.IsNullOrEmpty(issue))
                            issue = "UE " + plan.EngineVersion + "  ·  " + (plan.PayloadMode == "source" ? "源码安装" : "预编译直装");
                    }
                }
                if (!string.IsNullOrWhiteSpace(unrealOccupancy)) install = remove = false;
            }
            else
            {
                bool maya = TabMaya.IsChecked == true;
                var option = (maya ? MayaCombo.SelectedItem : BlenderCombo.SelectedItem) as HostOption;
                bool occupied = maya ? mayaRunning : blenderRunning;
                SetText(maya ? MayaTargetText : BlenderTargetText,
                    option != null && !string.IsNullOrEmpty(option.TargetPath) ? option.TargetPath : "请选择已经安装的软件版本。");
                install = option != null && option.Ready && !occupied;
                remove = install && option.Installed;
                if (occupied)
                    issue = maya ? "请先保存并关闭 Maya，再点击「刷新检测」。" : "请先保存并关闭 Blender，再点击「刷新检测」。";
                else if (option != null && (string.IsNullOrEmpty(issue) || !option.Ready))
                    issue = option.Message;
            }

            SourceCheck.IsEnabled = !busy && project != null && (project.Binary.SourceAvailable || project.Source.Ready);
            FindProjectEngineButton.IsEnabled = !busy && project != null && (project.Binary.NeedsEngineRoot || !string.IsNullOrEmpty(project.Override));
            InstallButton.IsEnabled = !busy && install;
            UninstallButton.IsEnabled = !busy && remove;
            foreach (var control in new[] { FindEngineButton, FindProjectButton, FindMayaButton, FindBlenderButton, RefreshButton })
                control.IsEnabled = !busy;
            SetText(StatusText, busy ? busyMessage : !string.IsNullOrEmpty(notice) ? notice : !string.IsNullOrEmpty(issue) ? issue : "请选择要安装的软件和位置。");
        }

        private static void SetText(TextBlock control, string text)
        {
            if (control.Text == text) return;
            control.Text = text;
            control.ToolTip = text;
        }

        private async void ActionClick(object sender, RoutedEventArgs e)
        {
            if (!initialized || !(sender is FrameworkElement)) return;
            string action = ((FrameworkElement)sender).Name;
            if (action == "GuideButton") { ShowGuide(); return; }
            if (action == "MayaFallbackButton" || action == "BlenderFallbackButton")
            {
                Reveal(action == "MayaFallbackButton" ? Path.Combine(distribution, "Install_DCC_AssetForge_Maya.py")
                    : Path.Combine(distribution, "Payload", "Blender", "DCC-AssetForge-Blender-v0.2.0.zip"));
                return;
            }
            if (busy) return;
            switch (action)
            {
                case "RefreshButton": await Refresh(); break;
                case "FindEngineButton": await ChooseEngine(false); break;
                case "FindProjectEngineButton": await ChooseEngine(true); break;
                case "FindProjectButton": await ChooseProject(); break;
                case "FindMayaButton": await ChooseHost(true); break;
                case "FindBlenderButton": await ChooseHost(false); break;
                case "InstallButton": await Apply(false); break;
                case "UninstallButton": await Apply(true); break;
            }
        }

        private async Task ChooseEngine(bool forProject)
        {
            var project = ProjectCombo.SelectedItem as ProjectOption;
            if (forProject && project == null) return;
            using (var picker = new Forms.FolderBrowserDialog { Description = "选择包含 Engine 文件夹的 Unreal 安装目录", ShowNewFolderButton = false })
            {
                if (picker.ShowDialog(new DialogOwner(new WindowInteropHelper(this).Handle)) != Forms.DialogResult.OK) return;
                string folder = picker.SelectedPath;
                await Work("正在读取引擎版本…", false, async () =>
                {
                    var engine = await Task.Run(() => unreal.ReadEngine(folder));
                    if (forProject) projectOverrides[project.File] = engine.Root;
                    else manualEngines[engine.Root] = engine;
                    await ProbeAll();
                    if (!forProject)
                    {
                        var selected = engines.FirstOrDefault(row => Same(row.Path, engine.Root));
                        if (selected != null)
                        {
                            selected.IsSelected = selected.IsEnabled;
                            EngineList.ItemsSource = null;
                            EngineList.ItemsSource = engines;
                        }
                    }
                    notice = "已选择 UE " + engine.Version + "。";
                });
            }
        }

        private async Task ChooseProject()
        {
            var picker = new OpenFileDialog { Title = "选择 Unreal 工程文件", Filter = "Unreal 工程 (*.uproject)|*.uproject", CheckFileExists = true };
            if (picker.ShowDialog(this) != true) return;
            string file = picker.FileName;
            await Work("正在核对工程和关联引擎…", false, async () =>
            {
                var project = await Task.Run(() => ReadProject(file));
                var previous = projects.FirstOrDefault(row => Same(row.File, file));
                manualProjects[file] = project;
                projectOverrides.Remove(file);
                if (previous != null) projects.Remove(previous);
                projects.Insert(0, project);
                ProjectCombo.ItemsSource = null;
                ProjectCombo.ItemsSource = projects;
                ProjectCombo.SelectedItem = project;
                notice = "已选择 Unreal 工程。";
            });
        }

        private async Task ChooseHost(bool maya)
        {
            string name = maya ? "maya.exe" : "blender.exe";
            var picker = new OpenFileDialog { Title = "选择 " + (maya ? "Maya" : "Blender") + " 程序", Filter = name + "|" + name, CheckFileExists = true };
            if (picker.ShowDialog(this) != true) return;
            string file = picker.FileName;
            await Work("正在读取软件版本…", false, async () =>
            {
                var found = await Task.Run(() => maya ? hosts.ReadMaya(file) : hosts.ReadBlender(file));
                var list = maya ? mayas : blenders;
                list.RemoveAll(option => Same(option.Executable, found.Executable));
                list.Insert(0, found);
                (maya ? mayaExecutables : blenderExecutables).Add(file);
                var choices = maya ? MayaCombo : BlenderCombo;
                choices.ItemsSource = null;
                choices.ItemsSource = list;
                choices.SelectedItem = found;
                notice = "已选择 " + found.Version + "。";
            });
        }

        private async Task Apply(bool remove)
        {
            string label = remove ? "卸载" : "安装";
            string detail;
            Func<string> action;
            if (TabUnreal.IsChecked == true && ModeProject.IsChecked != true)
            {
                var selected = engines.Where(item => item.IsSelected && (!remove || item.Plan.CanUninstall)).ToArray();
                if (selected.Length == 0) return;
                detail = string.Join("\n", selected.Select(item => item.Plan.TargetPath)) + "\n\n"
                    + (remove ? "请先在使用该引擎的工程中禁用 DCC AssetForge。" : "更新会保留原有预设并备份现有版本。");
                action = () => string.Join("  ", selected.Select(item =>
                {
                    var result = remove ? unreal.Uninstall(engineRoot: item.Path, engineInstall: true)
                        : unreal.Install(engineRoot: item.Path, engineInstall: true);
                    return result.PermissionRequired ? Elevate(item.Path, remove) : ResultMessage(result);
                }));
            }
            else if (TabUnreal.IsChecked == true)
            {
                var project = ProjectCombo.SelectedItem as ProjectOption;
                if (project == null) return;
                bool source = SourceCheck.IsChecked == true;
                detail = project.File + "\n\n"
                    + (remove ? "会备份工程文件，移除插件并清理工程里的启用记录。"
                        : source ? "会安装插件源码。下次打开 Unreal 时按提示编译。"
                        : "会备份工程文件，为此工程启用 DCC AssetForge。");
                action = () => ResultMessage(remove ? unreal.Uninstall(project.File, project.Override)
                    : unreal.Install(project.File, project.Override, source: source));
            }
            else
            {
                bool maya = TabMaya.IsChecked == true;
                var option = (maya ? MayaCombo.SelectedItem : BlenderCombo.SelectedItem) as HostOption;
                if (option == null) return;
                detail = option.Label + "\n\n" + (maya ? "请先关闭 Maya。安装助手会打开此版本以更新工具架。"
                    : "请先关闭 Blender。更新前会备份扩展和配置。");
                action = () => maya ? hosts.UpdateMaya(option, remove) : hosts.UpdateBlender(option, remove);
            }

            if (!Confirm(label, detail)) return;
            await Work("正在" + label + "…", true, async () =>
            {
                string result = await Task.Run(action);
                notice = result;
                await ProbeAll();
            });
        }

        private static string ResultMessage(UnrealResult result)
        {
            return result.Message + (string.IsNullOrWhiteSpace(result.BackupPath) ? "" : "  备份位置：" + result.BackupPath);
        }

        private static string Elevate(string engine, bool remove)
        {
            try
            {
                string executable = System.Reflection.Assembly.GetExecutingAssembly().Location;
                using (var child = Process.Start(new ProcessStartInfo(executable, HostInstaller.Arguments(remove ? "--engine-uninstall" : "--engine-install", engine))
                { UseShellExecute = true, Verb = "runas", WorkingDirectory = App.Distribution }))
                {
                    child.WaitForExit();
                    return child.ExitCode == 0 ? "引擎级插件更新完成。" : "管理员更新未完成。请查看管理员窗口提示。";
                }
            }
            catch (Win32Exception error) when (error.NativeErrorCode == 1223)
            {
                return "未获得管理员权限。可重试或改为安装到单个工程。";
            }
        }

        private async Task Work(string message, bool writes, Func<Task> operation)
        {
            busy = true;
            changingSystem = writes;
            busyMessage = message;
            notice = "";
            RenderSelection();
            try { await operation(); }
            catch (Exception error) when (error is IOException || error is UnauthorizedAccessException
                || error is InvalidOperationException || error is ArgumentException || error is Win32Exception)
            {
                notice = error is InvalidOperationException ? error.Message : "操作未完成。请检查目录权限并确认安装包已完整解压。";
            }
            finally
            {
                busy = false;
                changingSystem = false;
                RenderSelection();
            }
        }

        private bool Confirm(string action, string detail)
        {
            var dialog = new Window
            {
                Title = "确认" + action, Owner = this, WindowStartupLocation = WindowStartupLocation.CenterOwner,
                ResizeMode = ResizeMode.NoResize, SizeToContent = SizeToContent.Height, Width = 520, ShowInTaskbar = false,
                Background = new SolidColorBrush(Color.FromRgb(28, 28, 28)), Foreground = Brushes.White,
                FontFamily = FontFamily, FontSize = 13
            };
            dialog.SourceInitialized += (_, __) => ApplyDarkCaption(dialog);
            var panel = new StackPanel { Margin = new Thickness(24) };
            panel.Children.Add(new TextBlock { Text = detail, TextWrapping = TextWrapping.Wrap, Foreground = Brushes.Gainsboro });
            var buttons = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, Margin = new Thickness(0, 24, 0, 0) };
            foreach (var name in new[] { "取消", "确认" + action })
            {
                bool primary = name != "取消";
                var button = new Button { Content = name, MinWidth = 82, Margin = new Thickness(8, 0, 0, 0), IsCancel = !primary, IsDefault = primary };
                var style = TryFindResource(primary ? "PrimaryButton" : "GhostButton") as Style;
                if (style != null) button.Style = style;
                button.Click += (_, __) => dialog.DialogResult = primary;
                buttons.Children.Add(button);
            }
            panel.Children.Add(buttons);
            dialog.Content = panel;
            return dialog.ShowDialog() == true;
        }

        private void ShowGuide()
        {
            string file = new[] { "安装指南.md", "README.md" }.Select(name => Path.Combine(distribution, name)).FirstOrDefault(File.Exists);
            if (file == null) { notice = "未找到安装指南。请先完整解压发行 ZIP。"; RenderSelection(); return; }
            try { Process.Start(new ProcessStartInfo(file) { UseShellExecute = true }); }
            catch (Win32Exception)
            {
                Process.Start(new ProcessStartInfo("notepad.exe", HostInstaller.Arguments(file)) { UseShellExecute = true });
            }
        }

        private void Reveal(string file)
        {
            if (File.Exists(file))
                Process.Start(new ProcessStartInfo("explorer.exe", "/select," + HostInstaller.Arguments(file)) { UseShellExecute = true });
            else { notice = "未找到安装文件。请完整解压发行 ZIP。"; RenderSelection(); }
        }

        private static bool Same(string first, string second) { return string.Equals(first, second, StringComparison.OrdinalIgnoreCase); }

        private static string ExtractionNotice(string path)
        {
            var issues = new List<string>();
            if (path.Any(character => character > 127)) issues.Add("非英文字符");
            if (path.Any(char.IsWhiteSpace)) issues.Add("空格");
            if (path.Split(Path.DirectorySeparatorChar).Any(segment => segment.StartsWith("OneDrive", StringComparison.OrdinalIgnoreCase))
                || new[] { "OneDrive", "OneDriveConsumer", "OneDriveCommercial" }.Select(Environment.GetEnvironmentVariable)
                    .Any(location => !string.IsNullOrEmpty(location)
                        && path.StartsWith(location.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)))
                issues.Add("OneDrive 同步位置");
            return issues.Count == 0 ? "" : "当前路径含" + string.Join("、", issues) + "。请解压到纯英文、无空格的本地目录。";
        }

        private sealed class DialogOwner : Forms.IWin32Window
        {
            public DialogOwner(IntPtr handle) { Handle = handle; }
            public IntPtr Handle { get; private set; }
        }

        internal static void ApplyDarkCaption(Window window)
        {
            IntPtr handle = new WindowInteropHelper(window).Handle;
            int dark = 1;
            if (DwmSetWindowAttribute(handle, 20, ref dark, sizeof(int)) != 0)
                DwmSetWindowAttribute(handle, 19, ref dark, sizeof(int));
            int background = 0x141414;
            int text = 0xf0f0f0;
            int border = 0x2a2a2a;
            DwmSetWindowAttribute(handle, 34, ref border, sizeof(int));
            DwmSetWindowAttribute(handle, 35, ref background, sizeof(int));
            DwmSetWindowAttribute(handle, 36, ref text, sizeof(int));
        }

        [DllImport("dwmapi.dll")]
        private static extern int DwmSetWindowAttribute(IntPtr window, int attribute, ref int value, int byteCount);

        [DllImport("dwmapi.dll")]
        private static extern int DwmFlush();
    }
}
