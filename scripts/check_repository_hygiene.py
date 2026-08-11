"""Fail CI when the tracked public tree crosses DCC AssetForge safety boundaries."""

from __future__ import absolute_import, print_function

import os
import re
import subprocess
import sys


TEXT_EXTENSIONS = {
    "",
    ".cs",
    ".cpp",
    ".h",
    ".ini",
    ".json",
    ".md",
    ".mod",
    ".py",
    ".toml",
    ".txt",
    ".uplugin",
    ".yml",
    ".yaml",
}

FORBIDDEN_ROOTS = (
    ".tmp/",
    "assetforgereports/",
    "dev_doc/",
    "offline_static_prop_sample/",
    "测试/",
)

FORBIDDEN_BINARY_EXTENSIONS = {
    ".7z",
    ".abc",
    ".blend",
    ".fbx",
    ".ma",
    ".mb",
    ".obj",
    ".rar",
    ".uasset",
    ".umap",
    ".usd",
    ".usda",
    ".usdc",
    ".zip",
}

PRIVATE_MARKERS = (
    "/".join(("c:", "users", "elvis", "")),
    "/".join(("e:", "my_work", "ta_mytools", "")),
    "/".join(("j:", "ue_5.6", "")),
    "/".join(("w:", "ue_pj", "")),
    "/".join(("z:", "steamlibrary", "")),
    "/".join(("z:", "ue_pj", "")),
)

SENSITIVE_FILENAMES = {
    ".env",
    ".env.local",
    "id_dsa",
    "id_ed25519",
    "id_rsa",
}

MAX_TRACKED_BYTES = 5 * 1024 * 1024

SECRET_PATTERNS = (
    ("private key block", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("OpenAI-style key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    (
        "credential assignment",
        re.compile(
            r"(?i)\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|secret)\b"
            r"\s*[:=]\s*['\"][^'\"\r\n]{8,}['\"]"
        ),
    ),
)

FENCED_CODE_PATTERN = re.compile(r"```.*?```", re.DOTALL)
MARKDOWN_LINK_PATTERN = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
URL_SCHEME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")


def tracked_paths():
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        check=True,
        stdout=subprocess.PIPE,
    )
    return [item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def check_path(path):
    issues = []
    normalized = path.replace("\\", "/")
    lowered = normalized.lower()
    extension = os.path.splitext(lowered)[1]
    filename = os.path.basename(lowered)

    if lowered.startswith(FORBIDDEN_ROOTS):
        issues.append("local/generated path is tracked")
    if extension in FORBIDDEN_BINARY_EXTENSIONS:
        issues.append("DCC/engine/archive binary is tracked without an approved LFS policy")
    if filename in SENSITIVE_FILENAMES or filename.endswith((".key", ".p12", ".pfx", ".pem")):
        issues.append("sensitive filename is tracked")

    disk_path = os.path.abspath(path)
    if not os.path.isfile(disk_path):
        return issues
    size = os.path.getsize(disk_path)
    if size > MAX_TRACKED_BYTES:
        issues.append("tracked file exceeds 5 MiB")

    if extension in TEXT_EXTENSIONS or filename in {"license", "notice"}:
        with open(disk_path, "rb") as stream:
            raw = stream.read()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            issues.append("text file is not valid UTF-8")
            return issues
        if "\ufffd" in text:
            issues.append("text file contains U+FFFD")
        normalized_text = text.replace("\\", "/").lower()
        if any(marker in normalized_text for marker in PRIVATE_MARKERS):
            issues.append("text contains a maintainer-only absolute path")
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(text):
                issues.append("text matches secret pattern: {0}".format(label))
        if extension == ".md":
            issues.extend(check_markdown_links(path, text))
    return issues


def check_markdown_links(path, text):
    issues = []
    searchable = FENCED_CODE_PATTERN.sub("", text)
    base_dir = os.path.dirname(os.path.abspath(path))
    for match in MARKDOWN_LINK_PATTERN.finditer(searchable):
        target = match.group(1).strip().strip("<>")
        if not target or target.startswith("#") or URL_SCHEME_PATTERN.match(target):
            continue
        relative_target = target.split("#", 1)[0].split("?", 1)[0]
        if not relative_target:
            continue
        resolved = os.path.normpath(os.path.join(base_dir, relative_target.replace("/", os.sep)))
        if not os.path.exists(resolved):
            issues.append("Markdown link target does not exist: {0}".format(target))
    return issues


def main():
    failures = []
    paths = tracked_paths()
    for path in paths:
        for issue in check_path(path):
            failures.append((path, issue))

    if failures:
        print("Public repository hygiene check failed:")
        for path, issue in failures:
            print("- {0}: {1}".format(path, issue))
        return 1

    print("Public repository hygiene check passed for {0} public files.".format(len(paths)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
