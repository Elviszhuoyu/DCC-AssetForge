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

## UI, UX, and host-lifecycle invariants

When modifying Maya or Unreal UI, validation presentation, or host workflows, preserve these contracts across **all** rules and views (never patch only a single mentioned rule):

- **Unified diagnostic contract**: Every validation rule must surface human-readable copy (`actual vs expected`, impact/blocking status, and a context-appropriate action). Never expose raw Python dicts, internal English schema keys, or stack traces in primary artist UI. Keep passed checks inspectable in a collapsible section.
- **Honest state & pinned context**: Empty/initial state must never show an error badge. Clicking empty viewport space must not clear an active inspection report. Local re-checks must preserve real warning/blocking severity rather than overwriting it with a neutral "rechecked" state.
- **No dead controls or split workbenches**: Never leave permanently disabled placeholder icons in toolbars; embed context-only actions inside their diagnostic cards. Keep Unreal Gate (package import) and Batch Review unified in one native `FAppStyle` workbench window with clear mode tabs.
- **Non-intrusive feedback & safe file reveal**: Keep routine check results, inline import confirmations, and completion summaries inside the workbench—do not use alarming warning modal dialogs for non-blocking flows. Reveal raw `.json` reports/caches in the OS file manager rather than invoking the default OS file association.
- **Visual discipline**: Maya workbench uses strictly neutral grayscale (`R = G = B`, zero blue tint), unified dropdown/input surfaces, crisp corners, and custom-styled controls (no unstyled OS bright-blue checkboxes or default yellow focus outlines). Unreal workbench uses 100% native `FAppStyle`. Verify zero widget overlap, zero clipping, and zero horizontal overflow at both 100% and 150% DPI scaling across primary and secondary views.
- **Persistence & zero host side effects**: Live results, persisted report readback, workbench close/reopen, minimize/restore, and real-workspace cold start must show consistent localized copy and active handoff CTAs. Read-only inspection and asset import must never dirty plugin master materials or modify protected source assets. Reuse validated check caches on confirm instead of re-running redundant full preflight passes.
- **Component & scene fidelity**: Degenerate face/edge localization must select real polygon faces or edges while retaining visual markers (keeping vertex conversion as an explicit user action). Auto-detect valid textures already linked in the Maya scene when no external texture override is set.

## Evidence rules

Use this evidence order:

1. Current code and tests.
2. Real host behavior and captured reports.
3. Public contracts and documentation.
4. Ignored local maintainer status files.

Host-independent tests, fixtures, dry runs, JSON readback, commandlet exit codes, and static checks do not prove real Maya/Blender/Unreal behavior or visual quality. Mark unexecuted host validation as `unverified`.

## Pre-handoff user-perspective audit

Before reporting any UI or host workflow task as complete, inspect the actual captured screenshots and verify:

1. **Cold start & empty state**: Real workspace cold start produces no empty shell, no false error badge, and no unclickable toolbar icon.
2. **Reopen parity**: Closing and reopening the workbench preserves localized summaries, imported state, and review handoff entry points.
3. **Layout integrity**: All collapsible sections and secondary pages (settings, rules, logs, strategy panels) render with zero overlap or clipping under narrow widths and 100%/150% scaling.
4. **Action closure**: Every displayed warning, cache entry, or report path offers a clear, working next step.

## Unreal host test workspaces

- UE 5.6 host validation and native test builds reuse the existing AssetForgeAutomation project identified in the ignored `.tmp/UE_TEST_WORKSPACES.local.md` note.
- UE 5.8 host validation and native test builds reuse the sole fixed project at `.tmp/sandbox_ue58`, on the workspace drive.
- Never create or clone a temporary Unreal test project, including under `.tmp`. Check the version and descriptor of the designated fixed project before a host run. Report an unavailable workspace instead of opening a substitute.
- Between runs, clear only disposable test assets under `/Game/AssetForgeQA/` and the previous run's receipts. Reuse Binaries, Intermediate, and DerivedDataCache. Keep active user sessions, source assets, and acceptance evidence.

## Verification

For public-source changes, run the relevant subset plus:

```powershell
py -3 -m compileall -q asset_forge integrations scripts tests
py -3 -m unittest discover -s tests -p "test_*.py"
py -3 scripts\check_repository_hygiene.py
git diff --check