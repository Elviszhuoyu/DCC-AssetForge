"""Compatibility helpers for Unreal Python editor properties."""

from __future__ import absolute_import


def set_unreal_property(obj, name, value):
    """Set an Unreal editor property with a plain attribute fallback."""
    if hasattr(obj, "set_editor_property"):
        try:
            obj.set_editor_property(name, value)
            return True
        except Exception:
            pass

    try:
        setattr(obj, name, value)
        return True
    except Exception:
        return False


def get_unreal_property(obj, name, default=None):
    """Get an Unreal editor property with a plain attribute fallback."""
    if hasattr(obj, "get_editor_property"):
        try:
            return obj.get_editor_property(name)
        except Exception:
            pass

    return getattr(obj, name, default)


def set_first_available_property(obj, names, value):
    """Set the first available property name from a compatibility list."""
    for name in names:
        if set_unreal_property(obj, name, value):
            return name
    return None
