# Contributing to DCC AssetForge

Thank you for helping improve DCC AssetForge. The project currently focuses on a maintainable static-prop workflow between Maya or Blender and Unreal Editor.

## Before opening a change

- Keep product work inside the documented static-prop scope unless an issue explicitly expands it.
- Do not commit proprietary scenes, client assets, textures, engine binaries, generated reports, credentials, cookies, local installation paths, or user-home paths.
- Do not describe fixture, dry-run, JSON readback, commandlet exit code, or static analysis as real host or visual acceptance.
- Preserve compatibility identifiers such as `asset_forge`, `AssetForge`, `/AssetForge`, and existing schema keys unless a migration plan is approved.
- Do not add, replace, or modify project logos or covered icons without maintainer approval. See `BRAND_ASSET_POLICY.md`.
- Use UTF-8. U+FFFD or suspiciously corrupted Chinese text is a stop condition.

## Development setup

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m compileall -q asset_forge integrations scripts tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
.\.venv\Scripts\python.exe scripts\check_repository_hygiene.py
git diff --check
```

The default test suite must not require Maya, Blender, Unreal Engine, or a paid service. Host-specific validation should be documented separately with the exact host version and evidence boundary.

## Pull requests

A useful pull request explains:

- The problem and why it belongs in the current scope.
- The files and compatibility contracts affected.
- Offline test results.
- Any Maya, Blender, or Unreal version actually exercised.
- What remains unverified.

Small, reviewable changes are preferred. Add or update tests for bug fixes and public contract changes.

## Binary and large-file policy

Do not commit `.fbx`, `.blend`, `.ma`, `.mb`, `.uasset`, `.umap`, models, textures, videos, archives, or generated evidence by default. Use tiny programmatically generated fixtures when possible. Git LFS must be proposed and reviewed before introducing a tracked binary asset class; installing Git LFS does not by itself authorize committing assets.

## License

By submitting a contribution, you agree that it may be distributed under the repository's MIT License. Only submit work you have the right to license. Identify copied, generated, adapted, or reference-derived code and its license in the pull request. Brand assets are a separate permission boundary described in `BRAND_ASSET_POLICY.md`.
