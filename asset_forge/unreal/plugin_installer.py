"""Install the Asset Forge Unreal plugin into a UE project."""

from __future__ import absolute_import

import datetime
import fnmatch
import hashlib
import io
import json
import os
import re
import shutil


PLUGIN_NAME = "AssetForge"
SKIP_DIRS = {".git", "__pycache__", "Binaries", "Intermediate", "Saved"}
SKIP_PATTERNS = ["*.pyc", "*.pyo"]
RUNTIME_DIRS = ["asset_forge", "config"]


class UnrealPluginInstaller(object):
    """Copy the self-contained Content/Python Asset Forge plugin into a UE project."""

    def __init__(self, source_plugin_dir=None):
        self.source_plugin_dir = os.path.abspath(source_plugin_dir or self._default_source_plugin_dir())

    def plan(self, project_path):
        project_info = self._resolve_project(project_path)
        source_descriptor = os.path.join(self.source_plugin_dir, PLUGIN_NAME + ".uplugin")
        target_dir = os.path.join(project_info.get("project_root", ""), "Plugins", PLUGIN_NAME)
        checks = [
            self._check("source_plugin", os.path.isdir(self.source_plugin_dir), self.source_plugin_dir, "source plugin directory exists", "source plugin directory missing"),
            self._check("source_descriptor", os.path.exists(source_descriptor), source_descriptor, "source .uplugin exists", "source .uplugin missing"),
            self._check("project_root", bool(project_info.get("project_root")), project_info.get("project_root", ""), "UE project root resolved", "cannot resolve UE project root"),
            self._check("project_file", bool(project_info.get("project_file")), project_info.get("project_file", ""), ".uproject exists", ".uproject missing"),
        ]
        descriptor_info = self._descriptor_info(source_descriptor)
        checks.extend(self._runtime_source_checks())
        checks.extend(self._descriptor_compatibility_checks(source_descriptor, descriptor_info))
        can_install = all(item["status"] == "pass" for item in checks)
        action = "update" if os.path.isdir(target_dir) else "install"
        requires_cpp_compile = bool(descriptor_info.get("modules", []))
        skipped_directories = set(SKIP_DIRS)
        if not requires_cpp_compile:
            skipped_directories.add("Source")
        planned_plugin_files = self._planned_plugin_files(target_dir, include_source=requires_cpp_compile)
        planned_runtime_files = self._planned_runtime_files(target_dir)
        planned_metadata_file = self._norm(os.path.join(target_dir, "Content", "Python", "config", "asset_forge_install.json"))
        planned_copied_files = planned_plugin_files + planned_runtime_files + [planned_metadata_file]
        source_hash = self._source_hash(include_source=requires_cpp_compile)
        build_readiness = self._build_readiness(target_dir, requires_cpp_compile, can_install)
        project_target = self._project_target_name(project_info.get("project_file", ""))
        return {
            "status": "ready" if can_install else "error",
            "plugin_name": PLUGIN_NAME,
            "action": action,
            "can_install": can_install,
            "source_plugin_dir": self._norm(self.source_plugin_dir),
            "source_descriptor": self._norm(source_descriptor),
            "project_root": self._norm(project_info.get("project_root", "")),
            "project_file": self._norm(project_info.get("project_file", "")),
            "project_target": project_target,
            "target_plugin_dir": self._norm(target_dir),
            "target_descriptor": self._norm(os.path.join(target_dir, PLUGIN_NAME + ".uplugin")),
            "runtime_source_root": self._norm(self._runtime_source_root()),
            "runtime_target_root": self._norm(os.path.join(target_dir, "Content", "Python")),
            "runtime_directories": list(RUNTIME_DIRS),
            "content_mount": "/AssetForge",
            "requires_editor_restart": True,
            "requires_cpp_compile": requires_cpp_compile,
            "source_hash": source_hash,
            "source_hash_algorithm": "sha256",
            "planned_copied_file_count": len(planned_copied_files),
            "planned_copied_files_sample": planned_copied_files[:20],
            "can_build_after_editor_closed": build_readiness["can_build_after_editor_closed"],
            "blocked_by_running_editor": build_readiness["blocked_by_running_editor"],
            "build_readiness": build_readiness,
            "skipped_directories": sorted(skipped_directories),
            "checks": checks,
        }

    def install(self, project_path, enable_in_project=True, dry_run=False):
        install_plan = self.plan(project_path)
        report = {
            "status": "skipped" if dry_run else "failed",
            "message": "plugin install preflight completed; copy not executed" if dry_run else "plugin install failed",
            "plan": install_plan,
            "copied_files": [],
            "runtime_files": [],
            "post_install_checks": [],
            "enabled_in_project": False,
            "issues": [],
        }
        report.update(self._smoke_evidence(install_plan, dry_run=dry_run))
        if not install_plan["can_install"]:
            report["issues"] = [item["message"] for item in install_plan["checks"] if item["status"] == "error"]
            return report
        if dry_run:
            return report

        report["copied_files"] = self._copy_plugin_tree(
            install_plan["target_plugin_dir"],
            include_source=bool(install_plan.get("requires_cpp_compile", False)),
        )
        report["runtime_files"] = self._copy_runtime_tree(install_plan["target_plugin_dir"])
        report["runtime_files"].append(self._write_install_metadata(install_plan))
        report["post_install_checks"] = self._post_install_checks(install_plan["target_plugin_dir"])
        if enable_in_project:
            report["enabled_in_project"] = self._enable_plugin_in_project(install_plan["project_file"])
        report.update(self._smoke_evidence(install_plan, dry_run=False, report=report))

        failed_checks = [item for item in report["post_install_checks"] if item["status"] == "error"]
        report["issues"].extend([item["message"] for item in failed_checks])
        report["status"] = "error" if failed_checks else "success"
        if failed_checks:
            report["message"] = "AssetForge plugin installed with errors; embedded Python runtime is incomplete."
        elif install_plan.get("requires_cpp_compile", False):
            report["message"] = "AssetForge plugin installed; compile/restart UE so /AssetForge content and the native editor UI can load."
        else:
            report["message"] = "AssetForge plugin installed; restart UE so /AssetForge content and Python menu entries can load."
        return report

    def _resolve_project(self, project_path):
        if not project_path:
            return {"project_root": "", "project_file": ""}
        path = os.path.abspath(project_path)
        if os.path.isfile(path) and path.lower().endswith(".uproject"):
            return {"project_root": os.path.dirname(path), "project_file": path}
        if os.path.isdir(path):
            project_files = [os.path.join(path, name) for name in os.listdir(path) if name.lower().endswith(".uproject")]
            project_file = sorted(project_files)[0] if project_files else ""
            return {"project_root": path, "project_file": project_file}
        return {"project_root": "", "project_file": ""}

    def _default_source_plugin_dir(self):
        return os.path.join(self._runtime_source_root(), "Plugins", PLUGIN_NAME)

    def _runtime_source_root(self):
        return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    def _runtime_source_checks(self):
        root = self._runtime_source_root()
        checks = []
        for dir_name in RUNTIME_DIRS:
            path = os.path.join(root, dir_name)
            checks.append(
                self._check(
                    "runtime_source",
                    os.path.isdir(path),
                    path,
                    "runtime source exists: {0}".format(dir_name),
                    "runtime source missing: {0}".format(dir_name),
                )
            )
        return checks

    def _copy_plugin_tree(self, target_dir, include_source=False):
        copied = []
        if not os.path.isdir(target_dir):
            os.makedirs(target_dir)
        for root, dir_names, file_names in os.walk(self.source_plugin_dir):
            dir_names[:] = [
                name
                for name in dir_names
                if name not in SKIP_DIRS and (include_source or name != "Source")
            ]
            relative_root = os.path.relpath(root, self.source_plugin_dir)
            target_root = target_dir if relative_root == "." else os.path.join(target_dir, relative_root)
            if not os.path.isdir(target_root):
                os.makedirs(target_root)
            for file_name in file_names:
                if self._should_skip_file(file_name):
                    continue
                source_path = os.path.join(root, file_name)
                target_path = os.path.join(target_root, file_name)
                shutil.copy2(source_path, target_path)
                copied.append(self._norm(target_path))
        return copied

    def _planned_plugin_files(self, target_dir, include_source=False):
        return [
            self._norm(os.path.join(target_dir, relative_path))
            for relative_path in self._plugin_relative_files(include_source=include_source)
        ]

    def _planned_runtime_files(self, target_plugin_dir):
        source_root = self._runtime_source_root()
        target_python_dir = os.path.join(target_plugin_dir, "Content", "Python")
        planned = []
        for dir_name in RUNTIME_DIRS:
            source_dir = os.path.join(source_root, dir_name)
            if not os.path.isdir(source_dir):
                continue
            for relative_path in self._directory_relative_files(source_dir):
                planned.append(self._norm(os.path.join(target_python_dir, dir_name, relative_path)))
        return planned

    def _copy_runtime_tree(self, target_plugin_dir):
        copied = []
        source_root = self._runtime_source_root()
        target_python_dir = os.path.join(target_plugin_dir, "Content", "Python")
        if not os.path.isdir(target_python_dir):
            os.makedirs(target_python_dir)
        for dir_name in RUNTIME_DIRS:
            source_dir = os.path.join(source_root, dir_name)
            if os.path.isdir(source_dir):
                copied.extend(self._copy_directory(source_dir, os.path.join(target_python_dir, dir_name)))
        return copied

    def _copy_directory(self, source_dir, target_dir):
        copied = []
        if not os.path.isdir(target_dir):
            os.makedirs(target_dir)
        for root, dir_names, file_names in os.walk(source_dir):
            dir_names[:] = [name for name in dir_names if name not in SKIP_DIRS]
            relative_root = os.path.relpath(root, source_dir)
            target_root = target_dir if relative_root == "." else os.path.join(target_dir, relative_root)
            if not os.path.isdir(target_root):
                os.makedirs(target_root)
            for file_name in file_names:
                if self._should_skip_file(file_name):
                    continue
                source_path = os.path.join(root, file_name)
                target_path = os.path.join(target_root, file_name)
                shutil.copy2(source_path, target_path)
                copied.append(self._norm(target_path))
        return copied

    def _plugin_relative_files(self, include_source=False):
        files = []
        if not os.path.isdir(self.source_plugin_dir):
            return files
        for root, dir_names, file_names in os.walk(self.source_plugin_dir):
            dir_names[:] = [
                name
                for name in dir_names
                if name not in SKIP_DIRS and (include_source or name != "Source")
            ]
            relative_root = os.path.relpath(root, self.source_plugin_dir)
            for file_name in file_names:
                if self._should_skip_file(file_name):
                    continue
                relative_path = file_name if relative_root == "." else os.path.join(relative_root, file_name)
                files.append(self._norm(relative_path))
        return sorted(files)

    def _directory_relative_files(self, source_dir):
        files = []
        if not os.path.isdir(source_dir):
            return files
        for root, dir_names, file_names in os.walk(source_dir):
            dir_names[:] = [name for name in dir_names if name not in SKIP_DIRS]
            relative_root = os.path.relpath(root, source_dir)
            for file_name in file_names:
                if self._should_skip_file(file_name):
                    continue
                relative_path = file_name if relative_root == "." else os.path.join(relative_root, file_name)
                files.append(self._norm(relative_path))
        return sorted(files)

    def _source_hash(self, include_source=False):
        digest = hashlib.sha256()
        for label, path in self._source_hash_inputs(include_source=include_source):
            digest.update(label.encode("utf-8"))
            digest.update(b"\0")
            with open(path, "rb") as stream:
                digest.update(stream.read())
            digest.update(b"\0")
        return digest.hexdigest()

    def _source_hash_inputs(self, include_source=False):
        inputs = []
        for relative_path in self._plugin_relative_files(include_source=include_source):
            inputs.append(("plugin/{0}".format(relative_path), os.path.join(self.source_plugin_dir, relative_path.replace("/", os.sep))))
        source_root = self._runtime_source_root()
        for dir_name in RUNTIME_DIRS:
            source_dir = os.path.join(source_root, dir_name)
            for relative_path in self._directory_relative_files(source_dir):
                inputs.append(("runtime/{0}/{1}".format(dir_name, relative_path), os.path.join(source_dir, relative_path.replace("/", os.sep))))
        return sorted(inputs, key=lambda item: item[0])

    def _build_readiness(self, target_plugin_dir, requires_cpp_compile, can_install):
        if not can_install:
            return {
                "status": "blocked",
                "requires_cpp_compile": requires_cpp_compile,
                "can_build_after_editor_closed": False,
                "blocked_by_running_editor": "not_checked",
                "next_action": "fix installer preflight errors before running UBT",
            }
        if not requires_cpp_compile:
            return {
                "status": "not_required",
                "requires_cpp_compile": False,
                "can_build_after_editor_closed": False,
                "blocked_by_running_editor": "not_applicable",
                "next_action": "restart UE after install so /AssetForge content and Python entries mount",
            }
        external_preflight = self._external_plugin_build_preflight(target_plugin_dir)
        blocking_external = [item for item in external_preflight if item.get("status") == "error"]
        if blocking_external:
            blocker = blocking_external[0]
            return {
                "status": "blocked",
                "requires_cpp_compile": True,
                "can_build_after_editor_closed": False,
                "blocked_by_running_editor": "not_checked",
                "blocked_by_plugin": blocker.get("plugin", ""),
                "blocker_summary": blocker.get("message", ""),
                "external_plugin_preflight": external_preflight,
                "next_action": "fix or disable {0}, then rerun closed-editor UBT".format(blocker.get("plugin", "the external plugin")),
            }
        return {
            "status": "manual_validation_required",
            "requires_cpp_compile": True,
            "can_build_after_editor_closed": True,
            "blocked_by_running_editor": "not_checked",
            "native_editor_module": "AssetForgeEditor",
            "target_binary": self._norm(os.path.join(target_plugin_dir, "Binaries", "Win64", "UnrealEditor-AssetForgeEditor.dll")),
            "external_plugin_preflight": external_preflight,
            "next_action": "close UE Editor, then run UBT for the target project; an open editor can lock the plugin DLL",
        }

    def _external_plugin_build_preflight(self, target_plugin_dir):
        project_root = self._project_root_from_target_plugin_dir(target_plugin_dir)
        if not project_root:
            return []
        bridge_dir = os.path.join(project_root, "Plugins", "UE_MCP_Bridge")
        if not os.path.isdir(bridge_dir):
            return [{"id": "ue_mcp_bridge_present", "plugin": "UE_MCP_Bridge", "status": "not_found", "message": "UE_MCP_Bridge is not installed in this project."}]

        checks = [{"id": "ue_mcp_bridge_present", "plugin": "UE_MCP_Bridge", "status": "pass", "path": self._norm(bridge_dir), "message": "UE_MCP_Bridge is installed in this project."}]
        duplicate_cpp = os.path.join(bridge_dir, "Source", "UE_MCP_Bridge", "Public", "JsonSerializer.cpp")
        checks.append({
            "id": "ue_mcp_bridge_duplicate_json_serializer",
            "plugin": "UE_MCP_Bridge",
            "status": "error" if os.path.exists(duplicate_cpp) else "pass",
            "path": self._norm(duplicate_cpp),
            "message": "duplicate Public/JsonSerializer.cpp source will collide with Private/JsonSerializer.cpp" if os.path.exists(duplicate_cpp) else "Public/JsonSerializer.cpp duplicate source is absent.",
        })

        state_tree_cpp = os.path.join(bridge_dir, "Source", "UE_MCP_Bridge", "Private", "Handlers", "StateTreeHandlers.cpp")
        state_tree_status = "not_found"
        state_tree_message = "StateTreeHandlers.cpp is not present."
        if os.path.exists(state_tree_cpp):
            with io.open(state_tree_cpp, "r", encoding="utf-8", errors="ignore") as stream:
                state_tree_source = stream.read()
            has_runtime_data_call = "GetExecutionRuntimeDataType" in state_tree_source or "ExecutionRuntimeData.InitializeAs" in state_tree_source
            has_57_guard = self._has_statetree_runtime_data_57_guard(state_tree_source)
            state_tree_status = "pass" if (not has_runtime_data_call or has_57_guard) else "error"
            state_tree_message = (
                "StateTree ExecutionRuntimeData path is guarded for UE 5.7+."
                if state_tree_status == "pass"
                else "StateTree ExecutionRuntimeData API is used without the UE 5.7+ guard and can break UE 5.6 builds."
            )
        checks.append({
            "id": "ue_mcp_bridge_statetree_runtime_guard",
            "plugin": "UE_MCP_Bridge",
            "status": state_tree_status,
            "path": self._norm(state_tree_cpp),
            "message": state_tree_message,
        })
        return checks

    def _has_statetree_runtime_data_57_guard(self, source):
        guard_match = re.search(
            r"#define\s+UE_MCP_HAS_STATETREE_EXECUTION_RUNTIME_DATA\s+(.+)",
            source,
        )
        if not guard_match:
            return False
        guard_expression = guard_match.group(1)
        return "ENGINE_MINOR_VERSION >= 7" in guard_expression or "ENGINE_MINOR_VERSION > 6" in guard_expression

    def _project_root_from_target_plugin_dir(self, target_plugin_dir):
        parts = os.path.normpath(target_plugin_dir).split(os.sep)
        if len(parts) >= 2 and parts[-2].lower() == "plugins":
            return os.sep.join(parts[:-2])
        return ""

    def _smoke_evidence(self, install_plan, dry_run=False, report=None):
        copied_files = []
        if report:
            copied_files = list(report.get("copied_files", [])) + list(report.get("runtime_files", []))
        evidence = {
            "target_plugin_dir": install_plan.get("target_plugin_dir", ""),
            "requires_cpp_compile": bool(install_plan.get("requires_cpp_compile", False)),
            "source_hash": install_plan.get("source_hash", ""),
            "source_hash_algorithm": install_plan.get("source_hash_algorithm", "sha256"),
            "project_file": install_plan.get("project_file", ""),
            "project_target": install_plan.get("project_target", ""),
            "planned_copied_file_count": install_plan.get("planned_copied_file_count", 0),
            "planned_copied_files_sample": list(install_plan.get("planned_copied_files_sample", [])),
            "copied_file_count": len(copied_files),
            "copied_files_sample": copied_files[:20],
            "can_build_after_editor_closed": install_plan.get("can_build_after_editor_closed", False),
            "blocked_by_running_editor": install_plan.get("blocked_by_running_editor", "not_checked"),
            "build_readiness": dict(install_plan.get("build_readiness", {})),
        }
        release_boundary = self._release_boundary(evidence, dry_run)
        evidence["release_boundary"] = release_boundary
        return {
            "target_plugin_dir": evidence["target_plugin_dir"],
            "requires_cpp_compile": evidence["requires_cpp_compile"],
            "source_hash": evidence["source_hash"],
            "source_hash_algorithm": evidence["source_hash_algorithm"],
            "project_file": evidence["project_file"],
            "project_target": evidence["project_target"],
            "can_build_after_editor_closed": evidence["can_build_after_editor_closed"],
            "blocked_by_running_editor": evidence["blocked_by_running_editor"],
            "planned_copied_file_count": evidence["planned_copied_file_count"],
            "planned_copied_files_sample": evidence["planned_copied_files_sample"],
            "copied_file_count": evidence["copied_file_count"],
            "copied_files_sample": evidence["copied_files_sample"],
            "release_boundary": release_boundary,
            "install_smoke": evidence,
            "dry_run": dry_run,
        }

    def _release_boundary(self, evidence, dry_run):
        proven = [
            "source plugin scanned",
            "source hash calculated",
            "planned install file list generated",
        ]
        if evidence.get("copied_file_count", 0):
            proven.append("plugin files copied")
        not_proven = []
        next_actions = []
        if dry_run:
            not_proven.append("files were not copied because this was a dry run")
            next_actions.append("run installer without --dry-run when ready to update the target project")
        if evidence.get("requires_cpp_compile"):
            not_proven.append("native editor module has not been linked in a closed-editor UBT build")
            next_actions.append("close UE Editor, then run UBT for the target project")
        else:
            next_actions.append("restart UE Editor so /AssetForge content and Python entries mount")
        can_claim_clean_install = not dry_run and not evidence.get("requires_cpp_compile") and evidence.get("copied_file_count", 0) > 0
        if dry_run:
            status = "dry_run"
        elif can_claim_clean_install:
            status = "ready_after_restart"
        elif evidence.get("build_readiness", {}).get("status") == "blocked":
            status = "blocked"
            blocker = evidence.get("build_readiness", {}).get("blocked_by_plugin", "external plugin")
            summary = evidence.get("build_readiness", {}).get("blocker_summary", "")
            not_proven.append("closed-editor UBT is blocked by {0}: {1}".format(blocker, summary))
            next_actions[:] = [evidence.get("build_readiness", {}).get("next_action", "fix the external plugin blocker, then rerun UBT")]
        elif evidence.get("requires_cpp_compile"):
            status = "manual_validation_required"
        else:
            status = "restart_required"
        return {
            "status": status,
            "can_claim_clean_install": can_claim_clean_install,
            "what_is_proven": proven,
            "what_is_not_proven": not_proven,
            "next_actions": next_actions,
            "manual_validation_commands": self._manual_validation_commands(evidence, dry_run),
        }

    def _manual_validation_commands(self, evidence, dry_run):
        if not evidence.get("requires_cpp_compile"):
            return []
        project_file = evidence.get("project_file", "")
        project_target = evidence.get("project_target", "") or "<ProjectName>Editor"
        target_plugin_dir = evidence.get("target_plugin_dir", "")
        return [
            {
                "step": "close_ue_editor",
                "display_label": "关闭 UE：先关闭当前项目的 UE Editor，避免插件 DLL 被占用。",
                "action": "Close UE Editor for this project before compiling; an open editor can lock plugin DLLs.",
            },
            {
                "step": "run_ubt",
                "display_label": "运行 UBT：使用当前 UE 安装中的 UnrealBuildTool 手动编译目标项目。",
                "command_template": 'UnrealBuildTool.exe {0} Win64 Development -Project="{1}" -WaitMutex -NoHotReloadFromIDE'.format(
                    project_target,
                    project_file or "<Project.uproject>",
                ),
                "project_file": project_file,
                "target_plugin_dir": target_plugin_dir,
                "note": "Template only; resolve UnrealBuildTool from the active UE installation.",
            },
            {
                "step": "claim_boundary_after_success",
                "display_label": "验证边界：只有非 dry-run 安装且关闭编辑器后的 UBT 编译成功，才声明原生模块已链接。",
                "action": "After a non-dry-run install and successful closed-editor UBT build, you may claim the plugin files were installed and the native editor module linked for this project.",
                "dry_run": bool(dry_run),
            },
        ]

    def _post_install_checks(self, target_plugin_dir):
        python_root = os.path.join(target_plugin_dir, "Content", "Python")
        checks = [
            self._check(
                "installed_python_init",
                os.path.exists(os.path.join(python_root, "init_unreal.py")),
                os.path.join(python_root, "init_unreal.py"),
                "installed init_unreal.py exists",
                "installed init_unreal.py missing",
            ),
            self._check(
                "installed_runtime_package",
                os.path.exists(os.path.join(python_root, "asset_forge", "unreal", "editor_menu.py")),
                os.path.join(python_root, "asset_forge", "unreal", "editor_menu.py"),
                "embedded runtime editor_menu.py exists",
                "embedded runtime editor_menu.py missing",
            ),
            self._check(
                "installed_runtime_config",
                os.path.exists(os.path.join(python_root, "config", "material_profiles.json")),
                os.path.join(python_root, "config", "material_profiles.json"),
                "embedded material_profiles.json exists",
                "embedded material_profiles.json missing",
            ),
            self._check(
                "installed_runtime_metadata",
                os.path.exists(os.path.join(python_root, "config", "asset_forge_install.json")),
                os.path.join(python_root, "config", "asset_forge_install.json"),
                "embedded install metadata exists",
                "embedded install metadata missing",
            ),
        ]
        return checks

    def _write_install_metadata(self, install_plan):
        target_path = os.path.join(install_plan["target_plugin_dir"], "Content", "Python", "config", "asset_forge_install.json")
        metadata = {
            "schema_version": "1.0",
            "plugin_name": PLUGIN_NAME,
            "installed_at": datetime.datetime.now().replace(microsecond=0).isoformat(),
            "source_repo_root": self._norm(self._runtime_source_root()),
            "source_latest_maya_log": self._norm(os.path.join(self._runtime_source_root(), "AssetForgeReports", "logs", "latest_maya.log")),
            "target_project_root": install_plan.get("project_root", ""),
            "target_plugin_dir": install_plan.get("target_plugin_dir", ""),
        }
        target_dir = os.path.dirname(target_path)
        if not os.path.isdir(target_dir):
            os.makedirs(target_dir)
        with io.open(target_path, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True))
            stream.write("\n")
        return self._norm(target_path)

    def _descriptor_info(self, descriptor_path):
        if not os.path.exists(descriptor_path):
            return {"descriptor": {}, "modules": []}
        try:
            with io.open(descriptor_path, "r", encoding="utf-8") as stream:
                descriptor = json.load(stream)
        except Exception:
            return {"descriptor": {}, "modules": []}
        return {"descriptor": descriptor, "modules": list(descriptor.get("Modules", []))}

    def _descriptor_compatibility_checks(self, descriptor_path, descriptor_info=None):
        if not os.path.exists(descriptor_path):
            return []
        try:
            info = descriptor_info or self._descriptor_info(descriptor_path)
            descriptor = info.get("descriptor", {})
        except Exception as exc:
            return [self._check("plugin_descriptor_json", False, descriptor_path, "", "cannot read source .uplugin: {0}".format(exc))]

        modules = list(info.get("modules", descriptor.get("Modules", [])))
        checks = [
            self._check(
                "plugin_can_contain_content",
                bool(descriptor.get("CanContainContent", False)),
                descriptor_path,
                "AssetForge plugin can contain Content",
                "AssetForge.uplugin must set CanContainContent=true",
            )
        ]
        if not modules:
            checks.append(
                self._check(
                    "plugin_cpp_modules",
                    True,
                    descriptor_path,
                    "AssetForge plugin is content/Python-only and does not require C++ compile",
                    "AssetForge plugin C++ module check failed",
                )
            )
            return checks

        invalid_modules = [item for item in modules if item.get("Type") != "Editor"]
        checks.append(
            self._check(
                "plugin_cpp_modules",
                not invalid_modules,
                descriptor_path,
                "AssetForge declares Editor C++ module(s); installer will copy Source and require UE compile",
                "AssetForge only supports Editor C++ modules in this installer",
            )
        )
        checks.append(
            self._check(
                "plugin_cpp_source",
                os.path.isdir(os.path.join(self.source_plugin_dir, "Source")),
                os.path.join(self.source_plugin_dir, "Source"),
                "C++ Source directory exists for declared module(s)",
                "AssetForge.uplugin declares C++ module(s), but Source directory is missing",
            )
        )
        return checks

    def _enable_plugin_in_project(self, project_file):
        with io.open(project_file, "r", encoding="utf-8-sig") as stream:
            data = json.load(stream)

        plugins = data.setdefault("Plugins", [])
        for plugin in plugins:
            if plugin.get("Name") == PLUGIN_NAME:
                plugin["Enabled"] = True
                self._write_project(project_file, data)
                return True

        plugins.append({"Name": PLUGIN_NAME, "Enabled": True})
        self._write_project(project_file, data)
        return True

    def _write_project(self, project_file, data):
        with io.open(project_file, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(data, ensure_ascii=False, indent=2))
            stream.write("\n")

    def _project_target_name(self, project_file):
        if not project_file:
            return ""
        project_name = os.path.splitext(os.path.basename(project_file))[0]
        return "{0}Editor".format(project_name) if project_name else ""

    def _should_skip_file(self, file_name):
        return any(fnmatch.fnmatch(file_name, pattern) for pattern in SKIP_PATTERNS)

    def _check(self, check_id, passed, path, pass_message, fail_message):
        return {
            "id": check_id,
            "status": "pass" if passed else "error",
            "path": self._norm(path),
            "message": pass_message if passed else fail_message,
        }

    def _norm(self, path):
        return (path or "").replace("\\", "/")


def plan_assetforge_plugin_install(project_path, source_plugin_dir=None):
    return UnrealPluginInstaller(source_plugin_dir).plan(project_path)


def install_assetforge_plugin(project_path, source_plugin_dir=None, enable_in_project=True, dry_run=False):
    return UnrealPluginInstaller(source_plugin_dir).install(project_path, enable_in_project, dry_run)
