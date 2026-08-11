# AGENTS.md

This is the public agent entry point for DCC AssetForge.

## Start here

Before changing the repository, read:

1. `README.md`
2. `CONTRIBUTING.md`
3. `SECURITY.md`
4. The code, tests, manifest, and host integration files directly affected by the task

Maintainers may also keep ignored local status files under `docs/`. If those files exist, read the applicable `CURRENT`, `CURRENT_TASK`, `HANDOFF`, and architecture contracts without adding them to the public Git index.

## Encoding safety

All text files must remain UTF-8.

Stop writing and report the problem when:

- U+FFFD appears.
- Chinese text looks corrupted.
- The same patch fails twice.
- The checked-out baseline appears damaged.

## Public repository safety

- Preserve user-owned dirty, ignored, generated, and local test files.
- Do not use `git reset`, `git checkout --`, `git clean`, history rewriting, or force push unless the maintainer explicitly authorizes the exact action.
- Never print or commit credentials, cookies, private keys, private paths, proprietary assets, engine binaries, generated evidence, or client data.
- Do not treat deletion from the latest tree as removal from Git history.
- Repository rename, visibility change, Release creation, and external application submission are separate confirmation gates.

## Product and compatibility boundaries

The public brand is **DCC AssetForge**.

The following are compatibility identifiers, not alternate product brands:

- `asset_forge`
- `AssetForge` and `AssetForgeEditor`
- `/AssetForge`
- `ASSET_FORGE_*` and existing schema/report keys

Do not rename compatibility identifiers without a migration plan and backward-compatibility tests.

The current product focus is the static-prop workflow between Maya or Blender and Unreal Editor. Do not expand ordinary maintenance work into 3ds Max, skeletal mesh, animation, a standalone application, or a general asset-management platform.

## Evidence rules

Use this evidence order:

1. Current code and tests.
2. Real host behavior and captured reports.
3. Public contracts and documentation.
4. Ignored local maintainer status files.

Host-independent tests, fixtures, dry runs, JSON readback, commandlet exit codes, and static checks do not prove real Maya/Blender/Unreal behavior or visual quality. Mark unexecuted host validation as `unverified`.

## Verification

For public-source changes, run the relevant subset plus:

```powershell
py -3 -m compileall -q asset_forge integrations scripts tests
py -3 -m unittest discover -s tests -p "test_*.py"
py -3 scripts\check_repository_hygiene.py
git diff --check
```

Do not start Maya, Blender, or Unreal Editor unless the task explicitly requires host validation and the maintainer has accepted that cost and side effect.
