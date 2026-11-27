"""Verify the extracted Windows release, including the standalone x64 WPF installer."""

import argparse
from collections import Counter
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import struct
from zipfile import ZipFile, is_zipfile


DRIVE_PATH = re.compile(
    rb"(?<![a-z0-9_])([a-z]:[/\\]+(?:[a-z0-9_.~$!-][a-z0-9_.~$!() -]{0,79}[/\\]+)"
    rb"+[a-z0-9_.~$!-][a-z0-9_.~$!() -]{0,79})",
    re.IGNORECASE,
)
WIDE_STRINGS = (
    (re.compile(rb"(?:[ -~]\x00){6,}"), "utf-16-le"),
    (re.compile(rb"(?:\x00[ -~]){6,}"), "utf-16-be"),
)
SETUP_EXE = "DCC-AssetForge-Setup.exe"
INSTALLER_RUNTIME = PurePosixPath("Payload/InstallerRuntime")
MAX_SETUP_BYTES = 2 * 1024 * 1024


def check_setup_executable(file):
    data = file.read_bytes()
    if not 1536 <= len(data) <= MAX_SETUP_BYTES or data[:2] != b"MZ":
        raise ValueError("Setup must be a single PE executable at most 2 MiB")
    pe = struct.unpack_from("<I", data, 0x3c)[0]
    optional = pe + 24
    if pe < 0x40 or optional + 232 > len(data) or data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("Invalid Setup PE header")
    if struct.unpack_from("<H", data, pe + 4)[0] != 0x8664 or struct.unpack_from("<H", data, optional)[0] != 0x20b:
        raise ValueError("Setup must target Windows x64")
    directories = struct.unpack_from("<I", data, optional + 108)[0]
    size = struct.unpack_from("<H", data, pe + 20)[0]
    debug = struct.unpack_from("<II", data, optional + 112 + 8 * 6)
    managed = struct.unpack_from("<II", data, optional + 112 + 8 * 14)
    required = (b"BSJB", b"PresentationFramework", b"PresentationCore", b".NETFramework,Version=v4.8")
    if directories < 15 or size < 232 or not all(managed) or not all(value in data for value in required):
        raise ValueError("Setup must contain a .NET Framework 4.8 WPF assembly")
    if (any(debug) and not _only_reproducible_build_marker(data, pe, optional + size, debug)
            or b"MEI\x0c\x0b\x0a\x0b\x0e" in data):
        raise ValueError("Setup contains a symbol or self-extracting directory")


def _only_reproducible_build_marker(data, pe, section_start, directory):
    # The deterministic C# compiler emits one empty reproducible-build record without a PDB.
    rva, size = directory
    count = struct.unpack_from("<H", data, pe + 6)[0]
    if size != 28 or section_start + count * 40 > len(data):
        return False
    for index in range(count):
        _, address, raw_size, offset = struct.unpack_from("<IIII", data, section_start + 40 * index + 8)
        if address <= rva and rva + size <= address + raw_size:
            start = offset + rva - address
            return start + size <= len(data) and struct.unpack_from("<IIHHIIII", data, start) == (0, 0, 0, 0, 16, 0, 0, 0)
    return False


DEVELOPMENT_CONFIG_MARKERS = (
    b"sm_vivecontroller",
    b"gatefinish",
    b"/game/assetforgeqa",
    b"assetforgeautomation",
    b"sandbox_ue58",
)


def _has_development_config(path, data):
    if path.suffix.casefold() not in (".json", ".ini", ".toml"):
        return False
    parents = {part.casefold() for part in path.parts[:-1]}
    if not (parents.intersection(("config", "presets")) or path.name.casefold().endswith(".assetforge.json")):
        return False
    for view in _scan_views(data):
        normalized = view.lower().replace(b"\\", b"/")
        if any(marker in normalized for marker in DEVELOPMENT_CONFIG_MARKERS):
            return True
    return False


PUBLIC_IDENTITY = (
    "卓雨 (Elviszhuoyu)",
    "© 2026 Elviszhuoyu",
    "Copyright (c) 2026 Elviszhuoyu",
    "https://github.com/Elviszhuoyu/DCC-AssetForge",
    "https://work.zhuoyulabs.com",
)
PUBLIC_IDENTITY_ENCODINGS = (
    ("utf-8", rb"[a-zA-Z0-9_.-]"),
    ("utf-16-le", rb"[a-zA-Z0-9_.-]\x00"),
    ("utf-16-be", rb"\x00[a-zA-Z0-9_.-]"),
)


def _public_identity_patterns():
    for value in PUBLIC_IDENTITY:
        for encoding, continuation in PUBLIC_IDENTITY_ENCODINGS:
            encoded = re.escape(value.encode(encoding))
            yield re.compile(encoded + rb"(?!" + continuation + rb")")
        escaped = json.dumps(value, ensure_ascii=True)[1:-1]
        if escaped != value:
            yield re.compile(re.escape(escaped.encode("ascii")) + rb"(?![a-zA-Z0-9_.-])")


PUBLIC_IDENTITY_PATTERNS = tuple(_public_identity_patterns())


def _without_public_identity(data):
    for pattern in PUBLIC_IDENTITY_PATTERNS:
        data = pattern.sub(lambda match: b" " * len(match[0]), data)
    return data


def _scan_views(data):
    yield data
    for pattern, encoding in WIDE_STRINGS:
        for match in pattern.finditer(data):
            yield match[0].decode(encoding).encode("ascii")


def _portable_name(name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
        raise ValueError("Unsafe archive entry")
    return path


def _checksums(root, files):
    manifest = root / "SHA256SUMS.txt"
    expected = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        sha256, name = line.split("  ", 1)
        if not re.fullmatch("[a-f0-9]{64}", sha256) or name in expected:
            raise ValueError("Invalid SHA256SUMS.txt")
        expected[_portable_name(name).as_posix()] = sha256
    names = {file.relative_to(root).as_posix() for file in files if file != manifest}
    if names != expected.keys():
        raise ValueError("SHA256SUMS.txt does not cover the extracted files")
    for name, sha256 in expected.items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != sha256:
            raise ValueError("Checksum failed for " + name)
    return len(expected)


class ReleaseAudit:
    def __init__(self, sensitive_roots):
        self.entries = Counter()
        self.hits = Counter()
        self.samples = []
        self.terms = set()
        for root in sensitive_roots:
            normalized = str(root).replace("\\", "/").rstrip("/").lower()
            for value in (normalized, normalized.replace("/", "\\"), normalized.replace("/", "\\\\")):
                self.terms.update(value.encode(encoding) for encoding in ("utf-8", "utf-16-le", "utf-16-be"))
        user = os.environ.get("USERNAME")
        self.username = None
        if user and len(user) >= 3:
            self.username = re.compile(rb"(?<![a-z0-9_-])" + re.escape(user.encode("utf-8")) +
                                       rb"(?![a-z0-9_-])", re.IGNORECASE)

    def _finding(self, name, category, sample=b""):
        self.hits[category] += 1
        if len(self.samples) < 80:
            finding = {"member": name, "category": category}
            if sample:
                finding["root_sha256_prefix"] = hashlib.sha256(sample.lower()).hexdigest()[:12]
            self.samples.append(finding)

    def _scan_bytes(self, name, data):
        lowered = data.lower()
        if any(term in lowered for term in self.terms):
            self._finding(name, "known_machine_root")
        if self.username:
            # Only the username check can ignore exact public identity strings.
            if any(self.username.search(view) for view in _scan_views(_without_public_identity(data))):
                self._finding(name, "local_username")
        seen = set()
        for view in _scan_views(data):
            for match in DRIVE_PATH.finditer(view):
                path = re.sub(rb"[/\\]+", b"/", match[1].lower()).rstrip()
                if path in seen:
                    continue
                seen.add(path)
                self._finding(name, "windows_absolute_path", path)

    def _scan_member(self, name, data, kind):
        leaf = name.rsplit("!", 1)[-1]
        path = _portable_name(leaf)
        self.entries[kind] += 1
        self._scan_bytes(name, data)
        self._scan_bytes(name, name.encode("utf-8"))
        if path.suffix.lower() == ".pdb":
            self._finding(name, "pdb_file")
        if _has_development_config(path, data):
            self._finding(name, "development_config")
        if is_zipfile(BytesIO(data)):
            with ZipFile(BytesIO(data)) as archive:
                for info in archive.infolist():
                    if not info.is_dir():
                        self._scan_member(name + "!" + info.filename, archive.read(info), "embedded_zip")

    def scan(self, root):
        files = sorted(file for file in root.rglob("*") if file.is_file())
        if (root / INSTALLER_RUNTIME).exists():
            raise ValueError("The standalone installer cannot ship Payload/InstallerRuntime")
        for file in files:
            if file.is_symlink() or root not in file.resolve().parents:
                raise ValueError("Unexpected file redirection in extraction")
            name = file.relative_to(root).as_posix()
            self._scan_member(name, file.read_bytes(), "extracted_file")
            if name == SETUP_EXE:
                check_setup_executable(file)

        covered = _checksums(root, files) if (root / "SHA256SUMS.txt").is_file() else 0
        return {
            "status": "pass" if not self.hits and covered else "fail",
            "entries": dict(self.entries),
            "sha256_verified_files": covered,
            "privacy_findings": dict(self.hits),
            "redacted_findings": self.samples,
        }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("extracted_root", type=Path)
    parser.add_argument("--machine-root", type=Path, action="append", default=[])
    args = parser.parse_args(argv)
    roots = [
        Path(__file__).resolve().parents[1], Path.home(), Path(sys.base_prefix),
        *args.machine_root,
    ]
    report = ReleaseAudit(roots).scan(args.extracted_root.resolve(strict=True))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
