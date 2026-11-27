using System;
using System.IO;
using System.Reflection;
using System.Windows;

[assembly: AssemblyTitle("DCC AssetForge 安装助手")]
[assembly: AssemblyProduct("DCC AssetForge")]
[assembly: AssemblyCompany("卓雨 (Elviszhuoyu)")]
[assembly: AssemblyCopyright("© 2026 Elviszhuoyu")]
[assembly: AssemblyMetadata("AuthorURL", "https://work.zhuoyulabs.com")]
[assembly: AssemblyMetadata("ProjectURL", "https://github.com/Elviszhuoyu/DCC-AssetForge")]
[assembly: AssemblyVersion("0.2.0.0")]
[assembly: AssemblyFileVersion("0.2.0.0")]
[assembly: AssemblyInformationalVersion("0.2.0")]

namespace AssetForge.Setup
{
    public partial class App : Application
    {
        internal static string Distribution { get { return AppDomain.CurrentDomain.BaseDirectory; } }
        internal static UnrealInstaller Unreal() { return new UnrealInstaller(Path.Combine(Distribution, "Payload", "Unreal")); }

        protected override void OnStartup(StartupEventArgs e)
        {
            base.OnStartup(e);
            if (e.Args.Length == 2 && (e.Args[0] == "--engine-install" || e.Args[0] == "--engine-uninstall"))
            {
                RunElevatedEngineAction(e.Args[0] == "--engine-uninstall", e.Args[1]);
                return;
            }
            MainWindow = new MainWindow();
            MainWindow.Show();
        }

        private async void RunElevatedEngineAction(bool remove, string root)
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            try
            {
                var service = Unreal();
                var result = await System.Threading.Tasks.Task.Run(() => remove
                    ? service.Uninstall(engineRoot: root, engineInstall: true)
                    : service.Install(engineRoot: root, engineInstall: true));
                MessageBox.Show(result.Message + (string.IsNullOrWhiteSpace(result.BackupPath) ? "" : "\n备份位置：" + result.BackupPath),
                    "DCC AssetForge", MessageBoxButton.OK, result.Success ? MessageBoxImage.Information : MessageBoxImage.Warning);
                Shutdown(result.Success ? 0 : 1);
            }
            catch (Exception)
            {
                MessageBox.Show("引擎插件更新未完成。请确认引擎已关闭、安装包已完整解压，再重试。", "DCC AssetForge",
                    MessageBoxButton.OK, MessageBoxImage.Warning);
                Shutdown(1);
            }
        }
    }
}
