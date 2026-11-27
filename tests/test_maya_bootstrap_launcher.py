from __future__ import absolute_import

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import types
import unittest
from unittest import mock


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
LAUNCHER_PATH = os.path.join(REPO_ROOT, "scripts", "maya_launch_asset_forge.py")


def load_launcher():
    spec = importlib.util.spec_from_file_location("maya_launch_asset_forge_test", LAUNCHER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def exec_launcher(namespace):
    with open(LAUNCHER_PATH, "rb") as stream:
        code = compile(stream.read(), LAUNCHER_PATH, "exec")
    exec(code, namespace)
    return namespace


class MayaBootstrapLauncherTest(unittest.TestCase):
    def test_bootstrap_replaces_stale_asset_forge_maya_module(self):
        stale = types.ModuleType("asset_forge_maya")
        stale.__file__ = r"C:\old_tools\asset_forge_maya.py"
        sys.modules["asset_forge_maya"] = stale

        launcher = load_launcher()
        result = launcher.bootstrap(repo_root=REPO_ROOT, open_ui=False)

        loaded = sys.modules["asset_forge_maya"]
        self.assertTrue(result["has_reload_and_show"])
        self.assertTrue(callable(getattr(loaded, "reload_and_show", None)))
        self.assertIn("integrations", os.path.normpath(result["module_file"]))
        self.assertIn("asset_forge_maya.py", os.path.basename(result["module_file"]))
        self.assertIn("asset_forge_maya", result["purged_modules"])

    def test_bootstrap_prioritizes_repo_paths(self):
        launcher = load_launcher()
        result = launcher.bootstrap(repo_root=REPO_ROOT, open_ui=False)

        self.assertEqual(os.path.normcase(os.path.abspath(sys.path[0])), os.path.normcase(os.path.join(REPO_ROOT, "integrations", "maya", "scripts")))
        self.assertEqual(os.path.normcase(os.path.abspath(sys.path[1])), os.path.normcase(REPO_ROOT))
        self.assertEqual(os.path.normcase(os.path.abspath(sys.path[2])), os.path.normcase(os.path.join(REPO_ROOT, "scripts")))
        self.assertEqual(os.path.normcase(result["repo_scripts"]), os.path.normcase(os.path.join(REPO_ROOT, "scripts")))
        self.assertTrue(result["module_file"].endswith("asset_forge_maya.py"))

    def test_exec_without_file_uses_bootstrap_global(self):
        namespace = exec_launcher({"__name__": "maya_exec_test", "_bootstrap": LAUNCHER_PATH})

        result = namespace["bootstrap"](open_ui=False)

        self.assertEqual(os.path.normcase(result["repo_root"]), os.path.normcase(REPO_ROOT))
        self.assertTrue(result["has_reload_and_show"])

    def test_exec_with_explicit_file_namespace_finds_repo(self):
        namespace = exec_launcher(
            {
                "__file__": LAUNCHER_PATH,
                "__name__": "maya_exec_test",
                "ASSET_FORGE_BOOTSTRAP_PATH": LAUNCHER_PATH,
            }
        )

        result = namespace["bootstrap"](open_ui=False)

        self.assertEqual(os.path.normcase(result["repo_root"]), os.path.normcase(REPO_ROOT))
        self.assertTrue(result["module_file"].endswith("asset_forge_maya.py"))

    def test_help_and_check_are_readable_without_opening_ui(self):
        launcher = load_launcher()

        self.assertIn("--bridge", launcher.usage_text())
        self.assertIn("--install-ui-shelf", launcher.usage_text())
        self.assertIn("--install-bridge-shelf", launcher.usage_text())
        self.assertIn("--check", launcher.usage_text())
        report = launcher.check(REPO_ROOT)

        self.assertEqual(report["stage"], "maya_bootstrap_check")
        self.assertTrue(report["can_accept"])
        self.assertIn("next_action", report)

    def test_start_bridge_uses_repo_bridge_module(self):
        launcher = load_launcher()
        bridge = types.ModuleType("asset_forge_maya_bridge")
        calls = []

        def fake_start_bridge(**kwargs):
            calls.append(kwargs)
            return {"status": "running", "bridge_version": "test"}

        bridge.start_bridge = fake_start_bridge
        old_loader = launcher._load_bridge_module
        launcher._load_bridge_module = lambda _repo_root: bridge
        try:
            report = launcher.start_bridge(repo_root=REPO_ROOT, host="127.0.0.1", port=8765, token="local")
        finally:
            launcher._load_bridge_module = old_loader

        self.assertEqual(report["status"], "running")
        self.assertEqual(calls[0]["repo_root"], REPO_ROOT)
        self.assertEqual(calls[0]["port"], 8765)
        self.assertEqual(calls[0]["token"], "local")

    def test_install_bridge_shelf_button_uses_repo_bridge_module(self):
        launcher = load_launcher()
        bridge = types.ModuleType("asset_forge_maya_bridge")
        calls = []

        def fake_install_bridge_shelf_button(**kwargs):
            calls.append(kwargs)
            return {"status": "success", "button": "assetForgeMcpBridgeButton"}

        bridge.install_bridge_shelf_button = fake_install_bridge_shelf_button
        old_loader = launcher._load_bridge_module
        launcher._load_bridge_module = lambda _repo_root: bridge
        try:
            report = launcher.install_bridge_shelf_button(repo_root=REPO_ROOT)
        finally:
            launcher._load_bridge_module = old_loader

        self.assertEqual(report["status"], "success")
        self.assertEqual(calls[0]["repo_root"], REPO_ROOT)

    def test_install_bridge_shelf_button_does_not_stop_running_bridge_module(self):
        launcher = load_launcher()
        bridge = types.ModuleType("asset_forge_maya_bridge")
        bridge._SERVER = object()
        calls = []

        def fake_install_bridge_shelf_button(**kwargs):
            calls.append(kwargs)
            return {"status": "success", "button": "assetForgeMcpBridgeButton"}

        def fail_loader(_repo_root):
            raise AssertionError("running bridge module should be reused while installing shelf")

        bridge.install_bridge_shelf_button = fake_install_bridge_shelf_button
        old_bridge = sys.modules.get("asset_forge_maya_bridge")
        old_loader = launcher._load_bridge_module
        sys.modules["asset_forge_maya_bridge"] = bridge
        launcher._load_bridge_module = fail_loader
        try:
            report = launcher.install_bridge_shelf_button(repo_root=REPO_ROOT)
        finally:
            launcher._load_bridge_module = old_loader
            if old_bridge is None:
                sys.modules.pop("asset_forge_maya_bridge", None)
            else:
                sys.modules["asset_forge_maya_bridge"] = old_bridge

        self.assertEqual(report["status"], "success")
        self.assertEqual(calls[0]["repo_root"], REPO_ROOT)

    def test_current_bridge_module_reuses_running_bridge_for_status(self):
        launcher = load_launcher()
        bridge = types.ModuleType("asset_forge_maya_bridge")
        bridge._SERVER = object()
        bridge.show_bridge_status_window = lambda: {"status": "running"}

        def fail_loader(_repo_root):
            raise AssertionError("status lookup should not reload or stop a running bridge")

        old_bridge = sys.modules.get("asset_forge_maya_bridge")
        old_loader = launcher._load_bridge_module
        sys.modules["asset_forge_maya_bridge"] = bridge
        launcher._load_bridge_module = fail_loader
        try:
            module = launcher.current_bridge_module(repo_root=REPO_ROOT)
        finally:
            launcher._load_bridge_module = old_loader
            if old_bridge is None:
                sys.modules.pop("asset_forge_maya_bridge", None)
            else:
                sys.modules["asset_forge_maya_bridge"] = old_bridge

        self.assertIs(module, bridge)

    def test_start_bridge_reuses_running_bridge_module(self):
        launcher = load_launcher()
        bridge = types.ModuleType("asset_forge_maya_bridge")
        bridge._SERVER = object()
        calls = []

        def fake_start_bridge(**kwargs):
            calls.append(kwargs)
            return {"status": "running", "bridge_version": "test"}

        def fail_loader(_repo_root):
            raise AssertionError("start should ask the active bridge to report running status")

        bridge.start_bridge = fake_start_bridge
        old_bridge = sys.modules.get("asset_forge_maya_bridge")
        old_loader = launcher._load_bridge_module
        sys.modules["asset_forge_maya_bridge"] = bridge
        launcher._load_bridge_module = fail_loader
        try:
            report = launcher.start_bridge(repo_root=REPO_ROOT)
        finally:
            launcher._load_bridge_module = old_loader
            if old_bridge is None:
                sys.modules.pop("asset_forge_maya_bridge", None)
            else:
                sys.modules["asset_forge_maya_bridge"] = old_bridge

        self.assertEqual(report["status"], "running")
        self.assertEqual(calls[0]["repo_root"], REPO_ROOT)

    def test_install_ui_shelf_button_uses_unified_icon_and_repo_bootstrap(self):
        launcher = load_launcher()
        fake_cmds = FakeMayaCmds()
        fake_mel = types.ModuleType("maya.mel")
        fake_mel.eval = lambda _expr: "ShelfTopLevel"
        old_modules = _install_fake_maya_modules(fake_cmds, fake_mel)
        try:
            report = launcher.install_ui_shelf_button(repo_root=REPO_ROOT)
        finally:
            _restore_modules(old_modules)

        self.assertEqual(report["status"], "success")
        self.assertEqual(report["button"], launcher.UI_SHELF_BUTTON)
        button = fake_cmds.buttons[launcher.UI_SHELF_BUTTON]
        self.assertTrue(button["image"].endswith("/Workbench/brand/af_shelf.png"))
        self.assertEqual(button["image"], button["image1"])
        self.assertEqual(button["label"], "DCC AssetForge")
        self.assertEqual(button["imageOverlayLabel"], "")
        self.assertIn("maya_launch_asset_forge.py", button["command"])
        self.assertEqual(button["sourceType"], "python")

    def test_shelf_click_in_maya_main_opens_checkout_once_and_preserves_globals(self):
        launcher = load_launcher()
        namespace = {"__name__": "__main__", "__file__": "maya.exe", "__builtins__": __builtins__,
                     "ASSET_FORGE_REPO_ROOT": "other-checkout", "bootstrap": object()}
        original = namespace.copy()
        with tempfile.TemporaryDirectory(prefix="Artist's Checkout ") as repo:
            os.makedirs(os.path.join(repo, "scripts"))
            shutil.copyfile(LAUNCHER_PATH, os.path.join(repo, "scripts", "maya_launch_asset_forge.py"))
            entry = launcher._entry_script_path(repo)
            os.makedirs(os.path.dirname(entry))
            with open(entry, "w", encoding="utf-8") as stream:
                stream.write("shows = []\ndef reload_and_show():\n    shows.append(__file__)\n")
            with mock.patch.dict(sys.modules), mock.patch.object(sys, "path", sys.path[:]), \
                    mock.patch.object(sys, "argv", ["maya", "-noAutoloadPlugins"]):
                exec(launcher._ui_shelf_command(repo), namespace)
                self.assertEqual(sys.modules[launcher.MODULE_NAME].shows, [entry])
        self.assertEqual(namespace, original)

    def test_saved_workspace_restores_existing_control_without_shelf_or_pythonpath(self):
        from asset_forge.maya.ui import _workspace_restore_script
        with tempfile.TemporaryDirectory(prefix="美术 A's 工作区 ") as repo:
            scripts = os.path.join(repo, "scripts")
            maya_package = os.path.join(repo, "asset_forge", "maya")
            os.makedirs(scripts)
            os.makedirs(maya_package)
            shutil.copyfile(LAUNCHER_PATH, os.path.join(scripts, "maya_launch_asset_forge.py"))
            for folder in (os.path.dirname(maya_package), maya_package):
                open(os.path.join(folder, "__init__.py"), "w").close()
            with open(os.path.join(maya_package, "ui.py"), "w", encoding="utf-8") as stream:
                stream.write("calls = []\ndef restore_workspace():\n    calls.append('restore')\n")
            command = _workspace_restore_script(repo)
            self.assertTrue(command.isascii())
            self.assertNotIn(repo, command)
            with mock.patch.dict(sys.modules), mock.patch.object(sys, "path", sys.path[:]):
                for name in list(sys.modules):
                    if name == "asset_forge" or name.startswith("asset_forge."):
                        del sys.modules[name]
                namespace = {"__builtins__": __builtins__}
                exec(command, namespace)
                self.assertEqual(sys.modules["asset_forge.maya.ui"].calls, ["restore"])
                self.assertEqual(set(namespace), {"__builtins__"})
                self.assertEqual(sys.path.count(repo), 1)

    def test_load_bridge_module_replaces_stale_cached_bridge(self):
        launcher = load_launcher()
        stale = types.ModuleType("asset_forge_maya_bridge")
        stale.__file__ = r"C:\old_tools\asset_forge_maya_bridge.py"
        sys.modules["asset_forge_maya_bridge"] = stale

        module = launcher._load_bridge_module(REPO_ROOT)

        self.assertIs(sys.modules["asset_forge_maya_bridge"], module)
        self.assertIn("integrations", os.path.normpath(module.__file__))
        self.assertTrue(module.__file__.endswith("asset_forge_maya_bridge.py"))

    def test_cli_check_writes_maya_latest_log_when_requested(self):
        launcher = load_launcher()
        old_root = os.environ.get("ASSET_FORGE_LOG_ROOT")
        with tempfile.TemporaryDirectory() as temp_dir:
            os.environ["ASSET_FORGE_LOG_ROOT"] = temp_dir
            try:
                result = launcher.main(["--check", REPO_ROOT])
            finally:
                if old_root is None:
                    os.environ.pop("ASSET_FORGE_LOG_ROOT", None)
                else:
                    os.environ["ASSET_FORGE_LOG_ROOT"] = old_root

            self.assertEqual(result, 0)
            latest = os.path.join(temp_dir, "AssetForgeReports", "logs", "latest_maya.log")
            self.assertTrue(os.path.exists(latest))
            with open(latest, "r", encoding="utf-8") as stream:
                entry = json.loads(stream.readlines()[-1])
            self.assertEqual(entry["operation"], "maya_bootstrap_check")
            self.assertEqual(entry["outputs"]["stage"], "maya_bootstrap_check")
            self.assertTrue(entry["outputs"]["can_accept"])

    def test_bad_cli_arg_returns_usage_without_traceback(self):
        launcher = load_launcher()

        result = launcher.main(["--bad-arg"])

        self.assertEqual(result, 2)

    def test_shelf_export_uses_project_settings_and_operation_log(self):
        module_path = os.path.join(REPO_ROOT, "integrations", "maya", "scripts", "asset_forge_maya.py")
        spec = importlib.util.spec_from_file_location("asset_forge_maya_shelf_test", module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        settings_path = os.path.join(self._temp_dir(), "project_settings.json")
        with open(settings_path, "w", encoding="utf-8") as stream:
            json.dump(
                {
                    "asset_name_override": "SM_HK416D_Shelf",
                    "build_reversed_index_buffer": "enabled",
                    "generate_lightmap_uvs": "disabled",
                    "collision_complexity": "use_complex_as_simple",
                    "virtual_texture_policy": "force_off",
                },
                stream,
            )
        calls = []
        logs = []
        old_pipeline = module._pipeline_class
        old_logger = module._operation_logger_class
        module._pipeline_class = lambda: lambda: FakeShelfPipeline(calls)
        module._operation_logger_class = lambda: lambda: FakeShelfLogger(logs)
        try:
            result = module.export_selected(
                "D:/Exports",
                target_path="/Game/Props/HK416D",
                texture_folder="D:/Textures",
                texture_set_token="a1,d1",
                project_settings_path=settings_path,
            )
        finally:
            module._pipeline_class = old_pipeline
            module._operation_logger_class = old_logger

        self.assertEqual(result["scan"]["asset_name"], "SM_HK416D_Shelf")
        self.assertEqual(calls[0]["asset_name_override"], "SM_HK416D_Shelf")
        self.assertEqual(calls[0]["texture_import_policy"]["virtual_texture_policy"], "force_off")
        self.assertEqual(calls[0]["static_mesh_import_policy"]["build_reversed_index_buffer"], "enabled")
        self.assertEqual(calls[0]["static_mesh_import_policy"]["generate_lightmap_uvs"], "disabled")
        self.assertEqual(calls[0]["static_mesh_import_policy"]["collision_complexity"], "use_complex_as_simple")
        self.assertEqual([entry[0] for entry in logs], ["shelf_export_start", "shelf_export_success"])

    def _temp_dir(self):
        if not hasattr(self, "_shelf_temp_dir"):
            self._shelf_temp_dir = tempfile.mkdtemp()
            self.addCleanup(lambda: os.path.isdir(self._shelf_temp_dir) and __import__("shutil").rmtree(self._shelf_temp_dir))
        return self._shelf_temp_dir


class FakeShelfAdapter(object):
    def get_current_selection(self):
        return ["|SM_HK416D"]


class FakeShelfPipeline(object):
    def __init__(self, calls):
        self.adapter = FakeShelfAdapter()
        self.rules = {}
        self.calls = calls

    def export_assets(self, selection, output_dir, target_platform, target_path, **kwargs):
        self.calls.append(dict(kwargs))
        asset_name = kwargs.get("asset_name_override") or "SM_HK416D"
        return {
            "scan": {"asset_name": asset_name},
            "validation": {"status": "pass", "can_export": True, "checks": []},
            "package_dir": output_dir + "/" + asset_name,
            "manifest_path": output_dir + "/" + asset_name + "/" + asset_name + "_manifest.json",
            "fbx_path": output_dir + "/" + asset_name + "/" + asset_name + ".fbx",
            "export_report_path": output_dir + "/" + asset_name + "/" + asset_name + "_export_report.json",
        }


class FakeShelfLogger(object):
    root = REPO_ROOT

    def __init__(self, logs):
        self.logs = logs

    def log(self, operation, status, **kwargs):
        self.logs.append((operation, status, kwargs))
        return {"log_path": "E:/Repo/AssetForgeReports/logs/latest_maya.log"}


class FakeMayaCmds(object):
    def __init__(self):
        self.shelves = set()
        self.buttons = {}
        self.deleted = []

    def shelfLayout(self, name=None, exists=False, parent=None):
        if exists:
            return name in self.shelves
        self.shelves.add(name)
        return name

    def shelfButton(self, name=None, exists=False, **kwargs):
        if exists:
            return name in self.buttons
        self.buttons[name] = dict(kwargs)
        return name

    def deleteUI(self, name):
        self.deleted.append(name)
        self.buttons.pop(name, None)


def _install_fake_maya_modules(fake_cmds, fake_mel):
    old = {name: sys.modules.get(name) for name in ["maya", "maya.cmds", "maya.mel"]}
    maya_pkg = types.ModuleType("maya")
    maya_pkg.cmds = fake_cmds
    maya_pkg.mel = fake_mel
    sys.modules["maya"] = maya_pkg
    sys.modules["maya.cmds"] = fake_cmds
    sys.modules["maya.mel"] = fake_mel
    return old


def _restore_modules(old):
    for name, module in old.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


if __name__ == "__main__":
    unittest.main()
