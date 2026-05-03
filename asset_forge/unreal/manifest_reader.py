"""Manifest entry point for Unreal-side import tools."""

from __future__ import absolute_import

from asset_forge.shared.manifest_schema import read_manifest, validate_manifest


def load_manifest_for_import(path):
    """Read and validate a manifest before Unreal import."""
    manifest = read_manifest(path)
    issues = validate_manifest(manifest)
    return manifest, issues

