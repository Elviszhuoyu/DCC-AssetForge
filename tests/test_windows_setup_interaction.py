"""Contracts shared by the standalone WPF installer and its release builder."""

from pathlib import Path
import unittest
from xml.etree import ElementTree


PROJECT = Path(__file__).resolve().parents[1] / "tools/windows_setup/wpf"


class WindowsSetupInteractionTests(unittest.TestCase):
    def test_release_targets_system_wpf_x64(self):
        root = ElementTree.parse(PROJECT / "AssetForge.Setup.csproj").getroot()
        ms = {"m": "http://schemas.microsoft.com/developer/msbuild/2003"}
        self.assertEqual(root.findtext(".//m:TargetFrameworkVersion", namespaces=ms), "v4.8")
        self.assertEqual(root.findtext(".//m:PlatformTarget", namespaces=ms), "x64")
        self.assertEqual(root.findtext(".//m:DebugType", namespaces=ms), "none")
        manifest = (PROJECT / "app.manifest").read_text(encoding="utf-8")
        self.assertIn("PerMonitorV2,PerMonitor", manifest)
        self.assertIn('level="asInvoker"', manifest)

    def test_navigation_handlers_read_only_the_current_selection_snapshot(self):
        source = (PROJECT / "MainWindow.xaml.cs").read_text(encoding="utf-8")
        navigation = source.split("private void SelectionChanged(", 1)[1].split("private async void ActionClick(", 1)[0]
        for io_or_discovery in ("File.", "Directory.", "Process.", "Registry.", "unreal.Plan(", "ProbeAll(", "Task.Run("):
            self.assertNotIn(io_or_discovery, navigation)
