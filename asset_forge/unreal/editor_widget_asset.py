"""Create and inspect the Asset Forge Editor Utility Widget asset."""

from __future__ import absolute_import

from asset_forge.unreal.editor_widget_schema import get_editor_widget_plan
from asset_forge.unreal.unreal_bridge import get_unreal


def ensure_editor_widget_asset(unreal_module=None, widget_plan=None):
    plan = widget_plan or get_editor_widget_plan()
    unreal = unreal_module or get_unreal()
    report = {
        "status": "skipped",
        "asset_path": plan.get("asset_path", ""),
        "object_path": _object_path(plan.get("asset_path", "")),
        "created": False,
        "asset_exists": False,
        "core_widget_count": len(plan.get("core_widgets", []) or []),
        "created_widgets": [],
        "existing_widgets": [],
        "missing_widgets": [],
        "removed_widgets": [],
        "issues": [],
    }
    if unreal is None:
        report["issues"].append("unreal module is not available")
        return report

    asset_path = plan.get("asset_path", "")
    asset_exists = _asset_exists(unreal, asset_path)
    if not asset_exists:
        if _is_unattended(unreal):
            report["issues"].append("skip Editor Utility Widget creation while Unreal is running unattended")
            report["status"] = "skipped_unattended"
            return report
        created_asset = _create_editor_utility_widget_asset(unreal, plan)
        if created_asset is None:
            report["issues"].append("unable to create Editor Utility Widget asset")
            report["status"] = "error"
            return report
        report["created"] = True
        asset_exists = True

    widget_asset = _load_asset(unreal, asset_path)
    if widget_asset is None:
        report["issues"].append("unable to load Editor Utility Widget asset")
        report["status"] = "error"
        return report

    tree_report = _ensure_widget_tree(unreal, widget_asset, plan.get("core_widgets", []) or [], bool(plan.get("rebuild_tree", False)))
    removed_widgets = _remove_obsolete_widgets(widget_asset, plan.get("obsolete_widgets", []) or [])
    report.update(tree_report)
    report["removed_widgets"] = removed_widgets
    report["asset_exists"] = asset_exists
    report["status"] = "success" if not report["missing_widgets"] and not report["issues"] else "warning"
    _save_asset(unreal, asset_path)
    return report


def read_editor_widget_core_tree(unreal_module=None, widget_plan=None):
    plan = widget_plan or get_editor_widget_plan()
    unreal = unreal_module or get_unreal()
    if unreal is None:
        return {"status": "skipped", "asset_path": plan.get("asset_path", ""), "widgets": [], "issues": ["unreal module is not available"]}
    widget_asset = _load_asset(unreal, plan.get("asset_path", ""))
    if widget_asset is None:
        return {"status": "missing_asset", "asset_path": plan.get("asset_path", ""), "widgets": [], "issues": ["widget asset is missing"]}
    widget_tree = _widget_tree(widget_asset)
    widgets = []
    for spec in plan.get("core_widgets", []) or []:
        name = spec.get("name", "")
        widget = _find_widget(widget_tree, name)
        if widget is not None:
            widgets.append({"name": name, "class": _class_name(widget), "parent": spec.get("parent", "")})
    missing = [spec.get("name", "") for spec in plan.get("core_widgets", []) or [] if spec.get("name", "") not in [item.get("name", "") for item in widgets]]
    return {
        "status": "ready" if not missing else "incomplete",
        "asset_path": plan.get("asset_path", ""),
        "widgets": widgets,
        "missing_widgets": missing,
        "issues": [],
    }


def _create_editor_utility_widget_asset(unreal, plan):
    asset_tools_helpers = getattr(unreal, "AssetToolsHelpers", None)
    factory_class = getattr(unreal, "EditorUtilityWidgetBlueprintFactory", None)
    if asset_tools_helpers is None or factory_class is None or not hasattr(asset_tools_helpers, "get_asset_tools"):
        return None
    factory = factory_class()
    asset_tools = asset_tools_helpers.get_asset_tools()
    return asset_tools.create_asset(plan.get("widget_name", "EUW_AssetForgeGate"), plan.get("content_mount", "/AssetForge") + "/Editor", None, factory)


def _is_unattended(unreal):
    system_library = getattr(unreal, "SystemLibrary", None)
    if system_library is not None and hasattr(system_library, "is_unattended"):
        try:
            return bool(system_library.is_unattended())
        except Exception:
            return False
    return False


def _ensure_widget_tree(unreal, widget_asset, core_widgets, rebuild_tree=False):
    widget_tree = _widget_tree(widget_asset)
    report = {"created_widgets": [], "existing_widgets": [], "missing_widgets": [], "issues": []}
    if widget_tree is None:
        report["issues"].append("widget_tree is unavailable")
        report["missing_widgets"] = [item.get("name", "") for item in core_widgets]
        return report

    if rebuild_tree:
        root_spec = _root_widget_spec(core_widgets)
        root_widget = _construct_widget(unreal, widget_tree, root_spec) if root_spec else None
        if root_widget is None:
            report["issues"].append("unable to rebuild root widget")
            report["missing_widgets"] = [item.get("name", "") for item in core_widgets]
            return report
        _set_root_widget(widget_asset, widget_tree, root_widget)
        _apply_widget_text(unreal, root_widget, root_spec.get("text", ""))
        _apply_widget_metadata(unreal, root_widget, root_spec)
        report["created_widgets"].append(root_spec.get("name", ""))
        core_widgets = [item for item in core_widgets if item.get("name", "") != root_spec.get("name", "")]

    for spec in core_widgets:
        name = spec.get("name", "")
        widget = _find_widget(widget_tree, name)
        if widget is not None:
            report["existing_widgets"].append(name)
            _apply_widget_text(unreal, widget, spec.get("text", ""))
            _apply_widget_metadata(unreal, widget, spec)
            continue
        widget = _construct_widget(unreal, widget_tree, spec)
        if widget is None:
            report["missing_widgets"].append(name)
            continue
        if spec.get("parent"):
            parent = _find_widget(widget_tree, spec.get("parent", ""))
            if not _add_child(parent, widget):
                report["missing_widgets"].append(name)
                continue
        else:
            _set_root_widget(widget_asset, widget_tree, widget)
        _apply_widget_text(unreal, widget, spec.get("text", ""))
        _apply_widget_metadata(unreal, widget, spec)
        report["created_widgets"].append(name)
    return report


def _root_widget_spec(core_widgets):
    for spec in core_widgets:
        if not spec.get("parent"):
            return spec
    return None


def _construct_widget(unreal, widget_tree, spec):
    widget_class = getattr(unreal, spec.get("class", ""), None)
    if widget_class is None:
        return None
    if hasattr(widget_tree, "construct_widget"):
        try:
            return widget_tree.construct_widget(widget_class, spec.get("name", ""))
        except TypeError:
            return widget_tree.construct_widget(widget_class)
    return None


def _add_child(parent, child):
    if parent is None:
        return False
    if hasattr(parent, "add_child"):
        parent.add_child(child)
        return True
    if hasattr(parent, "add_child_to_vertical_box"):
        parent.add_child_to_vertical_box(child)
        return True
    return False


def _apply_widget_text(unreal, widget, text):
    if not text:
        return
    value = text
    text_class = getattr(unreal, "Text", None)
    if text_class is not None:
        try:
            value = text_class(text)
        except Exception:
            value = text
    if hasattr(widget, "set_text"):
        widget.set_text(value)
        return
    if hasattr(widget, "set_editor_property"):
        try:
            widget.set_editor_property("text", value)
        except Exception:
            pass


def _apply_widget_metadata(unreal, widget, spec):
    if spec.get("class") == "TextBlock":
        font_size = spec.get("font_size") or _default_font_size(spec)
        _set_editor_property(widget, "auto_wrap_text", True)
        _set_editor_property(widget, "font_size", int(font_size))
        _set_editor_property(widget, "color_and_opacity", _text_color(unreal, spec))
    _apply_slot_spacing(unreal, widget, spec)


def _default_font_size(spec):
    name = spec.get("name", "")
    if name == "AFG_HeaderTitle":
        return 18
    if name == "AFG_HeaderStatus":
        return 11
    if name.endswith("SectionTitle"):
        return 14
    if name.endswith("Title"):
        return 13
    if name.endswith("Label"):
        return 11
    return 12


def _text_color(unreal, spec):
    color = spec.get("color") or _default_text_color(spec)
    linear_color = getattr(unreal, "LinearColor", None)
    if linear_color is not None:
        try:
            return linear_color(float(color[0]), float(color[1]), float(color[2]), float(color[3]))
        except Exception:
            return color
    return color


def _default_text_color(spec):
    name = spec.get("name", "")
    if name == "AFG_HeaderStatus" or "GateStatus" in name:
        return (0.58, 0.78, 0.62, 1.0)
    if name.endswith("SectionTitle"):
        return (0.88, 0.92, 0.94, 1.0)
    if name.endswith("Title"):
        return (0.78, 0.84, 0.88, 1.0)
    if "Warning" in name:
        return (0.95, 0.75, 0.42, 1.0)
    if "Error" in name:
        return (0.95, 0.45, 0.42, 1.0)
    return (0.72, 0.76, 0.78, 1.0)


def _apply_slot_spacing(unreal, widget, spec):
    slot = getattr(widget, "slot", None)
    if slot is None and hasattr(widget, "get_editor_property"):
        try:
            slot = widget.get_editor_property("slot")
        except Exception:
            slot = None
    if slot is None:
        return
    margin = _margin(unreal, spec.get("padding") or _default_padding(spec))
    _set_editor_property(slot, "padding", margin)


def _margin(unreal, values):
    margin_class = getattr(unreal, "Margin", None)
    if margin_class is not None:
        try:
            return margin_class(float(values[0]), float(values[1]), float(values[2]), float(values[3]))
        except Exception:
            return values
    return tuple(values)


def _default_padding(spec):
    name = spec.get("name", "")
    if name in ("AFG_Header", "AFG_Workbench"):
        return (8, 8, 8, 6)
    if name.endswith("Section"):
        return (0, 6, 0, 6)
    if name.endswith("SectionHeader"):
        return (0, 3, 0, 3)
    if name.endswith("Button") or name.startswith("AFG_Tab"):
        return (4, 2, 4, 2)
    return (2, 2, 2, 2)


def _set_editor_property(widget, property_name, value):
    setter = getattr(widget, "set_editor_property", None)
    if setter is None:
        try:
            setattr(widget, property_name, value)
            return True
        except Exception:
            return False
    try:
        setter(property_name, value)
        return True
    except Exception:
        return False


def _widget_tree(widget_asset):
    if hasattr(widget_asset, "widget_tree"):
        return widget_asset.widget_tree
    if hasattr(widget_asset, "get_editor_property"):
        try:
            return widget_asset.get_editor_property("widget_tree")
        except Exception:
            return None
    return None


def _set_root_widget(widget_asset, widget_tree, widget):
    if hasattr(widget_tree, "set_editor_property"):
        try:
            widget_tree.set_editor_property("root_widget", widget)
            return
        except Exception:
            pass
    try:
        widget_tree.root_widget = widget
    except Exception:
        pass
    if hasattr(widget_asset, "set_editor_property"):
        try:
            widget_asset.set_editor_property("widget_tree", widget_tree)
        except Exception:
            pass


def _remove_obsolete_widgets(widget_asset, widget_names):
    widget_tree = _widget_tree(widget_asset)
    removed = []
    for name in widget_names:
        widget = _find_widget(widget_tree, name)
        if widget is None:
            continue
        if _remove_widget(widget_tree, widget):
            removed.append(name)
    return removed


def _remove_widget(widget_tree, widget):
    if widget_tree is None or widget is None:
        return False
    remover = getattr(widget_tree, "remove_widget", None)
    if remover is not None:
        try:
            remover(widget)
            return True
        except Exception:
            pass
    parent = _find_parent(getattr(widget_tree, "root_widget", None), widget)
    for method_name in ("remove_child", "remove_child_at"):
        method = getattr(parent, method_name, None) if parent is not None else None
        if method is None:
            continue
        try:
            if method_name == "remove_child_at":
                children = _children(parent)
                method(children.index(widget))
            else:
                method(widget)
            return True
        except Exception:
            continue
    return False


def _find_parent(root, target):
    if root is None or target is None:
        return None
    for child in _children(root):
        if child is target:
            return root
        parent = _find_parent(child, target)
        if parent is not None:
            return parent
    return None


def _find_widget(widget_tree, name):
    if widget_tree is None or not name:
        return None
    for method_name in ("find_widget", "find_widget_by_name"):
        method = getattr(widget_tree, method_name, None)
        if method is None:
            continue
        try:
            return method(name)
        except Exception:
            continue
    return _walk_widget(getattr(widget_tree, "root_widget", None), name)


def _walk_widget(widget, name):
    if widget is None:
        return None
    if getattr(widget, "name", "") == name or str(widget) == name:
        return widget
    for child in _children(widget):
        found = _walk_widget(child, name)
        if found is not None:
            return found
    return None


def _children(widget):
    if hasattr(widget, "children"):
        return list(widget.children)
    if hasattr(widget, "get_children"):
        return list(widget.get_children() or [])
    count_method = getattr(widget, "get_children_count", None)
    child_method = getattr(widget, "get_child_at", None)
    if count_method is not None and child_method is not None:
        return [child_method(index) for index in range(count_method())]
    return []


def _asset_exists(unreal, asset_path):
    library = getattr(unreal, "EditorAssetLibrary", None)
    if library and hasattr(library, "does_asset_exist"):
        return bool(library.does_asset_exist(asset_path) or library.does_asset_exist(_object_path(asset_path)))
    return False


def _load_asset(unreal, asset_path):
    library = getattr(unreal, "EditorAssetLibrary", None)
    if library and hasattr(library, "load_asset"):
        return library.load_asset(asset_path) or library.load_asset(_object_path(asset_path))
    return None


def _save_asset(unreal, asset_path):
    library = getattr(unreal, "EditorAssetLibrary", None)
    if library and hasattr(library, "save_asset"):
        try:
            return bool(library.save_asset(asset_path, only_if_is_dirty=False))
        except TypeError:
            return bool(library.save_asset(asset_path))
    return False


def _object_path(asset_path):
    if not asset_path or "." in asset_path:
        return asset_path
    name = asset_path.rsplit("/", 1)[-1]
    return asset_path + "." + name


def _class_name(widget):
    cls = getattr(widget, "__class__", None)
    return getattr(cls, "__name__", "") if cls is not None else ""
