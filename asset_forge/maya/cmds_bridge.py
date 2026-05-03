"""Small import bridge for maya.cmds.

Keeping this import lazy lets shared tests run outside Maya.
"""

from __future__ import absolute_import


def get_cmds():
    """Return maya.cmds or None when running outside Maya."""
    try:
        import maya.cmds as cmds
    except ImportError:
        return None
    return cmds

