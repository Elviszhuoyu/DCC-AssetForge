from __future__ import absolute_import

import unittest

from asset_forge.unreal.editor_widget_asset import ensure_editor_widget_asset, read_editor_widget_core_tree


class UnrealEditorWidgetAssetTest(unittest.TestCase):
    def test_ensure_creates_editor_utility_widget_and_core_controls(self):
        fake_unreal = FakeUnreal()

        report = ensure_editor_widget_asset(fake_unreal)

        self.assertEqual(report["status"], "success")
        self.assertTrue(report["created"])
        self.assertTrue(report["asset_exists"])
        self.assertIn("AFG_Root", report["created_widgets"])
        self.assertIn("AFG_MeshStatus", report["created_widgets"])
        self.assertIn("AFG_TextureStatus", report["created_widgets"])
        self.assertIn("AFG_MaterialStatus", report["created_widgets"])
        self.assertIn("AFG_ProfileStatus", report["created_widgets"])
        self.assertIn("AFG_GateStatus", report["created_widgets"])
        self.assertIn("AFG_WarningList", report["created_widgets"])
        self.assertIn("AFG_ErrorList", report["created_widgets"])
        self.assertIn("AFG_RefreshButton", report["created_widgets"])
        self.assertIn("AFG_ImportButton", report["created_widgets"])
        self.assertEqual(report["missing_widgets"], [])
        self.assertEqual(fake_unreal.EditorAssetLibrary.saved[-1], "/AssetForge/Editor/EUW_AssetForgeGate")

    def test_read_core_tree_reports_named_controls(self):
        fake_unreal = FakeUnreal()
        ensure_editor_widget_asset(fake_unreal)

        report = read_editor_widget_core_tree(fake_unreal)
        names = [item["name"] for item in report["widgets"]]

        self.assertEqual(report["status"], "ready")
        self.assertIn("AFG_RecentPackageList", names)
        self.assertIn("AFG_SelectedPackagePath", names)
        self.assertIn("AFG_PreviewGateButton", names)
        self.assertEqual(report["missing_widgets"], [])

    def test_ensure_skips_creation_when_unattended_and_asset_is_missing(self):
        fake_unreal = FakeUnreal(unattended=True)

        report = ensure_editor_widget_asset(fake_unreal)

        self.assertEqual(report["status"], "skipped_unattended")
        self.assertFalse(report["created"])
        self.assertFalse(report["asset_exists"])
        self.assertIn("skip Editor Utility Widget creation while Unreal is running unattended", report["issues"])
        self.assertEqual(fake_unreal.AssetToolsHelpers.get_asset_tools().create_calls, [])


class FakeUnreal(object):
    class EditorUtilityWidgetBlueprintFactory(object):
        pass

    class Text(object):
        def __init__(self, value):
            self.value = value

        def __str__(self):
            return self.value

    class VerticalBox(object):
        pass

    class HorizontalBox(object):
        pass

    class ScrollBox(object):
        pass

    class TextBlock(object):
        pass

    class Button(object):
        pass

    class EditableTextBox(object):
        pass

    class ComboBoxString(object):
        pass

    class ListView(object):
        pass

    class CheckBox(object):
        pass

    def __init__(self, unattended=False):
        self.EditorAssetLibrary = FakeEditorAssetLibrary()
        self.AssetToolsHelpers = FakeAssetToolsHelpers(self.EditorAssetLibrary)
        self.SystemLibrary = FakeSystemLibrary(unattended)


class FakeAssetToolsHelpers(object):
    def __init__(self, library):
        self.library = library
        self.asset_tools = FakeAssetTools(self.library)

    def get_asset_tools(self):
        return self.asset_tools


class FakeAssetTools(object):
    def __init__(self, library):
        self.library = library
        self.create_calls = []

    def create_asset(self, name, package_path, asset_class, factory):
        self.create_calls.append((name, package_path, asset_class, factory))
        asset_path = package_path + "/" + name
        asset = FakeWidgetAsset()
        self.library.assets[asset_path] = asset
        self.library.assets[asset_path + "." + name] = asset
        return asset


class FakeSystemLibrary(object):
    def __init__(self, unattended=False):
        self.unattended = unattended

    def is_unattended(self):
        return self.unattended


class FakeEditorAssetLibrary(object):
    def __init__(self):
        self.assets = {}
        self.saved = []

    def does_asset_exist(self, asset_path):
        return asset_path in self.assets

    def load_asset(self, asset_path):
        return self.assets.get(asset_path)

    def save_asset(self, asset_path, only_if_is_dirty=False):
        self.saved.append(asset_path)
        return True


class FakeWidgetAsset(object):
    def __init__(self):
        self.widget_tree = FakeWidgetTree()


class FakeWidgetTree(object):
    def __init__(self):
        self.root_widget = None

    def construct_widget(self, widget_class, name):
        return FakeWidget(name, widget_class.__name__)

    def find_widget(self, name):
        return self._walk(self.root_widget, name)

    def set_editor_property(self, property_name, value):
        if property_name == "root_widget":
            self.root_widget = value

    def _walk(self, widget, name):
        if widget is None:
            return None
        if widget.name == name:
            return widget
        for child in widget.children:
            found = self._walk(child, name)
            if found is not None:
                return found
        return None


class FakeWidget(object):
    def __init__(self, name, class_name):
        self.name = name
        self.class_name = class_name
        self.children = []
        self.text = ""

    def add_child(self, child):
        self.children.append(child)

    def set_text(self, text):
        self.text = str(text)


if __name__ == "__main__":
    unittest.main()
