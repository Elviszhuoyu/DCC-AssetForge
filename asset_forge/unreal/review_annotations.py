"""Artist-owned groups and color labels stored alongside an immutable review batch."""
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4


ACTIONS = frozenset(("create_group", "rename_group", "toggle_group", "move_asset",
                     "create_tag", "update_tag", "set_tag"))
_FILENAME = "workbench.json"


def empty():
    return {"version": 1, "groups": [], "tags": [], "assets": {}}


def _validate(data):
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError
    for key in ("tags", "groups"):
        items = data.get(key)
        if not isinstance(items, list):
            raise ValueError
        ids = set()
        for entry in items:
            if not isinstance(entry, dict) or not all(isinstance(entry.get(k), str) and entry[k].strip()
                                                      for k in ("id", "name")) or entry["id"] in ids:
                raise ValueError
            ids.add(entry["id"])
            if key == "tags" and not re.fullmatch(r"#[0-9a-fA-F]{6}", str(entry.get("color"))):
                raise ValueError
            if key == "groups" and not isinstance(entry.get("collapsed"), bool):
                raise ValueError
    groups = {g["id"] for g in data["groups"]}
    tags = {t["id"] for t in data["tags"]}
    if not isinstance(data.get("assets"), dict):
        raise ValueError
    for item in data["assets"].values():
        if not isinstance(item, dict) or item.get("group", "") not in groups | {""}:
            raise ValueError
        assigned = item.get("tags", [])
        if not isinstance(assigned, list) or not all(isinstance(i, str) and i in tags for i in assigned):
            raise ValueError


def load(directory):
    try:
        data = json.loads((directory / _FILENAME).read_text(encoding="utf-8"))
        _validate(data)
    except FileNotFoundError:
        return empty()
    except (ValueError, TypeError) as exc:
        raise ValueError("分组标签文件无法读取，已保留原文件。") from exc
    return data


@contextmanager
def _exclusive(directory):
    # The OS releases the byte-range lock even if an editor exits during a write.
    with (directory / ".workbench.lock").open("a+b") as handle:
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ValueError("另一个编辑器正在保存分组标签，请重试。") from exc
        yield


def _entry(items, ident):
    for item in items:
        if item["id"] == ident:
            return item
    raise ValueError("分组或标签已变化，请刷新批次。")


def _edited_field(args, key, entry):
    value = args.get(key)
    if not isinstance(value, str):
        raise ValueError("缺少名称或颜色。")
    value = value.strip()
    original = args.get("original_" + key)
    if key == "color":
        value = value.upper()
        original = original.upper() if isinstance(original, str) else original
    if entry and original is not None:
        current = entry[key]
        if key == "color":
            current = current.upper()
        if original == value:
            return current
        if current not in (original, value):
            raise ValueError("该字段已在另一编辑器中修改。请重新打开表单。")
    return value


def _apply(data, action, args, paths):
    path = args.get("path", "")
    if (path or action in ("move_asset", "set_tag")) and path not in paths:
        raise ValueError("该资产不属于当前批次。")
    group_action = action in ("create_group", "rename_group", "toggle_group", "move_asset")
    key = "group" if group_action else "tag"
    entries = data[key + "s"]
    ident = args.get(key, "")
    if not isinstance(ident, str):
        raise ValueError("请选择有效的分组或标签。")
    if action in ("move_asset", "set_tag"):
        if ident or action == "set_tag":
            _entry(entries, ident)
        item = data["assets"].setdefault(path, {"group": "", "tags": []})
        if action == "move_asset":
            item["group"] = ident
        else:
            if not isinstance(args.get("assigned"), bool):
                raise ValueError("请选择标签的挂载状态。")
            assigned = item.setdefault("tags", [])
            if args["assigned"] and ident not in assigned:
                assigned.append(ident)
            elif not args["assigned"] and ident in assigned:
                assigned.remove(ident)
        if not item.get("group") and not item.get("tags"):
            del data["assets"][path]
        return
    if action == "toggle_group":
        if not isinstance(args.get("collapsed"), bool):
            raise ValueError("缺少分组展开状态。")
        _entry(entries, ident)["collapsed"] = args["collapsed"]
        return
    create = action in ("create_group", "create_tag")
    existing = None if create else _entry(entries, ident)
    name = _edited_field(args, "name", existing)
    if not name or not name.isprintable():
        raise ValueError("请输入单行名称。")
    if any(item["name"].casefold() == name.casefold() and (create or item["id"] != ident) for item in entries):
        raise ValueError("当前批次已有同名分组或标签。")
    entry = {"id": uuid4().hex} if create else existing
    entry["name"] = name
    if group_action:
        entry.setdefault("collapsed", False)
    else:
        color = _edited_field(args, "color", existing)
        if not re.fullmatch(r"#[0-9A-F]{6}", color):
            raise ValueError("请选择有效的六位 RGB 颜色。")
        entry["color"] = color
    if create:
        entries.append(entry)
        if key == "tag" and path:
            item = data["assets"].setdefault(path, {"group": "", "tags": []})
            item.setdefault("tags", []).append(entry["id"])


def update(directory, action, argument, paths):
    try:
        args = json.loads(argument)
    except (ValueError, TypeError) as exc:
        raise ValueError("无法读取分组标签操作。") from exc
    if action not in ACTIONS or not isinstance(args, dict) or not isinstance(args.get("path", ""), str):
        raise ValueError("无法读取分组标签操作。")
    with _exclusive(directory):
        data = load(directory)
        _apply(data, action, args, paths)
        pending = None
        try:
            with NamedTemporaryFile(mode="w", encoding="utf-8", dir=str(directory),
                                    prefix=".workbench-", suffix=".tmp", delete=False) as stream:
                pending = Path(stream.name)
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(str(pending), str(directory / _FILENAME))
            pending = None
        finally:
            if pending is not None:
                pending.unlink()
    return data
