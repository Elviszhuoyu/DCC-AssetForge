"""Preview and remove only AssetForge-owned, disposable workbench files."""

from __future__ import absolute_import

import datetime
import errno
import os
import re
import stat
import sys


_HOSTS = ("maya", "unreal")
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)

try:
    _text_type = unicode
except NameError:
    _text_type = str


def _is_reparse(path, info):
    attributes = getattr(info, "st_file_attributes", None)
    if os.name == "nt" and attributes is None:
        # Maya's older embedded Python does not include Windows attributes in lstat results.
        from ctypes import windll
        wide_path = path if isinstance(path, _text_type) else path.decode(sys.getfilesystemencoding())
        attributes = windll.kernel32.GetFileAttributesW(wide_path)
    return stat.S_ISLNK(info.st_mode) or bool((attributes or 0) & _REPARSE_POINT)


def _directory_status(directory):
    parent = directory
    while True:
        try:
            info = os.lstat(parent)
        except OSError as exc:
            return "missing" if exc.errno == errno.ENOENT else "unavailable"
        if not stat.S_ISDIR(info.st_mode) or _is_reparse(parent, info):
            return "unavailable"
        next_parent = os.path.dirname(parent)
        if next_parent == parent:
            return "ready"
        parent = next_parent


def _regular_files(directory):
    try:
        for name in os.listdir(directory):
            path = os.path.join(directory, name)
            try:
                info = os.lstat(path)
            except OSError:
                continue
            if stat.S_ISREG(info.st_mode) and not _is_reparse(path, info) and info.st_nlink == 1:
                yield path, name, info
    except OSError:
        return


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size, getattr(info, "st_mtime_ns", info.st_mtime))


def _cache_directories(host, log_directory):
    if host not in _HOSTS:
        raise ValueError("Unsupported AssetForge workbench host")
    if log_directory is None:
        if host == "maya":
            from asset_forge.maya.operation_logger import logs_dir
        else:
            from asset_forge.unreal.operation_logger import logs_dir
        log_directory = logs_dir()
    logs = os.path.abspath(str(log_directory) if not isinstance(log_directory, _text_type) else log_directory)
    reports = os.path.dirname(logs)
    if os.path.basename(logs) != "logs" or os.path.basename(reports) != "AssetForgeReports":
        return {}
    return {"logs": logs, "reports": os.path.join(reports, "workbench_cache", host)}


def existing_cache_directory(host, kind, log_directory=None):
    """Resolve a workbench directory by Id, rechecking the location before opening it."""
    if kind not in ("logs", "reports"):
        return None
    directory = _cache_directories(host, log_directory).get(kind)
    return directory if directory and _directory_status(directory) == "ready" else None


def manage_cache(host, clear=False, log_directory=None):
    """Keep today's operation log, the latest mirror, and persisted package reports."""
    directories = _cache_directories(host, log_directory)
    total = dict(bytes=0, eligible_bytes=0, eligible_files=0, removed_bytes=0, removed_files=0,
                 failed_files=0, directories=[])

    today = datetime.date.today()
    today_stamp = today.strftime("%Y%m%d")
    dated_log = re.compile(r"asset_forge_" + host + r"_(\d{8})\.jsonl\Z")
    report_cache = re.compile(r"workbench_[a-z0-9_-]{1,80}\.(json|html|tmp)\Z")

    for kind in ("logs", "reports"):
        if kind not in directories:
            continue
        directory = directories[kind]
        status = _directory_status(directory)
        entry = dict(id=kind, path=directory, exists=status == "ready", status=status,
                     bytes=0, eligible_bytes=0, eligible_files=0)
        total["directories"].append(entry)
        if not entry["exists"]:
            continue
        for path, name, info in _regular_files(directory):
            written = datetime.date.fromtimestamp(info.st_mtime)
            if kind == "logs":
                match = dated_log.match(name)
                if not match and name != "latest_" + host + ".log":
                    continue
                eligible = bool(match and match.group(1) < today_stamp and written < today)
            else:
                if not report_cache.match(name):
                    continue
                eligible = written < today

            if eligible and clear:
                try:
                    # A concurrent writer or replacement invalidates the previewed file identity.
                    current = os.lstat(path)
                    if (_is_reparse(path, current) or not stat.S_ISREG(current.st_mode) or current.st_nlink != 1
                            or _identity(current) != _identity(info)):
                        total["failed_files"] += 1
                    else:
                        os.unlink(path)
                        total["removed_files"] += 1
                        total["removed_bytes"] += info.st_size
                        continue
                except OSError:
                    total["failed_files"] += 1
            if eligible:
                entry["eligible_files"] += 1
                entry["eligible_bytes"] += info.st_size
            entry["bytes"] += info.st_size
        for key in ("bytes", "eligible_bytes", "eligible_files"):
            total[key] += entry[key]
    return total
