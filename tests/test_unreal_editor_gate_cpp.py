from __future__ import absolute_import

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
GATE_SOURCE = REPO_ROOT / "Plugins" / "AssetForge" / "Source" / "AssetForgeEditor" / "Private" / "AssetForgeEditorModule.cpp"
REVIEW_SOURCE = GATE_SOURCE.with_name("SAssetForgeReview.cpp")
COMMENT_SOURCE = REPO_ROOT / "Plugins" / "AssetForge" / "Source" / "AssetForgeEditor" / "Private" / "AssetForgeEditorMaterialCommentLibrary.cpp"


class UnrealEditorGateCppTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = GATE_SOURCE.read_text(encoding="utf-8")

    def test_gate_registers_editor_entry_points(self):
        source = self.source

        self.assertIn("RegisterNomadTabSpawner", source)
        self.assertIn("AssetForge.OpenGateWorkbench.Tools", source)
        self.assertIn("AssetForge.OpenGateWorkbench.Window", source)
        self.assertIn("AssetForge.OpenGateWorkbench.Toolbar", source)
        self.assertIn("AssetForge.OpenGate", source)
        self.assertIn("RegisterConsoleCommand", source)
        self.assertIn("UnregisterConsoleObject", source)
        self.assertIn('UnregisterConsoleObject(TEXT("AssetForge.OpenGate"), false)', source)
        self.assertIn("AssetForge 工作台", source)
        self.assertIn('TEXT("Workbench.Mode.Import")', source)
        self.assertIn('TEXT("Workbench.Mode.Review")', source)
        self.assertIn("AssetForge.Review", source)
        self.assertIn("SWidgetSwitcher", source)

    def test_mode_labels_share_the_active_page_and_keep_both_scopes_visible(self):
        shell = self.source.split("class SWorkbench : ", 1)[1].split("static TWeakPtr<SWorkbench>", 1)[0]
        for title in ("包体导入", "入库批审", "DCC → UE", "UE 存量体检"):
            self.assertIn('"' + title + '"', shell)
        self.assertIn(".OnClicked_Lambda([this, Page](){ Show(Page);", shell)
        self.assertNotIn("OnValueChanged", shell)
        open_workbench = self.source.split("void FAssetForgeEditorModule::OpenGateWorkbench()", 1)[1]
        self.assertNotIn("Show(0)", open_workbench)
        self.assertIn("ActivePage() == Page", shell)
        self.assertIn("FStyleColors::Primary", shell)
        self.assertIn("Pages->SetActiveWidgetIndex(Page)", shell)

    def test_batch_confirm_consumes_click_and_defers_python_until_busy_is_visible(self):
        review = REVIEW_SOURCE.read_text(encoding="utf-8")
        self.assertIn('TEXT("apply"),{},TEXT("Icons.Check")', review)
        self.assertIn("Run(Action,Argument); return FReply::Handled();", review)
        self.assertNotIn("OpenGateWorkbench", review)
        self.assertNotIn("SetActiveWidgetIndex", review)
        run = review.split("    void Run(", 1)[1].split("    void Execute(", 1)[0]
        self.assertIn("if (!PendingAction.IsEmpty()) return;", run)
        self.assertLess(run.index("PendingAction = Action"), run.index("RegisterActiveTimer"))
        self.assertLess(run.index("Feedback->SetText"), run.index("RegisterActiveTimer"))
        self.assertLess(run.index("RegisterActiveTimer"), run.index("Execute(Action, Argument);", run.index("RegisterActiveTimer")))
        self.assertIn('FName(TEXT("Passed"))', review)
        self.assertIn('Items(State,TEXT("passed"))', review)

    def test_review_toolbar_has_discoverable_stock_rules(self):
        review = REVIEW_SOURCE.read_text(encoding="utf-8")
        self.assertIn('.Tag(TEXT("Review.Rules"))', review)
        self.assertIn('TEXT("批审规则")', review)
        self.assertIn("下次存量检查的目标平台", review)
        self.assertIn("下次存量检查的材质规则", review)
        self.assertIn('Str(*Policy,TEXT("limits"))', review)

    def test_overlapping_roots_share_a_set_of_full_manifest_paths(self):
        self.assertIn("int32 Depth, TSet<FString>& OutManifestPaths", self.source)
        self.assertIn("OutManifestPaths.Add(Directory / Manifest)", self.source)
        self.assertIn("TSet<FString> Manifests;\n        for (const FString& Root : ScanRoots)", self.source)
        self.assertIn("FindManifestsRecursive(Root, 0, Manifests)", self.source)

    def test_gate_uses_semantic_editor_controls(self):
        source = self.source

        for control in ["SSearchBox", "SListView", "SCheckBox", "SExpandableArea"]:
            self.assertIn(control, source)
        for section in ["包体来源", "导入策略", "包体摘要", "历史与报告"]:
            self.assertIn(section, source)

    def test_workbench_settings_uses_the_top_bar_and_confirms_cache_cleanup(self):
        workbench = self.source.split("class SWorkbench : public SCompoundWidget", 1)[1]
        top_bar = workbench.split("void Construct(", 1)[1].split("void Show(", 1)[0]
        self.assertLess(top_bar.index("GateVersionLabel"), top_bar.index('Tag(TEXT("Workbench.Settings"))'))
        for label in ("通用偏好", "清理缓存", "清理历史缓存与日志", "关于", "DCC AssetForge v0.2.0", "前往 GitHub Releases 检查更新"):
            self.assertIn(label, workbench)
        self.assertIn("FEngineVersion::Current()", workbench)
        self.assertIn("https://github.com/Elviszhuoyu/DCC-AssetForge/releases", workbench)
        self.assertIn("manage_cache('unreal', clear=%s)", workbench)
        self.assertIn("RefreshCacheStatus(false)", workbench)
        direct, confirm = workbench.split('Tag(TEXT("Workbench.Cache.Confirm"))', 1)
        confirm, cancel = confirm.split('Tag(TEXT("Workbench.Cache.Cancel"))', 1)
        self.assertNotIn("RefreshCacheStatus(true)", direct)
        self.assertNotIn("RefreshCacheStatus(true)", cancel)
        self.assertLess(confirm.index("if (bCacheClearArmed)"), confirm.index("RefreshCacheStatus(true)"))

    def test_workbench_cache_lists_each_backend_directory_and_only_opens_existing_folders(self):
        workbench = self.source.split("class SWorkbench : public SCompoundWidget", 1)[1]
        self.assertIn('TryGetArrayField(TEXT("directories")', workbench)
        self.assertIn('TryGetStringField(TEXT("path"), Directory.Path)', workbench)
        self.assertIn('TryGetBoolField(TEXT("exists"), Directory.bExists)', workbench)
        self.assertIn("FPaths::IsRelative(Directory.Path)", workbench)
        self.assertIn("目录尚未创建或不可用", workbench)
        self.assertIn('BuildCacheDirectoryRow(TEXT("logs"), TEXT("Workbench.Cache.Open.Logs")', workbench)
        self.assertIn('BuildCacheDirectoryRow(TEXT("reports"), TEXT("Workbench.Cache.Open.Reports")', workbench)
        opener = workbench.split("FReply OpenCacheDirectory(", 1)[1].split("TSharedRef<SWidget> BuildCacheDirectoryRow", 1)[0]
        self.assertIn("CacheDirectories.Find(DirectoryId)", opener)
        self.assertIn("Directory && Directory->bExists", opener)
        self.assertLess(opener.index("FPaths::DirectoryExists(Directory->Path)"), opener.index("FPlatformProcess::ExploreFolder(*Directory->Path)"))
        self.assertNotIn("LaunchFileInDefaultExternalApplication", opener)

    def test_imported_reopen_copy_matches_the_verified_review_action(self):
        source = self.source
        selection = source.split("void OnPackageSelected(", 1)[1].split("void LoadSelectedReportDetails(", 1)[0]
        refresh = source.split("void RefreshPackages()", 1)[1].split("TSharedPtr<FAssetForgePackageItem> FindFilteredPackageByDir", 1)[0]
        self.assertIn("该包体已导入，可直接前往「入库批审」查验本次资产", source)
        self.assertLess(selection.index("LoadSelectedReportDetails();"), selection.index("CanReviewSelectedImport()"))
        self.assertIn("CanReviewSelectedImport()", refresh)

    def test_gate_report_path_has_open_action(self):
        source = self.source

        self.assertIn("GetReportPath", source)
        self.assertIn("HandleOpenReportClicked", source)
        self.assertIn("HasSelectedReport", source)
        self.assertEqual(source.count('"定位完整报告"'), 2)
        handler = source.split("FReply HandleOpenReportClicked()", 1)[1].split("FReply HandleExportDebugClicked()", 1)[0]
        self.assertIn("FPaths::ConvertRelativePathToFull", handler)
        self.assertIn("FPaths::FileExists(ReportFile)", handler)
        self.assertIn("FPlatformProcess::ExploreFolder(*ReportFile)", handler)
        self.assertNotIn("LaunchFileInDefaultExternalApplication", handler)

    def test_gate_history_clear_is_explicit_and_non_destructive(self):
        source = self.source

        self.assertIn("清空列表", source)
        self.assertIn("已清理当前 Gate 导入历史列表", source)
        self.assertIn("这不会删除磁盘 Package 或 UE 资产", source)
        self.assertNotIn("预览清理候选", source)
        self.assertNotIn("预览可清理历史", source)
        self.assertNotIn('TEXT("cleanup_asset_forge_generated_props"), TargetPackageDir', source)

    def test_gate_has_manual_package_root_and_clear_list_controls(self):
        source = self.source

        for text in [
            "DesktopPlatform",
            "选择包体目录",
            "只看已选目录",
            "扫描来源",
            "已选目录",
            "ManualPackageRoot",
            "bScanManualRootOnly",
            "HandleChoosePackageRootClicked",
            "HandleClearListClicked",
            "清空列表",
            "历史包体会保留",
            "bScanManualRootOnly = false",
            "这不会删除磁盘 Package 或 UE 资产",
        ]:
            self.assertIn(text, source)

    def test_gate_right_column_uses_import_first_product_order(self):
        source = self.source

        ordered_labels = [
            'LOCTEXT("CheckPackage", "检查包体")',
            'SNew(SButton).Tag(TEXT("Gate.Import"))',
            'BuildWriteConfirmation()]',
            'LOCTEXT("PackageContentSection", "包体摘要")',
            'LOCTEXT("ImportStrategySection", "导入策略设置")',
            'LOCTEXT("PackageSourceRecord", "来源记录")',
            'LOCTEXT("HistorySection", "历史与报告")',
        ]
        positions = [source.index(label) for label in ordered_labels]

        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("2 包体画像", source)
        self.assertNotIn("3 包内资产", source)
        self.assertNotIn("2 入审与导入", source)
        self.assertNotIn("5 入审与导入", source)
        self.assertNotIn("6 历史与报告", source)

    def test_gate_surfaces_package_version_and_project_preset(self):
        source = self.source

        for text in [
            "package_naming",
            "project_preset",
            "ManifestPackageName",
            "PackageVersionMode",
            "PackageVersionLabel",
            "ProjectPresetName",
            "ProjectPresetVersion",
            "包体/版本",
            "项目预设",
            "PackageIdentityLine",
            "ProjectPresetLine",
        ]:
            self.assertIn(text, source)

    def test_gate_exposes_timestamped_status_and_source_record(self):
        source = self.source

        for text in ["来源记录", "包体时间", "报告时间", "Manifest", "备注"]:
            self.assertIn(text, source)
        self.assertIn("AssetForge v0.2", source)
        self.assertIn("Gate.Fold.Policy", source)
        self.assertIn("PackageRiskColor", source)
        self.assertIn("ModifiedTimeLabel", source)
        self.assertIn("ReportTimeLabel", source)
        self.assertIn("GetToolVersionText", source)
        self.assertIn("GetLastRefreshText", source)
        self.assertIn("GetPackageNoteText", source)
        self.assertIn("FStyleColors::Warning", source)
        self.assertIn("FStyleColors::Error", source)
        self.assertIn("PackageCountsLabel", source)
        self.assertIn("放行 %d / 警告 %d / 阻断 %d / 待检查 %d", source)
        self.assertIn("FStyleColors::Success", source)
        self.assertIn("true", source[source.index("PackageSourceRecord"):source.index("HistorySection")])
        self.assertIn("FDateTime::UtcNow()", source)
        self.assertIn("LocalOffset", source)

    def test_gate_package_rows_use_selection_dots_not_expand_arrows(self):
        source = self.source

        self.assertIn("SelectionDot", source)
        self.assertIn("SelectionDot(const TAttribute<bool>& bSelected)", source)
        self.assertIn("PackageSelectedDot", source)
        self.assertIn("PackageUnselectedDot", source)
        self.assertIn("HandlePackageRowSelect", source)
        self.assertIn("选择包体；右侧会显示来源记录、包内资产和导入策略", source)
        self.assertNotIn("ExpandedPackageDir", source)
        self.assertNotIn("HandlePackageRowToggle", source)
        self.assertNotIn("ExpanderGlyph", source)
        self.assertNotIn("TreeArrow_Expanded", source)
        self.assertNotIn("TreeArrow_Collapsed", source)
        self.assertNotIn('TEXT("▼")', source)
        self.assertNotIn('TEXT("▶")', source)
        self.assertNotIn('TEXT("▾")', source)
        self.assertNotIn('TEXT("▸")', source)
        self.assertNotIn("▸ 详情", source)
        self.assertNotIn("▾ 收起", source)
        row_source = source[source.index("TSharedRef<ITableRow> MakePackageRow"):source.index("void OnPackageSelected")]
        self.assertIn("TAttribute<bool>::CreateLambda", row_source)
        self.assertIn("PackageListView->IsItemSelected(Item)", row_source)
        self.assertNotIn("const bool bSelected =", row_source)
        self.assertIn("StatusPill(", row_source)
        self.assertIn("SimpleButton", row_source)
        self.assertIn("ListCompactMetaLabel", source)
        self.assertIn("ListExpandedDetailsLabel", source)
        self.assertIn("已选择 %s。右侧已显示来源记录", source)
        self.assertIn("UE 路径：", source)
        self.assertIn("包体目录：", source)
        self.assertIn("报告时间：", source)
        self.assertIn("来源 DCC：", source)
        self.assertIn("导入许可：", source)
        self.assertIn("报告路径：", source)
        self.assertIn("PreviousPackageDir", source)
        self.assertIn("FindFilteredPackageByDir", source)
        self.assertIn("SelectedPackage = RestoredPackage.IsValid()", source)
        self.assertIn("PackageListView->ClearSelection()", source)
        self.assertIn("当前搜索结果不包含原选中包体", source)

    def test_gate_distinguishes_source_meshes_from_fbx_file_count(self):
        source = self.source

        self.assertIn("SourceMeshCount", source)
        self.assertIn("FbxFileCount", source)
        self.assertIn("MaterialSlotCount", source)
        self.assertIn("AttachExportCounts", source)
        self.assertIn("AttachImportOptions", source)
        self.assertIn("*export_report.json", source)
        self.assertIn("resolved_preset", source)
        self.assertIn("combine_meshes", source)
        self.assertIn("独立 Mesh %d / FBX 文件 %d", source)
        self.assertIn("GetCombineMeshesText", source)
        self.assertIn("GetNormalImportText", source)
        self.assertIn("GetLodPolicyText", source)
        self.assertIn("GetNanitePolicyText", source)
        self.assertIn("Combine Meshes 关闭，UE 按 FBX 源节点拆分导入", source)
        self.assertNotIn("Maya Mesh", source)
        self.assertNotIn("%d 个 FBX / 静态网格入口", source)

    def test_gate_can_export_debug_snapshot(self):
        source = self.source

        self.assertIn("HandleExportDebugClicked", source)
        self.assertIn("BuildDebugExportText", source)
        self.assertIn("GetDebugExportPathText", source)
        self.assertIn("AssetForge/GateDebug", source)
        self.assertIn("visible_packages: %d / %d", source)
        self.assertIn("package_counts: %s", source)
        self.assertIn("selected_package_dir: %s", source)
        self.assertIn("SaveStringToFile", source)
        self.assertIn("导出调试信息", source)
        self.assertIn("调试导出", source)

    def test_gate_button_copy_uses_actionable_import_language(self):
        source = self.source

        self.assertIn("前往「入库批审」查验本次资产 →", source)
        self.assertIn("定位完整报告", source)
        self.assertIn("非阻断提醒", source)
        self.assertIn('true, TEXT("Gate.Fold.Policy")', source)
        self.assertIn("不写入验证", source)
        self.assertIn("workbench_dry_run_package", source)
        self.assertIn("workbench_apply_package", source)
        self.assertNotIn("import_approved_package_dir", source)
        self.assertIn("EPythonCommandExecutionMode::ExecuteFile", source)
        self.assertNotIn("EPythonCommandExecutionMode::ExecuteStatement", source)
        self.assertIn("return FString::Printf(TEXT(\"exec(%s)\"), *PythonStringLiteral(Script));", source)
        preview_handler = source.split("FReply HandlePreviewClicked()", 1)[1].split("FReply HandleDryRunClicked()", 1)[0]
        import_handler = source.split("FReply HandleImportClicked()", 1)[1].split("FReply HandleConfirmWriteClicked()", 1)[0]
        dry_run_handler = source.split("FReply HandleDryRunClicked()", 1)[1].split("FReply HandleImportClicked()", 1)[0]
        self.assertIn("QueueGateOperation(EGateOperation::Check)", preview_handler)
        self.assertIn("QueueGateOperation(EGateOperation::PrepareWrite)", import_handler)
        self.assertNotIn("QueueGateOperation(EGateOperation::Import)", import_handler)
        self.assertIn("QueueGateOperation(EGateOperation::DryRun)", dry_run_handler)
        self.assertIn("CanImportSelectedPackage", source)
        tooltip = source.split("FText GetImportTooltipText() const", 1)[1].split("FText GetOpenReportTooltipText()", 1)[0]
        self.assertLess(tooltip.index("GateOperation != EGateOperation::Idle"), tooltip.index("!CanImportSelectedPackage()"))
        self.assertIn("return FText::GetEmpty();", tooltip)
        self.assertIn("请在包体摘要中处理阻断项，再重新检查。", tooltip)
        self.assertIn("当前包体未放行，未写入 UE", source)
        self.assertIn("GetWriteContentSummaryText", source)
        self.assertIn("写入内容", source)
        self.assertIn("只写入当前选中包体；Static Mesh 始终导入；%s；%s；UE FBX 自动材质/贴图导入保持关闭。", source)
        self.assertIn("基础导入", source)
        basic_import = source.split("TSharedRef<SWidget> BuildBasicImportSummaryRow()", 1)[1].split(
            "TSharedRef<SWidget> BuildContentImportOptionRow()", 1
        )[0]
        self.assertIn("导入静态网格", basic_import)
        self.assertIn(".AutoWrapText(true)", basic_import)
        self.assertIn("材质贴图", source)
        self.assertIn("创建材质实例", source)
        self.assertIn("导入贴图资产", source)
        self.assertIn("高级设置：变换 / 单位", source)
        self.assertIn("高级设置：构建输出", source)
        self.assertIn("CanImportSelectedPackage()", import_handler)
        self.assertNotIn("workbench_apply_package", preview_handler)
        self.assertIn("bool bGateImportMaterials = true;", source)
        self.assertIn("bool bGateImportTextures = true;", source)
        self.assertIn('Options->SetBoolField(TEXT("fbx_import_materials"), false);', source)
        self.assertIn('Options->SetBoolField(TEXT("fbx_import_textures"), false);', source)
        self.assertNotIn("Import Materials", source)
        self.assertNotIn("Import Textures", source)
        self.assertNotIn("IsGateImportTexturesChecked)).IsEnabled(false)", source)
        self.assertNotIn("IsGateImportMaterialsChecked)).IsEnabled(false)", source)
        self.assertNotIn("预检选中包体", source)
        self.assertNotIn("检查当前包体", source)
        self.assertNotIn("模拟导入（不写入）", source)
        self.assertNotIn("生成门禁报告", source)
        self.assertNotIn("门禁报告：", source)
        self.assertNotIn("复核导入预演（不写入）", source)
        self.assertNotIn("批准导入当前包体", source)
        self.assertNotIn("检查层", source)
        self.assertNotIn("预演层", source)
        self.assertNotIn("写入层", source)
        self.assertNotIn("默认选中 %s", source)
        self.assertIn("请在左侧明确选择一个包体", source)

    def test_gate_keeps_the_write_step_inline_and_updates_only_the_selected_report(self):
        source = self.source
        for value in ("Gate.ConfirmPanel", "Gate.ConfirmWrite", "Gate.CancelWrite", "Gate.Handoff",
                      "Gate.FullReport", "等待确认…", "正在导入资产…", "确认写入", "operator_warnings", "operator_errors",
                      "policy_summary", "existing_count", "warning_count", "report_path"):
            self.assertIn(value, source)
        confirm = source.split("FReply HandleConfirmWriteClicked()", 1)[1].split("FReply HandleCancelWriteClicked()", 1)[0]
        cancel = source.split("FReply HandleCancelWriteClicked()", 1)[1].split("FReply QueueGateOperation", 1)[0]
        queue = source.split("FReply QueueGateOperation", 1)[1].split("FReply HandleOpenReportClicked()", 1)[0]
        self.assertIn("QueueGateOperation(EGateOperation::Import)", confirm)
        self.assertIn("GateOperation != EGateOperation::AwaitConfirm", confirm)
        self.assertNotIn("QueueGateOperation", cancel)
        self.assertIn("bImport ? ConfirmedOptions : BuildGateImportOptionsJson()", queue)
        self.assertIn("import_succeeded", queue)
        self.assertIn("RefreshSelectedPackageReport(PackageDir, Result)", queue)
        self.assertNotIn("RefreshPackages()", queue)
        self.assertLess(queue.index("GateMessage = bImport"), queue.index("RegisterActiveTimer"))
        self.assertLess(queue.index("RegisterActiveTimer"), queue.index("ExecuteGatePythonCommand"))
        self.assertIn("AssetForgeGateTiming action=%s", queue)

    def test_gate_uses_the_backend_notice_projection_for_the_selected_report(self):
        source = self.source
        report = source.split("static void AttachReportDecision", 1)[1].split("static FString ReportImportPermissionText", 1)[0]
        discovery = source.split("void RefreshPackages()", 1)[1].split("TSharedPtr<FAssetForgePackageItem> FindFilteredPackageByDir", 1)[0]
        selection = source.split("void OnPackageSelected(", 1)[1].split("FReply HandleRefreshClicked()", 1)[0]
        self.assertIn("AttachOperatorNotices(Item, Report)", report)
        self.assertNotIn('TEXT("messages")', report)
        self.assertIn('TEXT("workbench_read_reports")', source)
        self.assertIn("_af_kwargs['report_path'] = _af_report_path", source)
        self.assertIn("LoadSelectedReportDetails()", selection)
        self.assertNotIn("ExecuteGatePythonCommand", discovery)

    def test_completed_receipt_reuses_write_position_and_opens_recorded_static_meshes(self):
        source = self.source
        column = source.split("TSharedRef<SWidget> BuildReviewColumn()", 1)[1].split("BuildGateNotices()", 1)[0]
        self.assertLess(column.index("BuildWriteConfirmation()"), column.index("BuildCompletedImport()"))
        self.assertLess(column.index("BuildCompletedImport()"), column.index("包体摘要"))
        completion = source.split("TSharedRef<SWidget> BuildCompletedImport()", 1)[1].split("GetGateNotices(", 1)[0]
        self.assertIn("✓ 导入完成", completion)
        self.assertIn("HandleImportedReviewClicked", completion)
        self.assertIn("打开静态网格", completion)
        self.assertIn("SWrapBox", completion)
        handler = source.split("FReply HandleOpenImportedMeshClicked()", 1)[1].split("FReply HandleOpenReportClicked()", 1)[0]
        self.assertIn("LoadSelectedReportDetails(true)", handler)
        self.assertIn("OpenEditorForAssets(Assets)", handler)
        self.assertIn("Paths != OriginalPaths", handler)
        self.assertNotIn("QueueGateOperation", handler)

    def test_review_uses_a_focused_native_content_browser_and_visible_effective_budget(self):
        review = REVIEW_SOURCE.read_text(encoding="utf-8")
        self.assertIn("在内容浏览器定位", review)
        header = review.split("TSharedRef<SWidget> AssetHeader(", 1)[1].split("FReply LocateInContentBrowser(", 1)[0]
        self.assertIn("Review.LocateSelected", header)
        self.assertIn("return LocateInContentBrowser(Path)", header)
        self.assertIn("auto Actions = SNew(SWrapBox)", header)
        self.assertIn("GetAssetByObjectPath", review)
        self.assertIn("SyncBrowserToAssets(TArray<FAssetData>{Asset}, false, true)", review)
        self.assertIn("已在内容浏览器定位", review)
        locate = review.split("FReply LocateInContentBrowser(", 1)[1].split("TSharedRef<SWidget> IssueList(", 1)[0]
        self.assertIn("FSlateNotificationManager::Get().AddNotification(Notice)", locate)
        self.assertIn("Notice.ExpireDuration = 3.0f", locate)
        for name in ("budget_summary", "budget_source", "rules_triangles", "rules_material_slots"):
            self.assertIn(name, review)
        current = review.split("void AddBatchBudgetFields(", 1)[1].split("TOptional<int32> StockBudgetValue(", 1)[0]
        for value in ("batch_budget", "本批次预算", "应用并复验本批次", "Review.BatchBudget.Triangles",
                      "Review.BatchBudget.MaterialSlots", "rules_batch_budget"):
            self.assertIn(value, current)
        self.assertEqual(current.count('Run(TEXT("rules_batch_budget"), Budgets)'), 1)

    def test_gate_uses_the_durable_project_receipt_for_imported_review(self):
        source = self.source
        queue = source.split("FReply QueueGateOperation", 1)[1].split("void RefreshSelectedPackageReport", 1)[0]
        handoff = source.split("bool CanReviewSelectedImport() const", 1)[1].split("FReply HandleOpenReportClicked()", 1)[0]
        self.assertIn("handoff_receipt", source)
        self.assertIn('ExecuteGatePythonCommand(TEXT("workbench_read_reports"), Item.PackageDir', source)
        self.assertIn("AttachHandoffReceipt(*SelectedPackage, Result)", source)
        self.assertIn("CanImportSelectedPackage()", handoff)
        self.assertIn("LoadSelectedReportDetails(true)", handoff)
        self.assertIn("AssetForgeReview::OpenImported", handoff)
        self.assertNotIn("FGuid::NewGuid()", queue)
        self.assertNotIn("ImportReceipts.Contains", source)

    def test_gate_transform_units_and_offsets_use_full_width_wrapping(self):
        source = self.source
        for control in ("BuildTransformOptionRow", "BuildTransformOffsetOptionRow"):
            section = source.split("TSharedRef<SWidget> " + control + "()", 1)[1].split("TSharedRef<SWidget> ", 1)[0]
            self.assertIn("SNew(SWrapBox)", section)
            self.assertIn("UseAllottedSize(true)", section)
        self.assertIn('FullWidthPolicyRow(LOCTEXT("GateTransformGroup"', source)
        self.assertIn('FullWidthPolicyRow(LOCTEXT("GateTransformOffsetGroup"', source)
        self.assertIn("顶点转绝对坐标", source)
        self.assertIn("旋转 P/Y/R", source)

    def test_gate_passes_import_options_to_python(self):
        source = self.source

        self.assertIn("SComboBox<TSharedPtr<FString>>", source)
        self.assertIn("BuildContentImportOptionRow", source)
        self.assertIn("BuildTransformOptionRow", source)
        self.assertIn("BuildTransformOffsetOptionRow", source)
        self.assertIn("BuildTransformNumberEntry", source)
        self.assertIn("BuildNormalImportCombo", source)
        self.assertIn("BuildNormalOptionRow", source)
        self.assertIn("BuildNormalGenerationCombo", source)
        self.assertIn("BuildImportUniformScaleWidget", source)
        self.assertIn("BuildVertexOverrideColorRow", source)
        self.assertIn("GetVertexOverrideColorVisibility", source)
        self.assertIn("GetNormalGenerationTooltipText", source)
        self.assertIn("先选择包体，再设置法线生成方式。", source)
        self.assertIn("UE 会忽略法线生成器", source)
        self.assertIn("SNumericEntryBox<float>", source)
        self.assertIn("BuildLodGroupCombo", source)
        self.assertIn("BuildVertexColorCombo", source)
        self.assertIn("OnNormalImportSelectionChanged", source)
        self.assertIn("OnNormalGenerationSelectionChanged", source)
        self.assertIn("OnLodGroupSelectionChanged", source)
        self.assertIn("OnVertexColorSelectionChanged", source)
        self.assertIn("BuildMeshBuildOptionRow", source)
        self.assertIn("BuildMeshQualityOptionRow", source)
        self.assertIn("BuildOutputBuildOptionRow", source)
        self.assertIn("BuildBasicImportSummaryRow", source)
        self.assertIn("BuildGateImportOptionsJson", source)
        self.assertIn("EffectiveImportOptionsObject", source)
        self.assertIn("fbx_import_options_report", source)
        self.assertIn("import_options=_asset_forge_import_options", source)
        self.assertIn("combine_meshes", source)
        self.assertIn("import_materials", source)
        self.assertIn("import_textures", source)
        self.assertIn("import_mesh_lods", source)
        self.assertIn("auto_generate_collision", source)
        self.assertIn("one_convex_hull_per_ucx", source)
        self.assertIn("remove_degenerates", source)
        self.assertIn("compute_weighted_normals", source)
        self.assertIn("generate_lightmap_uvs", source)
        self.assertIn("build_reversed_index_buffer", source)
        self.assertIn("convert_scene", source)
        self.assertIn("force_front_x_axis", source)
        self.assertIn("convert_scene_unit", source)
        self.assertIn("transform_vertex_to_absolute", source)
        self.assertIn("bake_pivot_in_vertex", source)
        self.assertIn("import_translation", source)
        self.assertIn("import_rotation", source)
        self.assertIn("import_uniform_scale", source)
        self.assertIn("IsGateForceFrontXAxisChecked", source)
        self.assertIn("OnGateForceFrontXAxisChanged", source)
        self.assertIn("normal_import_method", source)
        self.assertIn("normal_generation_method", source)
        self.assertIn("static_mesh_lod_group", source)
        self.assertIn("vertex_color_import_option", source)
        self.assertIn("vertex_override_color", source)
        self.assertIn("GateVertexColorImportOption == TEXT(\"override\")", source)
        self.assertIn("return IsVertexOverrideColorEnabled() ? EVisibility::Visible : EVisibility::Collapsed", source)
        self.assertIn("SetArrayField(TEXT(\"vertex_override_color\")", source)
        self.assertIn("OnGateBakePivotInVertexChanged", source)
        self.assertIn("bGateTransformVertexToAbsolute = false", source)

    def test_plugin_material_comment_repair_restores_visible_chinese_blocks(self):
        source = COMMENT_SOURCE.read_text(encoding="utf-8")

        self.assertIn("const TCHAR* Text;", source)
        self.assertIn("Comment->Text = Spec.Text;", source)
        self.assertIn("Comment->Desc = Spec.Text;", source)
        self.assertIn("GraphComment->NodeComment = Spec.Text;", source)
        self.assertIn("GraphComment->NodeWidth = Spec.Size.X;", source)
        self.assertIn("GraphComment->NodeHeight = Spec.Size.Y;", source)
        for text in ["BaseColor", "Normal", "ARM / ORM", "Imperfection", "Emissive", "Opacity / Mask"]:
            self.assertIn(text, source)


if __name__ == "__main__":
    unittest.main()
