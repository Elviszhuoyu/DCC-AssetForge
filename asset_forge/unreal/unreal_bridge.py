"""Small import bridge for Unreal Python."""

from __future__ import absolute_import


def get_unreal():
    """Return unreal module or None when running outside Unreal Editor."""
    try:
        import unreal
    except ImportError:
        return None
    return unreal
