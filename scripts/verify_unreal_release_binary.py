"""Check the UE Win64 release DLL for private build paths and valid module metadata."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import struct


PLUGIN_EXPORT = b"ThisIsAnUnrealEngineModule"
DRIVE_PATH = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z]:/(?=[\w.$~-])")
UNC_PATH = re.compile(r"(?<![:/A-Za-z0-9_])//[\w.$-]+/[\w.$-]+/")
PRINTABLE_RUN = re.compile(rb"[^\x00-\x1f\x7f]{6,}")
WIDE_RUN = re.compile(r"[^\x00-\x1f\x7f]{6,}")


def path_indicators(data, private_roots=()):
    """Return distinct matching strings without printing any build-machine paths."""
    roots = tuple(root.replace("\\", "/").rstrip("/").casefold() for root in private_roots if root)
    strings = {part.decode("utf-8", errors="replace") for part in PRINTABLE_RUN.findall(data)}
    for offset in (0, 1):
        wide_text = data[offset:].decode("utf-16-le", errors="replace")
        strings.update(WIDE_RUN.findall(wide_text))

    found = set()
    for value in strings:
        value = value.replace("\\", "/").casefold()
        if DRIVE_PATH.search(value) or UNC_PATH.search(value) or any(root in value for root in roots):
            found.add(value)
    return found


class _PortableExecutable:
    def __init__(self, data):
        self.data = data
        if data[:2] != b"MZ":
            raise ValueError("The DLL has no DOS header.")
        pe = self.read("<I", 0x3c)[0]
        if data[pe:pe + 4] != b"PE\0\0":
            raise ValueError("The DLL has no PE signature.")
        machine, section_count, _, _, _, optional_size, characteristics = self.read("<HHIIIHH", pe + 4)
        optional = pe + 24
        if machine != 0x8664 or not characteristics & 0x2000 or self.read("<H", optional)[0] != 0x20b:
            raise ValueError("The payload must be an x64 PE32+ DLL.")
        if optional_size < 112 + 8 * 7 or self.read("<I", optional + 108)[0] < 7:
            raise ValueError("The PE directory table is incomplete.")
        self.directories = optional + 112
        self.sections = []
        for index in range(section_count):
            section = optional + optional_size + index * 40
            _, rva, length, offset = self.read("<IIII", section + 8)
            if length and offset + length > len(data):
                raise ValueError("A PE section points outside the DLL.")
            self.sections.append((rva, length, offset))

    def read(self, layout, offset):
        try:
            return struct.unpack_from(layout, self.data, offset)
        except struct.error as error:
            raise ValueError("The DLL data is truncated.") from error

    def file_offset(self, rva, length=1):
        for start, size, offset in self.sections:
            if start <= rva and rva + length <= start + size:
                return offset + rva - start
        raise ValueError("A PE directory or string is outside its file sections.")

    def directory(self, index):
        return self.read("<II", self.directories + 8 * index)

    def c_string(self, offset):
        end = self.data.find(b"\0", offset)
        if end == -1:
            raise ValueError("A PE string is missing its terminator.")
        return self.data[offset:end]

    def exports(self):
        address, size = self.directory(0)
        if not address or size < 40:
            raise ValueError("The DLL export directory is missing.")
        export = self.read("<IIHHIIIIIII", self.file_offset(address, 40))
        count, names = export[7], export[9]
        offset = self.file_offset(names, count * 4)
        return {
            self.c_string(self.file_offset(self.read("<I", offset + index * 4)[0]))
            for index in range(count)
        }

    def codeview_paths(self):
        address, size = self.directory(6)
        if not address and not size:
            return []
        if not size or size % 28:
            raise ValueError("The PE debug directory has an invalid length.")
        offset = self.file_offset(address, size)
        paths = []
        for index in range(size // 28):
            *_, kind, length, _, payload = self.read("<IIHHIIII", offset + index * 28)
            if kind != 2:
                continue
            record = self.data[payload:payload + length]
            if len(record) != length or length < 25 or record[:4] != b"RSDS":
                raise ValueError("The CodeView debug entry is incomplete.")
            path, separator, _ = record[24:].partition(b"\0")
            if not separator or not path:
                raise ValueError("The PE debug path is missing its terminator.")
            paths.append(path)
        return paths


def verify_dll(data, private_roots=()):
    pe = _PortableExecutable(data)
    exports = pe.exports()
    paths = pe.codeview_paths()
    leaking_pdb = sum(b"/" in path or b"\\" in path or b":" in path for path in paths)
    leaks = len(path_indicators(data, private_roots))
    has_module_export = PLUGIN_EXPORT in exports
    mappings = {
        "assetforge": data.count(b"AssetForgeSource\\") + data.count(b"AssetForgeSource/"),
        "unreal": data.count(b"UnrealEngineSource\\") + data.count(b"UnrealEngineSource/"),
    }
    return {
        "status": "pass" if has_module_export and not leaking_pdb and not leaks else "fail",
        "sha256": hashlib.sha256(data).hexdigest().upper(),
        "bytes": len(data),
        "machine": "x64",
        "type": "PE32+ DLL",
        "unreal_module_export": has_module_export,
        "export_count": len(exports),
        "codeview_record_count": len(paths),
        "codeview_paths_with_directories": leaking_pdb,
        "private_path_strings": leaks,
        "mapped_diagnostic_paths": mappings,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dll", type=Path)
    parser.add_argument("--private-root", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        report = verify_dll(args.dll.read_bytes(), args.private_root)
    except (OSError, ValueError) as error:
        parser.exit(1, "UE binary verification failed: {}\n".format(error))
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

