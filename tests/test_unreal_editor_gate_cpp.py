from __future__ import absolute_import

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
GATE_SOURCE = REPO_ROOT / "Plugins" / "AssetForge" / "Source" / "AssetForgeEditor" / "Private" / "AssetForgeEditorModule.cpp"
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
        self.assertIn("Asset Forge 导入门禁", source)

    def test_gate_uses_semantic_editor_controls(self):
        source = self.source

        for control in ["SSearchBox", "SListView", "SCheckBox", "SExpandableArea"]:
            self.assertIn(control, source)
        for section in ["包体来源", "导入策略", "入审与导入", "历史与报告"]:
            self.assertIn(section, source)

    def test_gate_report_path_has_open_action(self):
        source = self.source

        self.assertIn("GetReportPath", source)
        self.assertIn("HandleOpenReportClicked", source)
        self.assertIn("HasSelectedReport", source)
        self.assertIn("打开报告", source)
        self.assertIn("LaunchFileInDefaultExternalApplication", source)

    def test_gate_exposes_timestamped_status_and_source_record(self):
        source = self.source

        for text in ["来源记录", "包体时间", "报告时间", "Manifest", "备注"]:
            self.assertIn(text, source)
        self.assertIn("Asset Forge Gate v0.1.5", source)
        self.assertIn("Build 2026-06-03-R7", source)
        self.assertIn("PackageRiskColor", source)
        self.assertIn("ModifiedTimeLabel", source)
        self.assertIn("ReportTimeLabel", source)
        self.assertIn("GetToolVersionText", source)
        self.assertIn("GetLastRefreshText", source)
        self.assertIn("GetPackageNoteText", source)
        self.assertIn("GetHeaderStatusColor", source)
        self.assertIn("StatusPillDynamic", source)
        self.assertIn("PackageCountsLabel", source)
        self.assertIn("放行 %d / 警告 %d / 阻断 %d / 待预检 %d", source)
        self.assertIn("FLinearColor(0.55f, 0.65f, 0.72f, 1.0f)", source)
        self.assertIn("true", source[source.index("PackageSourceRecord"):source.index("PackageDetail")])

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

        self.assertIn("生成入审报告", source)
        self.assertIn("预演导入计划（不写入）", source)
        self.assertIn("dry_run_gate_for_package_dir", source)
        self.assertIn("EPythonCommandExecutionMode::ExecuteFile", source)
        self.assertNotIn("EPythonCommandExecutionMode::ExecuteStatement", source)
        self.assertIn("return FString::Printf(TEXT(\"exec(%s)\"), *PythonStringLiteral(Script));", source)
        preview_handler = source[source.index("FReply HandlePreviewClicked") : source.index("FReply HandleDryRunClicked")]
        dry_run_handler = source[source.index("FReply HandleDryRunClicked") : source.index("FReply HandleImportClicked")]
        self.assertIn('ExecuteGatePythonCommand(TEXT("preview_gate_for_package_dir"), SelectedPackage->PackageDir, BuildGateImportOptionsJson())', preview_handler)
        self.assertIn('ExecuteGatePythonCommand(TEXT("dry_run_gate_for_package_dir"), SelectedPackage->PackageDir, BuildGateImportOptionsJson())', dry_run_handler)
        self.assertIn("正式导入选中包体", source)
        self.assertIn("CanImportSelectedPackage", source)
        self.assertIn("当前报告未放行或仍有错误，正式导入已禁用。", source)
        self.assertIn("当前包体未被报告放行，无法正式导入", source)
        self.assertIn("GetWriteContentSummaryText", source)
        self.assertIn("写入内容", source)
        self.assertIn("检查层只生成入审报告；预演层按当前设置生成 dry-run 计划但不写资产；写入层只导入当前选中包体。", source)
        self.assertIn("正式导入只写入当前选中包体；Static Mesh 始终导入；%s；%s；UE FBX 自动材质/贴图导入保持关闭。", source)
        self.assertIn("基础导入", source)
        self.assertIn("默认导入 Static Mesh", source)
        self.assertIn("材质贴图", source)
        self.assertIn("创建材质实例", source)
        self.assertIn("导入贴图资产", source)
        self.assertIn("高级设置：变换 / 单位", source)
        self.assertIn("高级设置：构建输出", source)
        self.assertIn("5 入审与导入", source)
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
        self.assertNotIn("默认选中 %s", source)
        self.assertIn("请在左侧明确选择一个包体", source)

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
