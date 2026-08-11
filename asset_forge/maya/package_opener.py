"""Open exported DCC AssetForge package folders from Maya."""

from __future__ import absolute_import

import os
import subprocess
import sys


def open_directory(path, launcher=None):
    """Open a directory with the host OS file browser."""
    if not path:
        raise RuntimeError("No export package directory is available")

    directory = os.path.abspath(path)
    if not os.path.isdir(directory):
        raise RuntimeError("Export package directory does not exist: {0}".format(directory))

    if launcher is not None:
        launcher(directory)
        return directory

    if sys.platform.startswith("win"):
        os.startfile(directory)
        return directory

    command = ["open", directory] if sys.platform == "darwin" else ["xdg-open", directory]
    subprocess.Popen(command)
    return directory
