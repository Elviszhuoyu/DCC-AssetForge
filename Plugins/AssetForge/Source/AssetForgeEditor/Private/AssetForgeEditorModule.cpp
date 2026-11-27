#include "AssetForgeEditorModule.h"
#include "SAssetForgeReview.h"

#include "Widgets/Input/SComboButton.h"

#include "Brushes/SlateImageBrush.h"
#include "DesktopPlatformModule.h"
#include "Editor.h"
#include "Engine/StaticMesh.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Framework/Docking/TabManager.h"
#include "HAL/FileManager.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformMisc.h"
#include "HAL/PlatformProcess.h"
#include "HAL/PlatformTime.h"
#include "Interfaces/IPluginManager.h"
#include "IDesktopPlatform.h"
#include "IPythonScriptPlugin.h"
#include "Misc/EngineVersion.h"
#include "Misc/FileHelper.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#endif
#include "Misc/PackageName.h"
#include "Misc/Paths.h"
#include "Policies/CondensedJsonPrintPolicy.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "Styling/AppStyle.h"
#include "Styling/SlateStyle.h"
#include "Styling/SlateStyleRegistry.h"
#include "Subsystems/AssetEditorSubsystem.h"
#include "UObject/SoftObjectPath.h"
#include "ToolMenus.h"
#include "Widgets/Docking/SDockTab.h"
#include "Widgets/Images/SImage.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Input/SCheckBox.h"
#include "Widgets/Input/SComboBox.h"
#include "Widgets/Input/SNumericEntryBox.h"
#include "Widgets/Input/SSearchBox.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SExpandableArea.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/Layout/SSeparator.h"
#include "Widgets/Layout/SSplitter.h"
#include "Widgets/Layout/SWidgetSwitcher.h"
#include "Widgets/Layout/SWrapBox.h"
#include "Styling/StyleColors.h"
#include "Widgets/SCompoundWidget.h"
#include "Widgets/Text/STextBlock.h"
#include "Widgets/Views/SListView.h"

#define LOCTEXT_NAMESPACE "AssetForgeEditor"

DEFINE_LOG_CATEGORY_STATIC(LogAssetForgeEditor, Log, All);

namespace AssetForgeEditor
{
static const FName GateTabName(TEXT("AssetForge.GateWorkbench"));
static const FName StyleSetName(TEXT("AssetForgeEditorStyle"));
static const FName WorkbenchIconName(TEXT("AssetForge.ReviewTabIcon"));
static const TCHAR* GateVersionLabel = TEXT("AssetForge v0.2");
static const TCHAR* ImportedSelectionMessage = TEXT("该包体已导入，可直接前往「入库批审」查验本次资产");
static const TCHAR* DccPackageRootName = TEXT("dcc_packages");

struct FAssetForgePackageItem
{
    FString AssetName;
    FString SourceDcc;
    FString MaterialBindings;
    FString TargetPath;
    FString SchemaVersion;
    FString ManifestPackageName;
    FString PackageVersionMode;
    FString PackageVersionLabel;
    FString ProjectPresetName;
    FString ProjectPresetVersion;
    FString PackageDir;
    FString ManifestPath;
    FString ImportReportPath;
    FString LastImportStatus;
    FString ReportDecision;
    FString ReportDecisionLabel;
    FString ReportNextAction;
    FString ReportRiskCaption;
    TArray<FString> OperatorWarnings;
    TArray<FString> OperatorErrors;
    TSharedPtr<FJsonObject> HandoffReceipt;
    bool bReportViewLoaded = false;
    bool bImported = false;
    bool bReportCanImportKnown = false;
    bool bReportCanImport = false;
    int32 ReportWarningCount = 0;
    int32 ReportErrorCount = 0;
    int32 MeshCount = 0;
    int32 TriangleBudget = INDEX_NONE;
    int32 MaterialSlotBudget = INDEX_NONE;
    int32 SourceMeshCount = 0;
    int32 FbxFileCount = 0;
    int32 TextureCount = 0;
    int32 MaterialCount = 0;
    int32 MaterialSlotCount = 0;
    bool bCombineMeshesKnown = false;
    bool bCombineMeshes = false;
    FString NormalImportMethod;
    FString StaticMeshLodPolicy;
    FString NanitePolicy;
    FDateTime ModifiedTime = FDateTime::MinValue();
    FDateTime ReportTime = FDateTime::MinValue();

    bool HasReport() const
    {
        return !ImportReportPath.IsEmpty();
    }

    FString StatePrefix() const
    {
        if ((bReportCanImportKnown && !bReportCanImport) || ReportErrorCount > 0)
        {
            return TEXT("[阻断]");
        }
        if (bImported)
        {
            return TEXT("[已导入]");
        }
        if (!HasReport())
        {
            return TEXT("[待检查]");
        }
        if (bReportCanImportKnown)
        {
            return ReportWarningCount > 0 ? TEXT("[可导入 · 需复核]") : TEXT("[可导入]");
        }
        return TEXT("[需复核]");
    }

    FString RiskSummary() const
    {
        if (!HasReport())
        {
            return TEXT("风险：等待检查报告");
        }
        if (!ReportRiskCaption.IsEmpty())
        {
            return ReportRiskCaption;
        }
        return FString::Printf(TEXT("风险：警告 %d / 阻断 %d"), ReportWarningCount, ReportErrorCount);
    }

    FString ListPrimaryLabel() const
    {
        const FString DccLabel = SourceDcc.IsEmpty() ? TEXT("DCC 未记录") : SourceDcc.ToUpper();
        return FString::Printf(TEXT("%s %s    %s"), *StatePrefix(), *AssetName, *DccLabel);
    }

    FString ListSecondaryLabel() const
    {
        const FString TargetLabel = TargetPath.IsEmpty() ? TEXT("UE 路径未记录") : TargetPath;
        return FString::Printf(TEXT("%s    更新 %s    独立 Mesh %d / FBX %d / 贴图 %d / 材质 %d    %s"), *TargetLabel, *ModifiedTimeLabel(), SourceMeshDisplayCount(), FbxDisplayCount(), TextureCount, MaterialCount, *RiskSummary());
    }

    FString ListCompactMetaLabel() const
    {
        const FString DccLabel = SourceDcc.IsEmpty() ? TEXT("DCC 未记录") : SourceDcc.ToUpper();
        const FString TargetLabel = TargetPath.IsEmpty() ? TEXT("UE 路径未记录") : TargetPath;
        return FString::Printf(TEXT("%s  ·  %s"), *DccLabel, *TargetLabel);
    }

    FString ListExpandedDetailsLabel() const
    {
        return FString::Printf(
            TEXT("来源记录\n来源 DCC：%s\nUE 路径：%s\n%s\n%s\n包体目录：%s\nManifest：%s\n包体时间：%s\n报告时间：%s\n导入许可：%s\n资源：独立 Mesh %d / FBX %d / 贴图 %d / 材质计划 %d / Schema %s\n导入策略：%s\n报告路径：%s"),
            SourceDcc.IsEmpty() ? TEXT("未记录") : *SourceDcc,
            TargetPath.IsEmpty() ? TEXT("未记录") : *TargetPath,
            *PackageIdentityLine(),
            *ProjectPresetLine(),
            *PackageDir,
            *ManifestPath,
            *ModifiedTimeLabel(),
            *ReportTimeLabel(),
            *ImportPermissionLine(),
            SourceMeshDisplayCount(),
            FbxDisplayCount(),
            TextureCount,
            MaterialCount,
            SchemaVersion.IsEmpty() ? TEXT("未记录") : *SchemaVersion,
            *ImportStrategyLine(),
            ImportReportPath.IsEmpty() ? TEXT("暂无报告") : *ImportReportPath
        );
    }

    FString PackageIdentityLine() const
    {
        const FString PackageLabel = ManifestPackageName.IsEmpty() ? FPaths::GetCleanFilename(PackageDir) : ManifestPackageName;
        const FString ModeLabel = PackageVersionMode.IsEmpty() ? TEXT("overwrite") : PackageVersionMode;
        const FString VersionSuffix = PackageVersionLabel.IsEmpty() ? FString() : FString::Printf(TEXT("；版本：%s"), *PackageVersionLabel);
        return FString::Printf(TEXT("包体/文件夹：%s；版本策略：%s%s"), *PackageLabel, *ModeLabel, *VersionSuffix);
    }

    FString ProjectPresetLine() const
    {
        if (ProjectPresetName.IsEmpty() && ProjectPresetVersion.IsEmpty())
        {
            return TEXT("项目预设：未记录");
        }
        return FString::Printf(TEXT("项目预设：%s v%s"),
            ProjectPresetName.IsEmpty() ? TEXT("未命名") : *ProjectPresetName,
            ProjectPresetVersion.IsEmpty() ? TEXT("-") : *ProjectPresetVersion);
    }

    FString ModifiedTimeLabel() const
    {
        return TimeLabel(ModifiedTime);
    }

    FString ReportTimeLabel() const
    {
        return TimeLabel(ReportTime);
    }

    FString OperatorNote() const
    {
        if (!HasReport())
        {
            return TEXT("备注：暂无报告；先生成检查报告，再决定是否导入。");
        }
        return FString::Printf(TEXT("备注：%s；%s；下一步 %s"),
            *ReportDecisionLineSafe(),
            *RiskSummary(),
            ReportNextAction.IsEmpty() ? TEXT("按门禁状态继续") : *ReportNextAction);
    }

    FString ReportDecisionLineSafe() const
    {
        return ReportDecisionLabel.IsEmpty() ? LastImportStatus : ReportDecisionLabel;
    }

    FString ImportPermissionLine() const
    {
        if (!bReportCanImportKnown)
        {
            return TEXT("导入许可未记录");
        }
        return bReportCanImport ? TEXT("报告允许导入") : TEXT("报告不允许导入");
    }

    int32 SourceMeshDisplayCount() const
    {
        return SourceMeshCount > 0 ? SourceMeshCount : MeshCount;
    }

    int32 FbxDisplayCount() const
    {
        return FbxFileCount > 0 ? FbxFileCount : (MeshCount > 0 ? 1 : 0);
    }

    FString MeshSummaryLine() const
    {
        return FString::Printf(TEXT("独立 Mesh %d / FBX 文件 %d"), SourceMeshDisplayCount(), FbxDisplayCount());
    }

    FString MaterialSummaryLine() const
    {
        if (MaterialSlotCount > 0)
        {
            return FString::Printf(TEXT("%d 个材质实例计划 / %d 个材质槽"), MaterialCount, MaterialSlotCount);
        }
        return FString::Printf(TEXT("%d 个材质实例计划"), MaterialCount);
    }

    FString ImportStrategyLine() const
    {
        TArray<FString> Details;
        if (!NormalImportMethod.IsEmpty())
        {
            Details.Add(FString::Printf(TEXT("法线 %s"), *NormalImportMethod));
        }
        if (!StaticMeshLodPolicy.IsEmpty())
        {
            Details.Add(FString::Printf(TEXT("LOD %s"), *StaticMeshLodPolicy));
        }
        if (!NanitePolicy.IsEmpty())
        {
            Details.Add(NanitePolicy);
        }
        const FString DetailText = Details.Num() > 0 ? FString::Printf(TEXT("；%s"), *FString::Join(Details, TEXT(" / "))) : FString();
        if (!bCombineMeshesKnown)
        {
            return FString::Printf(TEXT("Combine Meshes 未记录，真实 Static Mesh 数需等 UE 导入前确认%s"), *DetailText);
        }
        const FString Base = bCombineMeshes
            ? TEXT("Combine Meshes 开启，UE 会把多个 FBX 节点合并为 1 个 Static Mesh")
            : TEXT("Combine Meshes 关闭，UE 按 FBX 源节点拆分导入");
        return Base + DetailText;
    }

    static FString TimeLabel(const FDateTime& Time)
    {
        if (Time == FDateTime::MinValue())
        {
            return TEXT("未记录");
        }
        const FTimespan LocalOffset = FDateTime::Now() - FDateTime::UtcNow();
        return (Time + LocalOffset).ToString(TEXT("%Y-%m-%d %H:%M"));
    }
};

static FSlateFontInfo DetailFont()
{
    return FAppStyle::GetFontStyle("PropertyWindow.NormalFont");
}

static FSlateFontInfo StrongFont()
{
    return FAppStyle::GetFontStyle("DetailsView.CategoryFontStyle");
}

static TSharedRef<STextBlock> TextBlock(const TAttribute<FText>& Text, const FSlateColor& Color = FSlateColor::UseForeground())
{
    return SNew(STextBlock)
        .Text(Text)
        .Font(DetailFont())
        .ColorAndOpacity(Color);
}

static TSharedRef<STextBlock> WrappedTextBlock(const TAttribute<FText>& Text, const TAttribute<FText>& ToolTipText = TAttribute<FText>())
{
    return SNew(STextBlock)
        .Text(Text)
        .Font(DetailFont())
        .AutoWrapText(true)
        .ToolTipText(ToolTipText);
}

static TSharedRef<SWidget> PropertyRow(const FText& Label, const TAttribute<FText>& Value)
{
    return SNew(SBorder)
        .BorderImage(FAppStyle::GetBrush("DetailsView.GridLine"))
        .Padding(FMargin(8.0f, 5.0f))
        [
            SNew(SHorizontalBox)
            + SHorizontalBox::Slot()
            .FillWidth(0.32f)
            [
                TextBlock(Label, FSlateColor::UseSubduedForeground())
            ]
            + SHorizontalBox::Slot()
            .FillWidth(0.68f)
            [
                WrappedTextBlock(Value, Value)
            ]
        ];
}

static TSharedRef<SWidget> PropertyRow(const FText& Label, const TSharedRef<SWidget>& ValueWidget)
{
    return SNew(SBorder)
        .BorderImage(FAppStyle::GetBrush("DetailsView.GridLine"))
        .Padding(FMargin(8.0f, 5.0f))
        [
            SNew(SHorizontalBox)
            + SHorizontalBox::Slot()
            .FillWidth(0.32f)
            [
                TextBlock(Label, FSlateColor::UseSubduedForeground())
            ]
            + SHorizontalBox::Slot()
            .FillWidth(0.68f)
            [
                ValueWidget
            ]
        ];
}

static TSharedRef<SWidget> StatusPill(const TAttribute<FText>& Text, const FSlateColor& Color)
{
    return SNew(SBorder)
        .BorderImage(FAppStyle::GetBrush("ToolPanel.DarkGroupBorder"))
        .Padding(FMargin(10.0f, 4.0f))
        [
            TextBlock(Text, Color)
        ];
}

static TSharedRef<SWidget> SelectionDot(const TAttribute<bool>& bSelected)
{
    return SNew(SBorder)
        .BorderImage(FAppStyle::GetBrush("NoBorder"))
        .Padding(FMargin(0.0f, 0.0f, 4.0f, 0.0f))
        [
            SNew(STextBlock)
            .Text(TAttribute<FText>::CreateLambda([bSelected]()
            {
                return bSelected.Get()
                    ? LOCTEXT("PackageSelectedDot", "●")
                    : LOCTEXT("PackageUnselectedDot", "○");
            }))
            .Font(DetailFont())
            .ColorAndOpacity(TAttribute<FSlateColor>::CreateLambda([bSelected]()
            {
                return bSelected.Get()
                    ? FStyleColors::Foreground
                    : FSlateColor::UseSubduedForeground();
            }))
        ];
}

static FSlateColor PackageRiskColor(const FAssetForgePackageItem& Item)
{
    if (!Item.HasReport())
    {
        return FSlateColor::UseSubduedForeground();
    }
    if ((Item.bReportCanImportKnown && !Item.bReportCanImport) || Item.ReportErrorCount > 0)
    {
        return FStyleColors::Error;
    }
    if (!Item.bImported && (Item.ReportWarningCount > 0 || !Item.bReportCanImportKnown))
    {
        return FStyleColors::Warning;
    }
    return FStyleColors::Success;
}

static TSharedRef<SWidget> CompactButton(
    const TAttribute<FText>& Text,
    const FName IconName,
    FOnClicked OnClicked = FOnClicked(),
    const TAttribute<bool>& IsEnabled = TAttribute<bool>(true),
    const TAttribute<FText>& ToolTipText = TAttribute<FText>(FText::GetEmpty())
)
{
    return SNew(SButton)
        .ContentPadding(FMargin(10.0f, 5.0f))
        .OnClicked(OnClicked)
        .IsEnabled(IsEnabled)
        .ToolTipText(ToolTipText)
        [
            SNew(SHorizontalBox)
            + SHorizontalBox::Slot()
            .AutoWidth()
            .VAlign(VAlign_Center)
            [
                SNew(SImage)
                .Image(FAppStyle::GetBrush(IconName))
            ]
            + SHorizontalBox::Slot()
            .AutoWidth()
            .VAlign(VAlign_Center)
            .Padding(6.0f, 0.0f, 0.0f, 0.0f)
            [
                TextBlock(Text)
            ]
        ];
}

static TSharedRef<SWidget> CompactButton(const FText& Text, const FName IconName, FOnClicked OnClicked = FOnClicked())
{
    return CompactButton(TAttribute<FText>(Text), IconName, OnClicked);
}

static FString PythonStringLiteral(FString Value)
{
    Value.ReplaceInline(TEXT("\\"), TEXT("\\\\"));
    Value.ReplaceInline(TEXT("'"), TEXT("\\'"));
    Value.ReplaceInline(TEXT("\r"), TEXT("\\r"));
    Value.ReplaceInline(TEXT("\n"), TEXT("\\n"));
    return FString::Printf(TEXT("'%s'"), *Value);
}

static FString BuildWorkbenchPythonCommand(const FString& ActionScript)
{
    FString PluginPythonRoot;
    if (const TSharedPtr<IPlugin> Plugin = IPluginManager::Get().FindPlugin(TEXT("AssetForge")))
    {
        PluginPythonRoot = FPaths::ConvertRelativePathToFull(FPaths::Combine(Plugin->GetBaseDir(), TEXT("Content"), TEXT("Python")));
    }
    const FString Script = FString::Printf(
        TEXT("import os, sys, json\n")
        TEXT("_af_roots = [%s, os.environ.get('ASSET_FORGE_SOURCE_ROOT', ''), os.environ.get('ASSET_FORGE_REPO_ROOT', '')]\n")
        TEXT("try:\n")
        TEXT("    _af_meta = os.path.join(%s, 'config', 'asset_forge_install.json')\n")
        TEXT("    if os.path.exists(_af_meta):\n")
        TEXT("        with open(_af_meta, 'r', encoding='utf-8-sig') as _af_stream:\n")
        TEXT("            _af_data = json.load(_af_stream)\n")
        TEXT("        _af_roots.extend([_af_data.get('source_repo_root', ''), os.path.dirname(os.path.dirname(_af_data.get('source_latest_maya_log', '')))])\n")
        TEXT("except Exception:\n")
        TEXT("    pass\n")
        TEXT("for p in _af_roots:\n")
        TEXT("    if p and os.path.isdir(os.path.join(p, 'asset_forge')) and p not in sys.path:\n")
        TEXT("        sys.path.insert(0, p)\n")
        TEXT("%s\n")
        TEXT("print('ASSET_FORGE_GATE_RESULT=' + json.dumps(_af_result, ensure_ascii=True))\n"),
        *PythonStringLiteral(PluginPythonRoot),
        *PythonStringLiteral(PluginPythonRoot),
        *ActionScript
    );
    return FString::Printf(TEXT("exec(%s)"), *PythonStringLiteral(Script));
}

static FString BuildGatePythonAction(const FString& FunctionName, const FString& PackageDir,
    const FString& ImportOptionsJson, const FString& ConfirmationToken, const FString& ReportPath)
{
    return FString::Printf(
        TEXT("from asset_forge.unreal.editor_menu import %s as _asset_forge_gate_action\n")
        TEXT("_asset_forge_import_options = json.loads(%s)\n")
        TEXT("_af_token = %s\n")
        TEXT("_af_kwargs = {'confirmation_token': _af_token} if _af_token else {}\n")
        TEXT("_af_report_path = %s\n")
        TEXT("if _af_report_path:\n")
        TEXT("    _af_kwargs['report_path'] = _af_report_path\n")
        TEXT("_asset_forge_report = _asset_forge_gate_action(%s, import_options=_asset_forge_import_options, **_af_kwargs)\n")
        TEXT("_af_fields = ('status', 'message', 'report_path', 'gate_passed', 'can_import', 'operator_warnings', 'operator_errors', 'timings_ms', 'cache_hit', 'confirmation', 'import_succeeded', 'handoff_receipt')\n")
        TEXT("_af_result = {key: _asset_forge_report[key] for key in _af_fields if key in _asset_forge_report}"),

        *FunctionName,
        *PythonStringLiteral(ImportOptionsJson),
        *PythonStringLiteral(ConfirmationToken),
        *PythonStringLiteral(ReportPath),
        *PythonStringLiteral(PackageDir)
    );
}

static TSharedPtr<FJsonObject> ExecuteWorkbenchPythonCommand(const FString& ActionScript, FString& OutError)
{
    IPythonScriptPlugin* PythonPlugin = IPythonScriptPlugin::Get();
    if (!PythonPlugin || !PythonPlugin->IsPythonAvailable())
    {
        OutError = TEXT("UE Python 不可用，无法执行门禁动作。");
        return nullptr;
    }

    FPythonCommandEx PythonCommand;
    PythonCommand.Command = BuildWorkbenchPythonCommand(ActionScript);
    PythonCommand.ExecutionMode = EPythonCommandExecutionMode::ExecuteFile;
    PythonCommand.FileExecutionScope = EPythonFileExecutionScope::Public;
    if (PythonPlugin->ExecPythonCommandEx(PythonCommand))
    {
        for (const FPythonLogOutputEntry& Entry : PythonCommand.LogOutput)
        {
            FString Json;
            TSharedPtr<FJsonObject> Result;
            if (Entry.Output.Split(TEXT("ASSET_FORGE_GATE_RESULT="), nullptr, &Json)
                && FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Json), Result) && Result)
            {
                return Result;
            }
        }
    }

    OutError = TEXT("门禁动作未返回结果。请查看 Output Log，再重新检查包体。");
    return nullptr;
}

static TSharedPtr<FJsonObject> ExecuteGatePythonCommand(const FString& FunctionName, const FString& PackageDir,
    const FString& ImportOptionsJson, const FString& ConfirmationToken, FString& OutError, const FString& ReportPath = FString())
{
    return ExecuteWorkbenchPythonCommand(
        BuildGatePythonAction(FunctionName, PackageDir, ImportOptionsJson, ConfirmationToken, ReportPath), OutError);
}

static TSharedRef<SWidget> Section(const FText& Title, TSharedRef<SWidget> Body, bool InitiallyCollapsed = false, FName Tag = NAME_None)
{
    return SNew(SExpandableArea).Tag(Tag)
        .InitiallyCollapsed(InitiallyCollapsed)
        .HeaderPadding(FMargin(8.0f, 5.0f))
        .Padding(FMargin(0.0f, 4.0f, 0.0f, 8.0f))
        .BorderImage(FAppStyle::GetBrush("DetailsView.CategoryTop"))
        .HeaderContent()
        [
            SNew(STextBlock)
            .Text(Title)
            .Font(StrongFont())
        ]
        .BodyContent()
        [
            SNew(SBorder)
            .BorderImage(FAppStyle::GetBrush("ToolPanel.GroupBorder"))
            .Padding(FMargin(8.0f))
            [
                Body
            ]
        ];
}

static TSharedPtr<FJsonObject> ReadJsonObject(const FString& FilePath)
{
    FString Text;
    if (!FFileHelper::LoadFileToString(Text, *FilePath))
    {
        return nullptr;
    }

    TSharedPtr<FJsonObject> Object;
    const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Text);
    if (!FJsonSerializer::Deserialize(Reader, Object) || !Object.IsValid())
    {
        return nullptr;
    }
    return Object;
}

static int32 JsonArrayCount(const TSharedPtr<FJsonObject>& Object, const FString& FieldName)
{
    const TArray<TSharedPtr<FJsonValue>>* Values = nullptr;
    return Object.IsValid() && Object->TryGetArrayField(FieldName, Values) ? Values->Num() : 0;
}

static int32 JsonIntField(const TSharedPtr<FJsonObject>& Object, const FString& FieldName, int32 DefaultValue = 0)
{
    double Value = 0.0;
    return Object.IsValid() && Object->TryGetNumberField(FieldName, Value) ? FMath::Max(0, FMath::RoundToInt(Value)) : DefaultValue;
}

static TSharedPtr<FJsonObject> JsonObjectField(const TSharedPtr<FJsonObject>& Object, const FString& FieldName)
{
    const TSharedPtr<FJsonValue> Value = Object.IsValid() ? Object->TryGetField(FieldName) : nullptr;
    return Value.IsValid() && Value->Type == EJson::Object ? Value->AsObject() : nullptr;
}

static TSharedPtr<FJsonObject> EffectiveImportOptionsObject(const TSharedPtr<FJsonObject>& Report)
{
    const TSharedPtr<FJsonObject> FbxOptionsReport = JsonObjectField(Report, TEXT("fbx_import_options_report"));
    const TSharedPtr<FJsonObject> EffectiveOptions = JsonObjectField(FbxOptionsReport, TEXT("options"));
    if (EffectiveOptions.IsValid())
    {
        return EffectiveOptions;
    }
    const TSharedPtr<FJsonObject> ResolvedPreset = JsonObjectField(Report, TEXT("resolved_preset"));
    return ResolvedPreset.IsValid() ? ResolvedPreset : Report;
}

static bool TryReportStringField(const TSharedPtr<FJsonObject>& Summary, const TSharedPtr<FJsonObject>& Report, const FString& FieldName, FString& OutValue)
{
    FString Value;
    if (Summary.IsValid() && Summary->TryGetStringField(FieldName, Value) && !Value.TrimStartAndEnd().IsEmpty())
    {
        OutValue = Value.TrimStartAndEnd();
        return true;
    }
    if (Report.IsValid() && Report->TryGetStringField(FieldName, Value) && !Value.TrimStartAndEnd().IsEmpty())
    {
        OutValue = Value.TrimStartAndEnd();
        return true;
    }
    return false;
}

static bool TryReportBoolField(const TSharedPtr<FJsonObject>& Summary, const TSharedPtr<FJsonObject>& Report, const FString& FieldName, bool& OutValue)
{
    return (Summary.IsValid() && Summary->TryGetBoolField(FieldName, OutValue))
        || (Report.IsValid() && Report->TryGetBoolField(FieldName, OutValue));
}

static int32 ReportIntField(const TSharedPtr<FJsonObject>& Summary, const TSharedPtr<FJsonObject>& Report, const FString& FieldName, int32 DefaultValue = 0)
{
    if (Summary.IsValid() && Summary->HasField(FieldName))
    {
        return JsonIntField(Summary, FieldName, DefaultValue);
    }
    return JsonIntField(Report, FieldName, DefaultValue);
}

static void AttachExportCounts(FAssetForgePackageItem& Item, const TSharedPtr<FJsonObject>& Report)
{
    if (!Report.IsValid())
    {
        return;
    }
    Item.SourceMeshCount = FMath::Max(Item.SourceMeshCount, JsonIntField(Report, TEXT("mesh_count"), 0));
    Item.MaterialSlotCount = FMath::Max(Item.MaterialSlotCount, JsonIntField(Report, TEXT("material_slots"), 0));
    if (Item.MaterialCount == 0 && Item.MaterialSlotCount > 0)
    {
        Item.MaterialCount = Item.MaterialSlotCount;
    }
    Item.MeshCount = FMath::Max(Item.MeshCount, Item.SourceMeshDisplayCount());
}

static void AttachImportOptions(FAssetForgePackageItem& Item, const TSharedPtr<FJsonObject>& Report)
{
    if (!Report.IsValid())
    {
        return;
    }

    const TSharedPtr<FJsonObject> EffectiveOptions = EffectiveImportOptionsObject(Report);
    const TSharedPtr<FJsonObject> Preset = JsonObjectField(Report, TEXT("resolved_preset"));
    bool bCombineMeshes = false;
    if (TryReportBoolField(EffectiveOptions, Preset, TEXT("combine_meshes"), bCombineMeshes))
    {
        Item.bCombineMeshesKnown = true;
        Item.bCombineMeshes = bCombineMeshes;
    }
    if (TryReportBoolField(EffectiveOptions, Preset, TEXT("build_nanite"), bCombineMeshes))
    {
        Item.NanitePolicy = bCombineMeshes ? TEXT("Nanite 开启") : TEXT("Nanite 关闭");
    }
    TryReportStringField(EffectiveOptions, Preset, TEXT("normal_import_method"), Item.NormalImportMethod);
    if (!TryReportStringField(EffectiveOptions, Preset, TEXT("static_mesh_lod_group"), Item.StaticMeshLodPolicy))
    {
        bool bImportMeshLods = false;
        if (TryReportBoolField(EffectiveOptions, Preset, TEXT("import_mesh_lods"), bImportMeshLods))
        {
            Item.StaticMeshLodPolicy = bImportMeshLods ? TEXT("导入源 LOD") : TEXT("忽略源 LOD");
        }
        else
        {
            TryReportStringField(Preset, Report, TEXT("static_mesh_lod_import_policy"), Item.StaticMeshLodPolicy);
        }
    }
}

static FString DecisionLabelFromCode(const FString& Decision, const FString& Status, bool bCanImportKnown, bool bCanImport)
{
    if (bCanImportKnown && bCanImport)
    {
        return TEXT("报告放行：可以导入");
    }
    if (Decision.Equals(TEXT("ready"), ESearchCase::IgnoreCase) || Decision.Equals(TEXT("accepted"), ESearchCase::IgnoreCase))
    {
        return TEXT("报告放行：可以导入");
    }
    if (Decision.Equals(TEXT("blocked"), ESearchCase::IgnoreCase) || Decision.Equals(TEXT("rejected"), ESearchCase::IgnoreCase))
    {
        return TEXT("报告阻断：需要修复");
    }
    if (Decision.Equals(TEXT("warning"), ESearchCase::IgnoreCase))
    {
        return TEXT("报告警告：请确认后再导入");
    }
    if (Decision.Equals(TEXT("not_run"), ESearchCase::IgnoreCase) || Decision.Equals(TEXT("skipped"), ESearchCase::IgnoreCase))
    {
        return TEXT("报告未完成：请重新检查");
    }
    if (Status.Equals(TEXT("success"), ESearchCase::IgnoreCase) || Status.Equals(TEXT("pass"), ESearchCase::IgnoreCase))
    {
        return TEXT("报告放行：可以导入");
    }
    if (Status.Equals(TEXT("warning"), ESearchCase::IgnoreCase))
    {
        return TEXT("报告警告：请确认后再导入");
    }
    if (Status.Equals(TEXT("failed"), ESearchCase::IgnoreCase) || Status.Equals(TEXT("error"), ESearchCase::IgnoreCase))
    {
        return TEXT("报告阻断：需要修复");
    }
    return TEXT("已生成导入报告");
}

static void AttachOperatorNotices(FAssetForgePackageItem& Item, const TSharedPtr<FJsonObject>& Report)
{
    TArray<FString> Warnings, Errors;
    if (Report->TryGetStringArrayField(TEXT("operator_warnings"), Warnings))
    {
        Item.OperatorWarnings = MoveTemp(Warnings);
    }
    if (Report->TryGetStringArrayField(TEXT("operator_errors"), Errors))
    {
        Item.OperatorErrors = MoveTemp(Errors);
    }
}

static void AttachHandoffReceipt(FAssetForgePackageItem& Item, const TSharedPtr<FJsonObject>& Result)
{
    // Python validates the receipt against the current project, manifest and target.
    const auto Receipt = JsonObjectField(Result, TEXT("handoff_receipt"));
    FString ReceiptId;
    TArray<FString> Meshes;
    Item.HandoffReceipt.Reset();
    if (Receipt && Receipt->TryGetStringField(TEXT("receipt"), ReceiptId) && !ReceiptId.IsEmpty()
        && Receipt->TryGetStringArrayField(TEXT("meshes"), Meshes) && !Meshes.IsEmpty())
    {
        Item.HandoffReceipt = Receipt;
        Item.bImported = true;
    }
}

static void AttachReportDecision(FAssetForgePackageItem& Item, const TSharedPtr<FJsonObject>& Report)
{
    if (!Report.IsValid())
    {
        return;
    }

    const TSharedPtr<FJsonObject> Summary = JsonObjectField(Report, TEXT("summary"));
    FString Status;
    TryReportStringField(Summary, Report, TEXT("status"), Status);
    TryReportStringField(Summary, Report, TEXT("decision"), Item.ReportDecision);
    TryReportStringField(Summary, Report, TEXT("decision_label"), Item.ReportDecisionLabel);
    TryReportStringField(Summary, Report, TEXT("next_action"), Item.ReportNextAction);
    Item.bReportCanImportKnown = TryReportBoolField(Summary, Report, TEXT("can_import"), Item.bReportCanImport)
        || TryReportBoolField(Summary, Report, TEXT("can_accept"), Item.bReportCanImport);
    if (!Item.bReportCanImportKnown
        && (Item.ReportDecision.Equals(TEXT("ready"), ESearchCase::IgnoreCase)
            || Status.Equals(TEXT("success"), ESearchCase::IgnoreCase)
            || Status.Equals(TEXT("pass"), ESearchCase::IgnoreCase)))
    {
        Item.bReportCanImportKnown = true;
        Item.bReportCanImport = true;
    }
    else if (!Item.bReportCanImportKnown
        && (Item.ReportDecision.Equals(TEXT("blocked"), ESearchCase::IgnoreCase)
            || Item.ReportDecision.Equals(TEXT("rejected"), ESearchCase::IgnoreCase)
            || Status.Equals(TEXT("failed"), ESearchCase::IgnoreCase)
            || Status.Equals(TEXT("error"), ESearchCase::IgnoreCase)))
    {
        Item.bReportCanImportKnown = true;
        Item.bReportCanImport = false;
    }
    Item.ReportWarningCount = ReportIntField(Summary, Report, TEXT("warning_count"), JsonArrayCount(Report, TEXT("warnings")));
    Item.ReportErrorCount = ReportIntField(Summary, Report, TEXT("error_count"), JsonArrayCount(Report, TEXT("errors")));
    // The package summary counts checks. The flow summary counts messages across stages.
    FString Stage;
    Report->TryGetStringField(TEXT("stage"), Stage);
    const bool bFlow = Stage == TEXT("package_acceptance_flow");
    const auto PackageReport = bFlow ? JsonObjectField(Report, TEXT("package_acceptance")) : Report;
    const auto Checks = JsonObjectField(PackageReport, TEXT("summary"));
    AttachOperatorNotices(Item, Report);
    const int32 WarningChecks = JsonIntField(Checks, TEXT("warning_count"), INDEX_NONE);
    const int32 BlockingChecks = JsonIntField(Checks, TEXT("error_count"), INDEX_NONE);
    Item.ReportRiskCaption.Reset();
    if (WarningChecks >= 0 && BlockingChecks >= 0)
    {
        Item.ReportRiskCaption = FString::Printf(TEXT("包体检查：%d 项警告 / %d 项阻断"), WarningChecks, BlockingChecks);
    }
    else if (bFlow)
    {
        Item.ReportRiskCaption = FString::Printf(TEXT("流程记录：%d 条提醒 / %d 条阻断"), Item.ReportWarningCount, Item.ReportErrorCount);
    }
    if (Item.ReportDecisionLabel.IsEmpty())
    {
        Item.ReportDecisionLabel = DecisionLabelFromCode(Item.ReportDecision, Status, Item.bReportCanImportKnown, Item.bReportCanImport);
    }
    bool bGatePassed = false;
    if (Report->TryGetBoolField(TEXT("gate_passed"), bGatePassed) && !bGatePassed)
    {
        Item.bReportCanImportKnown = true;
        Item.bReportCanImport = false;
        Item.ReportDecisionLabel = TEXT("阻断");
    }
    Item.LastImportStatus = Item.ReportDecisionLabel;

    bool bRunImport = false;
    FString SavedProject, ImportStatus;
    const auto ImportReport = JsonObjectField(Report, TEXT("import"));
    if (bFlow && bGatePassed && Item.bReportCanImport && Item.ReportErrorCount == 0 && ImportReport
        && Report->TryGetBoolField(TEXT("run_import"), bRunImport) && bRunImport
        && Report->TryGetStringField(TEXT("workbench_project_file"), SavedProject) && !SavedProject.IsEmpty()
        && FPaths::IsSamePath(FPaths::ConvertRelativePathToFull(FPaths::GetProjectFilePath()), SavedProject)
        && ImportReport->TryGetStringField(TEXT("status"), ImportStatus)
        && ImportStatus == TEXT("success"))
    {
        TArray<FString> ImportedPaths;
        if (ImportReport->TryGetStringArrayField(TEXT("imported_assets"), ImportedPaths) && !ImportedPaths.IsEmpty())
        {
            Item.bImported = !ImportedPaths.ContainsByPredicate([](const FString& ObjectPath)
            {
                const FString PackageName = FPackageName::ObjectPathToPackageName(ObjectPath);
                return !FPackageName::IsValidLongPackageName(PackageName) || !FPackageName::DoesPackageExist(PackageName);
            });
        }
    }
}

static FString ReportImportPermissionText(const FAssetForgePackageItem& Item)
{
    if (!Item.bReportCanImportKnown)
    {
        return TEXT("导入许可未记录");
    }
    return Item.bReportCanImport ? TEXT("报告允许导入") : TEXT("报告不允许导入");
}

static FString ReportDecisionLine(const FAssetForgePackageItem& Item)
{
    return FString::Printf(
        TEXT("%s；%s；警告 %d / 阻断 %d"),
        *Item.ReportDecisionLabel,
        *ReportImportPermissionText(Item),
        Item.ReportWarningCount,
        Item.ReportErrorCount
    );
}

static bool LooksLikeAssetForgeManifest(const TSharedPtr<FJsonObject>& Object)
{
    return Object.IsValid()
        && (Object->HasField(TEXT("asset_name"))
            || Object->HasField(TEXT("source_dcc"))
            || Object->HasField(TEXT("schema_version"))
            || Object->HasField(TEXT("fbx_path"))
            || Object->HasField(TEXT("target_path")));
}

static void AddRootIfValid(TArray<FString>& Roots, const FString& Root)
{
    FString Normalized = FPaths::ConvertRelativePathToFull(Root);
    FPaths::NormalizeDirectoryName(Normalized);
    if (FPaths::DirectoryExists(Normalized))
    {
        Roots.AddUnique(Normalized);
    }
}

static void AddPackageDirCandidate(TArray<FString>& Roots, const FString& Candidate)
{
    FString Path = Candidate.TrimStartAndEnd();
    if (Path.IsEmpty())
    {
        return;
    }
    Path = FPaths::ConvertRelativePathToFull(Path);
    FPaths::NormalizeFilename(Path);
    if (FPaths::FileExists(Path))
    {
        AddRootIfValid(Roots, FPaths::GetPath(Path));
        return;
    }
    AddRootIfValid(Roots, Path);
}

static void AddPackageDirField(TArray<FString>& Roots, const TSharedPtr<FJsonObject>& Object, const FString& FieldName)
{
    FString Value;
    if (Object.IsValid() && Object->TryGetStringField(FieldName, Value))
    {
        AddPackageDirCandidate(Roots, Value);
    }
}

static void AddPackageDirFields(TArray<FString>& Roots, const TSharedPtr<FJsonObject>& Object)
{
    AddPackageDirField(Roots, Object, TEXT("package_dir"));
    AddPackageDirField(Roots, Object, TEXT("manifest_path"));
    AddPackageDirField(Roots, Object, TEXT("fbx_path"));
    AddPackageDirField(Roots, Object, TEXT("report_path"));
}

static void AddPackageDirsFromLog(TArray<FString>& Roots, const FString& PackageLogPath)
{
    if (!FPaths::FileExists(PackageLogPath))
    {
        return;
    }

    FString Text;
    if (!FFileHelper::LoadFileToString(Text, *PackageLogPath))
    {
        return;
    }

    TArray<FString> Lines;
    Text.ParseIntoArrayLines(Lines, false);
    const int32 FirstLine = FMath::Max(0, Lines.Num() - 200);
    for (int32 Index = FirstLine; Index < Lines.Num(); ++Index)
    {
        const FString Line = Lines[Index].TrimStartAndEnd();
        if (Line.IsEmpty())
        {
            continue;
        }

        TSharedPtr<FJsonObject> Entry;
        const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Line);
        if (!FJsonSerializer::Deserialize(Reader, Entry) || !Entry.IsValid())
        {
            continue;
        }

        AddPackageDirFields(Roots, Entry);
        AddPackageDirFields(Roots, JsonObjectField(Entry, TEXT("outputs")));
        AddPackageDirFields(Roots, JsonObjectField(Entry, TEXT("inputs")));
    }
}

static void AddKnownDccLogPackageDirs(TArray<FString>& Roots, const FString& ReportsRoot)
{
    const FString LogsRoot = FPaths::Combine(ReportsRoot, TEXT("logs"));
    AddPackageDirsFromLog(Roots, FPaths::Combine(LogsRoot, TEXT("latest_maya.log")));
    AddPackageDirsFromLog(Roots, FPaths::Combine(LogsRoot, TEXT("latest_blender.log")));
    AddPackageDirsFromLog(Roots, FPaths::Combine(LogsRoot, TEXT("latest_unreal.log")));
}

static void AddPluginInstallMetadataRoots(TArray<FString>& Roots)
{
    FString PluginPythonRoot;
    if (const TSharedPtr<IPlugin> Plugin = IPluginManager::Get().FindPlugin(TEXT("AssetForge")))
    {
        PluginPythonRoot = FPaths::ConvertRelativePathToFull(FPaths::Combine(Plugin->GetBaseDir(), TEXT("Content"), TEXT("Python")));
    }
    if (PluginPythonRoot.IsEmpty())
    {
        return;
    }

    const FString MetadataPath = FPaths::Combine(PluginPythonRoot, TEXT("config"), TEXT("asset_forge_install.json"));
    const TSharedPtr<FJsonObject> Metadata = ReadJsonObject(MetadataPath);
    if (!Metadata.IsValid())
    {
        return;
    }

    FString SourceRepoRoot;
    if (Metadata->TryGetStringField(TEXT("source_repo_root"), SourceRepoRoot))
    {
        const FString SourceReportsRoot = FPaths::Combine(SourceRepoRoot, TEXT("AssetForgeReports"));
        AddRootIfValid(Roots, FPaths::Combine(SourceReportsRoot, DccPackageRootName));
        AddKnownDccLogPackageDirs(Roots, SourceReportsRoot);
    }

    FString SourceLatestMayaLog;
    if (Metadata->TryGetStringField(TEXT("source_latest_maya_log"), SourceLatestMayaLog))
    {
        AddPackageDirsFromLog(Roots, SourceLatestMayaLog);
    }
}

static TArray<FString> CollectExportRoots()
{
    TArray<FString> Roots;
    AddRootIfValid(Roots, FPaths::Combine(FPlatformProcess::UserDir(), TEXT("AssetForge"), TEXT("Exports")));
    AddRootIfValid(Roots, FPaths::Combine(FPaths::ProjectDir(), TEXT("AssetForgeReports"), DccPackageRootName));
    AddRootIfValid(Roots, FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("AssetForge"), TEXT("Exports")));

    FString EnvRoot = FPlatformMisc::GetEnvironmentVariable(TEXT("ASSET_FORGE_EXPORT_ROOT"));
    if (!EnvRoot.IsEmpty())
    {
        AddRootIfValid(Roots, EnvRoot);
    }

    FString RepoRoot = FPlatformMisc::GetEnvironmentVariable(TEXT("ASSET_FORGE_REPO_ROOT"));
    if (!RepoRoot.IsEmpty())
    {
        const FString RepoReportsRoot = FPaths::Combine(RepoRoot, TEXT("AssetForgeReports"));
        AddRootIfValid(Roots, FPaths::Combine(RepoReportsRoot, DccPackageRootName));
        AddKnownDccLogPackageDirs(Roots, RepoReportsRoot);
    }

    FString SourceRoot = FPlatformMisc::GetEnvironmentVariable(TEXT("ASSET_FORGE_SOURCE_ROOT"));
    if (!SourceRoot.IsEmpty())
    {
        const FString SourceReportsRoot = FPaths::Combine(SourceRoot, TEXT("AssetForgeReports"));
        AddRootIfValid(Roots, FPaths::Combine(SourceReportsRoot, DccPackageRootName));
        AddKnownDccLogPackageDirs(Roots, SourceReportsRoot);
    }

    AddPluginInstallMetadataRoots(Roots);
    return Roots;
}

static bool ShouldSkipDirectory(const FString& DirectoryName)
{
    return DirectoryName.StartsWith(TEXT("."))
        || DirectoryName.Equals(TEXT("__pycache__"), ESearchCase::IgnoreCase)
        || DirectoryName.Equals(TEXT("test_tmp"), ESearchCase::IgnoreCase)
        || DirectoryName.Equals(TEXT("Intermediate"), ESearchCase::IgnoreCase)
        || DirectoryName.Equals(TEXT("Saved"), ESearchCase::IgnoreCase)
        || DirectoryName.Equals(TEXT("backups"), ESearchCase::IgnoreCase)
        || DirectoryName.Equals(TEXT("debug"), ESearchCase::IgnoreCase)
        || DirectoryName.Equals(TEXT("field_validation"), ESearchCase::IgnoreCase)
        || DirectoryName.Equals(TEXT("logs"), ESearchCase::IgnoreCase)
        || DirectoryName.Equals(TEXT("portfolio_captures"), ESearchCase::IgnoreCase)
        || DirectoryName.Equals(TEXT("runtime_alias"), ESearchCase::IgnoreCase);
}

static TSharedPtr<FAssetForgePackageItem> BuildPackageItemFromManifest(const FString& ManifestPath)
{
    const TSharedPtr<FJsonObject> Manifest = ReadJsonObject(ManifestPath);
    if (!LooksLikeAssetForgeManifest(Manifest))
    {
        return nullptr;
    }

    TSharedPtr<FAssetForgePackageItem> Item = MakeShared<FAssetForgePackageItem>();
    Item->ManifestPath = ManifestPath;
    Item->PackageDir = FPaths::GetPath(ManifestPath);
    Manifest->TryGetStringField(TEXT("asset_name"), Item->AssetName);
    Manifest->TryGetStringField(TEXT("source_dcc"), Item->SourceDcc);
    Manifest->TryGetStringField(TEXT("target_path"), Item->TargetPath);
    Manifest->TryGetStringField(TEXT("schema_version"), Item->SchemaVersion);
    if (Item->SchemaVersion.IsEmpty())
    {
        Manifest->TryGetStringField(TEXT("asset_forge_schema_version"), Item->SchemaVersion);
    }
    const TSharedPtr<FJsonObject> PackageNaming = JsonObjectField(Manifest, TEXT("package_naming"));
    if (PackageNaming.IsValid())
    {
        PackageNaming->TryGetStringField(TEXT("package_name"), Item->ManifestPackageName);
        PackageNaming->TryGetStringField(TEXT("version_mode"), Item->PackageVersionMode);
        PackageNaming->TryGetStringField(TEXT("version_label"), Item->PackageVersionLabel);
    }
    const TSharedPtr<FJsonObject> ProjectPreset = JsonObjectField(Manifest, TEXT("project_preset"));
    if (ProjectPreset.IsValid())
    {
        ProjectPreset->TryGetStringField(TEXT("preset_name"), Item->ProjectPresetName);
        ProjectPreset->TryGetStringField(TEXT("preset_version"), Item->ProjectPresetVersion);
    }
    if (Item->AssetName.IsEmpty())
    {
        Item->AssetName = FPaths::GetBaseFilename(ManifestPath).Replace(TEXT("_manifest"), TEXT(""));
    }
    if (Item->ManifestPackageName.IsEmpty())
    {
        Item->ManifestPackageName = FPaths::GetCleanFilename(Item->PackageDir);
    }
    Item->TextureCount = JsonArrayCount(Manifest, TEXT("textures"));
    Item->MaterialCount = JsonArrayCount(Manifest, TEXT("materials"));
    const TArray<TSharedPtr<FJsonValue>>* Materials = nullptr;
    if (Manifest->TryGetArrayField(TEXT("materials"), Materials))
    {
        TArray<FString> Lines;
        for (const auto& Entry : *Materials)
        {
            const auto Material = Entry->AsObject();
            FString Name;
            if (!Material || !Material->TryGetStringField(TEXT("name"), Name)) continue;
            const TArray<TSharedPtr<FJsonValue>>* Textures = nullptr;
            TArray<FString> Bindings;
            if (Material->TryGetArrayField(TEXT("textures"), Textures))
            {
                for (const auto& Value : *Textures)
                {
                    const auto Texture = Value->AsObject();
                    FString File;
                    if (Texture && (Texture->TryGetStringField(TEXT("package_path"), File) || Texture->TryGetStringField(TEXT("path"), File)))
                        Bindings.AddUnique(FPaths::GetBaseFilename(File));
                }
            }
            Lines.Add(Bindings.Num() ? Name + TEXT(" → ") + FString::Join(Bindings, TEXT("、")) : Name);
        }
        Item->MaterialBindings = FString::Join(Lines, TEXT("\n"));
    }
    Item->MaterialSlotCount = JsonArrayCount(Manifest, TEXT("material_slots"));
    if (Item->MaterialCount == 0 && Item->MaterialSlotCount > 0)
    {
        Item->MaterialCount = Item->MaterialSlotCount;
    }
    Item->FbxFileCount = Manifest->HasField(TEXT("fbx_path")) ? 1 : JsonArrayCount(Manifest, TEXT("fbx_files"));
    Item->SourceMeshCount = JsonIntField(Manifest, TEXT("mesh_count"), JsonArrayCount(Manifest, TEXT("meshes")));
    const TSharedPtr<FJsonObject> Checks = JsonObjectField(Manifest, TEXT("checks"));
    const TSharedPtr<FJsonObject> MeshExistsCheck = JsonObjectField(Checks, TEXT("mesh_exists"));
    Item->SourceMeshCount = FMath::Max(Item->SourceMeshCount, JsonIntField(MeshExistsCheck, TEXT("value"), 0));
    const auto AssetBudgets = JsonObjectField(Manifest, TEXT("asset_budgets"));
    Item->TriangleBudget = JsonIntField(AssetBudgets, TEXT("triangles"), INDEX_NONE);
    Item->MaterialSlotBudget = JsonIntField(AssetBudgets, TEXT("material_slots"), INDEX_NONE);
    Item->MeshCount = Item->SourceMeshDisplayCount();
    if (Item->MeshCount == 0 && Item->FbxFileCount > 0)
    {
        Item->MeshCount = Item->FbxFileCount;
    }
    Item->ModifiedTime = IFileManager::Get().GetTimeStamp(*ManifestPath);

    TArray<FString> ExportReports;
    IFileManager::Get().FindFiles(ExportReports, *(Item->PackageDir / TEXT("*export_report.json")), true, false);
    if (ExportReports.Num() > 0)
    {
        ExportReports.Sort();
        AttachExportCounts(*Item, ReadJsonObject(Item->PackageDir / ExportReports.Last()));
    }

    // A dry-run import report describes one substep. The package flow owns the gate decision.
    const FString FlowReport = Item->PackageDir / TEXT("AssetForgeReports/package_acceptance_flow_report.json");
    if (FPaths::FileExists(FlowReport))
    {
        Item->ImportReportPath = FlowReport;
    }
    else
    {
        TArray<FString> Reports;
        IFileManager::Get().FindFiles(Reports, *(Item->PackageDir / TEXT("*import_report.json")), true, false);
        Reports.Sort();
        if (!Reports.IsEmpty()) Item->ImportReportPath = Item->PackageDir / Reports.Last();
    }
    if (!Item->ImportReportPath.IsEmpty())
    {
        Item->ReportTime = IFileManager::Get().GetTimeStamp(*Item->ImportReportPath);
        const TSharedPtr<FJsonObject> Report = ReadJsonObject(Item->ImportReportPath);
        if (Report.IsValid())
        {
            Item->LastImportStatus = Report->HasField(TEXT("status")) ? Report->GetStringField(TEXT("status")) : TEXT("已生成导入报告");
            AttachReportDecision(*Item, Report);
            AttachImportOptions(*Item, Report);
        }
    }

    return Item;
}


#if WITH_DEV_AUTOMATION_TESTS
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FPackageGateReportTest, "AssetForge.Workbench.GateReportPrecedence",
    EAutomationTestFlags::EditorContext | EAutomationTestFlags::EngineFilter)

bool FPackageGateReportTest::RunTest(const FString&)
{
    const FString Dir = FPaths::ProjectSavedDir() / TEXT("Automation/AssetForge") / FGuid::NewGuid().ToString();
    const FString Reports = Dir / TEXT("AssetForgeReports");
    if (!IFileManager::Get().MakeDirectory(*Reports, true)) return false;
    const FString Manifest = Dir / TEXT("SM_Gate_manifest.json");
    const FString Legacy = Dir / TEXT("SM_Gate_import_report.json");
    const FString Flow = Reports / TEXT("package_acceptance_flow_report.json");
    FFileHelper::SaveStringToFile(TEXT("{\"asset_name\":\"SM_Gate\"}"), *Manifest);
    FFileHelper::SaveStringToFile(TEXT("{\"status\":\"skipped\",\"summary\":{\"can_import\":true},\"checks\":[{\"status\":\"warning\",\"label\":\"Raw legacy notice\"}]}"), *Legacy);
    const auto Old = BuildPackageItemFromManifest(Manifest);
    TestTrue(TEXT("Legacy packages use their sole report"), Old && Old->bReportCanImport && Old->ImportReportPath == Legacy);
    TestTrue(TEXT("A discovery read does not display untranslated legacy notices"), Old && Old->OperatorWarnings.IsEmpty());
    FFileHelper::SaveStringToFile(TEXT("{\"gate_passed\":false,\"summary\":{\"can_import\":false,\"error_count\":1},")
        TEXT("\"operator_warnings\":[\"请复核贴图槽位\"],\"operator_errors\":[\"包体文件缺失\"]}"), *Flow);
    const auto Blocked = BuildPackageItemFromManifest(Manifest);
    TestTrue(TEXT("Failed flow takes precedence over permissive skipped substep"), Blocked && Blocked->ImportReportPath == Flow
        && Blocked->bReportCanImportKnown && !Blocked->bReportCanImport && Blocked->ReportErrorCount == 1);
    TestTrue(TEXT("Persisted operator arrays survive discovery"),
        Blocked && Blocked->OperatorWarnings == TArray<FString>{TEXT("请复核贴图槽位")}
            && Blocked->OperatorErrors == TArray<FString>{TEXT("包体文件缺失")});

    const auto VerifiedReceipt = MakeShared<FJsonObject>();
    VerifiedReceipt->SetStringField(TEXT("receipt"), TEXT("saved-receipt"));
    VerifiedReceipt->SetArrayField(TEXT("meshes"), {MakeShared<FJsonValueString>(TEXT("/Game/AF/SM_Gate.SM_Gate"))});
    const auto Response = MakeShared<FJsonObject>();
    Response->SetObjectField(TEXT("handoff_receipt"), VerifiedReceipt);
    FAssetForgePackageItem Imported;
    AttachHandoffReceipt(Imported, Response);
    TestTrue(TEXT("A verified backend receipt restores handoff"), Imported.bImported && Imported.HandoffReceipt == VerifiedReceipt);
    AttachHandoffReceipt(Imported, MakeShared<FJsonObject>());
    TestFalse(TEXT("A missing receipt revokes handoff"), Imported.HandoffReceipt.IsValid());
    IFileManager::Get().Delete(*Manifest);
    IFileManager::Get().Delete(*Legacy);
    IFileManager::Get().Delete(*Flow);
    IFileManager::Get().DeleteDirectory(*Reports);
    IFileManager::Get().DeleteDirectory(*Dir);
    return true;
}
#endif

static void FindManifestsRecursive(const FString& Directory, int32 Depth, TSet<FString>& OutManifestPaths)
{
    if (Depth > 5)
    {
        return;
    }

    TArray<FString> Manifests;
    IFileManager::Get().FindFiles(Manifests, *(Directory / TEXT("*_manifest.json")), true, false);
    for (const FString& Manifest : Manifests)
    {
        OutManifestPaths.Add(Directory / Manifest);
    }

    TArray<FString> Children;
    IFileManager::Get().FindFiles(Children, *(Directory / TEXT("*")), false, true);
    for (const FString& Child : Children)
    {
        if (!ShouldSkipDirectory(Child))
        {
            FindManifestsRecursive(Directory / Child, Depth + 1, OutManifestPaths);
        }
    }
}

class SAssetForgeGatePanel : public SCompoundWidget
{
public:
    SLATE_BEGIN_ARGS(SAssetForgeGatePanel) {}
    SLATE_END_ARGS()

    void Construct(const FArguments& InArgs)
    {
        InitializeGateImportOptionLists();
        RefreshPackages();

        ChildSlot
        [
            SNew(SSplitter)
            + SSplitter::Slot().Value(0.32f)
            [SNew(SBox).IsEnabled_Lambda([this](){ return GateOperation == EGateOperation::Idle; })[BuildPackageColumn()]]
            + SSplitter::Slot().Value(0.68f)[BuildReviewColumn()]
        ];
    }

private:
    TArray<TSharedPtr<FAssetForgePackageItem>> Packages;
    TArray<TSharedPtr<FAssetForgePackageItem>> FilteredPackages;
    TArray<TSharedPtr<FString>> History;
    TArray<TSharedPtr<FString>> NormalImportOptions;
    TArray<TSharedPtr<FString>> NormalGenerationOptions;
    TArray<TSharedPtr<FString>> StaticMeshLodGroupOptions;
    TArray<TSharedPtr<FString>> VertexColorImportOptions;
    TArray<FString> ScanRoots;
    TSharedPtr<FAssetForgePackageItem> SelectedPackage;
    TSharedPtr<SListView<TSharedPtr<FAssetForgePackageItem>>> PackageListView;
    FString SearchText;
    FString ManualPackageRoot;
    FString LastDebugExportPath;
    FDateTime LastRefreshTime = FDateTime::MinValue();
    FString GateMessage = TEXT("请先刷新包体列表；找到 AF 包体后选中一项，再检查或导入。");
    bool bScanManualRootOnly = false;
    bool bGateImportMaterials = true;
    bool bGateImportTextures = true;
    bool bGateCombineMeshes = false;
    bool bGateImportLods = true;
    bool bGateAutoGenerateCollision = true;
    bool bGateOneConvexHullPerUcx = true;
    bool bGateRemoveDegenerates = true;
    bool bGateComputeWeightedNormals = false;
    bool bGateGenerateLightmapUvs = true;
    bool bGateBuildNanite = false;
    bool bGateBuildReversedIndexBuffer = false;
    bool bGateConvertScene = true;
    bool bGateForceFrontXAxis = false;
    bool bGateConvertSceneUnit = true;
    bool bGateTransformVertexToAbsolute = true;
    bool bGateBakePivotInVertex = false;
    float GateImportTranslationX = 0.0f;
    float GateImportTranslationY = 0.0f;
    float GateImportTranslationZ = 0.0f;
    float GateImportRotationPitch = 0.0f;
    float GateImportRotationYaw = 0.0f;
    float GateImportRotationRoll = 0.0f;
    float GateImportUniformScale = 1.0f;
    float GateVertexOverrideColorR = 1.0f;
    float GateVertexOverrideColorG = 1.0f;
    float GateVertexOverrideColorB = 1.0f;
    FString GateNormalImportMethod = TEXT("import_normals_and_tangents");
    FString GateNormalGenerationMethod = TEXT("mikk_t_space");
    FString GateStaticMeshLodGroup = TEXT("project_default");
    TSharedPtr<FJsonObject> WriteSummary;
    FString ConfirmedOptions;
    enum class EGateOperation { Idle, Check, DryRun, PrepareWrite, AwaitConfirm, Import };
    EGateOperation GateOperation = EGateOperation::Idle;
    FString GateVertexColorImportOption = TEXT("replace");

    TSharedRef<SWidget> BuildPackageColumn()
    {
        return SNew(SBorder)
            .BorderImage(FAppStyle::GetBrush("ToolPanel.GroupBorder"))
            .Padding(FMargin(8.0f))
            [
                SNew(SVerticalBox)
                + SVerticalBox::Slot().AutoHeight()
                [
                    SNew(SSearchBox).Tag(TEXT("Gate.Search"))
                    .HintText(LOCTEXT("SearchHint", "搜索包体名 / DCC / 目标路径 / 材质规则"))
                    .OnTextChanged(this, &SAssetForgeGatePanel::HandleSearchChanged)
                ]
                + SVerticalBox::Slot().AutoHeight().Padding(0,6,0,0)
                [
                    Section(
                        LOCTEXT("ScanSection", "包体来源"),
                        SNew(SVerticalBox)
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("ScanSourceSummary", "扫描来源"), StaticCastSharedRef<SWidget>(WrappedTextBlock(TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetScanSourceSummaryText), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetScanRootsText))))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("ManualScanRoot", "已选目录"), StaticCastSharedRef<SWidget>(WrappedTextBlock(TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetManualPackageRootShortText), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetManualPackageRootTooltip))))]
                        + SVerticalBox::Slot().AutoHeight().Padding(0.0f, 6.0f, 0.0f, 0.0f)
                        [
                            SNew(SHorizontalBox)
                            + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)
                            [
                                SNew(SCheckBox)
                                .IsChecked(TAttribute<ECheckBoxState>::CreateSP(this, &SAssetForgeGatePanel::IsManualRootOnlyChecked))
                                .OnCheckStateChanged(this, &SAssetForgeGatePanel::OnManualRootOnlyChanged)
                                [
                                    TextBlock(LOCTEXT("ManualRootOnly", "只看已选目录"))
                                ]
                            ]
                        ]
                        + SVerticalBox::Slot().AutoHeight().Padding(0.0f, 8.0f, 0.0f, 0.0f)
                        [
                            SNew(SWrapBox).UseAllottedSize(true).InnerSlotPadding(FVector2D(6, 4))
                            + SWrapBox::Slot()[CompactButton(LOCTEXT("ChoosePackageRoot", "选择包体目录"), "Icons.FolderOpen", FOnClicked::CreateSP(this, &SAssetForgeGatePanel::HandleChoosePackageRootClicked))]
                            + SWrapBox::Slot()[CompactButton(LOCTEXT("Refresh", "刷新"), "Icons.Refresh", FOnClicked::CreateSP(this, &SAssetForgeGatePanel::HandleRefreshClicked))]
                            + SWrapBox::Slot()[CompactButton(LOCTEXT("ClearVisiblePackages", "清空列表"), "Icons.Delete", FOnClicked::CreateSP(this, &SAssetForgeGatePanel::HandleClearListClicked))]
                        ]
                    )
                ]
                + SVerticalBox::Slot()
                .FillHeight(1.0f)
                .Padding(0.0f, 8.0f, 0.0f, 0.0f)
                [
                    SAssignNew(PackageListView, SListView<TSharedPtr<FAssetForgePackageItem>>)
                    .ListItemsSource(&FilteredPackages)
                    .OnGenerateRow(this, &SAssetForgeGatePanel::MakePackageRow)
                    .OnSelectionChanged(this, &SAssetForgeGatePanel::OnPackageSelected)
                ]
            ];
    }

    TSharedRef<SWidget> BuildReviewColumn()
    {
        return SNew(SScrollBox)
            + SScrollBox::Slot()
            [
                SNew(SVerticalBox)
                + SVerticalBox::Slot().AutoHeight().Padding(0,0,0,8)
                [
                    SNew(SWrapBox).UseAllottedSize(true).InnerSlotPadding(FVector2D(6,4))
                    + SWrapBox::Slot()
                    [SNew(SButton).Tag(TEXT("Gate.Check"))
                        .Text_Lambda([this](){ return GateOperation == EGateOperation::Check
                            ? LOCTEXT("CheckingPackage", "正在检查包体…") : LOCTEXT("CheckPackage", "检查包体"); })
                        .IsEnabled(this,&SAssetForgeGatePanel::HasSelectedPackage)
                        .ToolTipText(this,&SAssetForgeGatePanel::GetPreviewTooltipText)
                        .OnClicked(this,&SAssetForgeGatePanel::HandlePreviewClicked)]
                    + SWrapBox::Slot()
                    [SNew(SButton).Tag(TEXT("Gate.Import")).ButtonStyle(FAppStyle::Get(),"PrimaryButton")
                        .Text(this, &SAssetForgeGatePanel::GetImportButtonText)
                        .IsEnabled(this,&SAssetForgeGatePanel::CanImportSelectedPackage)
                        .ToolTipText(this,&SAssetForgeGatePanel::GetImportTooltipText)
                        .OnClicked(this,&SAssetForgeGatePanel::HandleImportClicked)]
                    + SWrapBox::Slot()
                    [SNew(SButton).Tag(TEXT("Gate.Handoff")).ButtonStyle(FAppStyle::Get(),"PrimaryButton")
                        .IsEnabled(this,&SAssetForgeGatePanel::CanReviewSelectedImport)
                        .Text(LOCTEXT("ImportedReview", "前往「入库批审」查验本次资产 →"))
                        .Visibility_Lambda([this](){ return CanReviewSelectedImport() && !GetCompletedImportCounts()
                            ? EVisibility::Visible : EVisibility::Collapsed; })
                        .OnClicked(this,&SAssetForgeGatePanel::HandleImportedReviewClicked)]
                ]
                + SVerticalBox::Slot().AutoHeight().Padding(0,0,0,7)[BuildWriteConfirmation()]
                + SVerticalBox::Slot().AutoHeight().Padding(0,0,0,7)[BuildCompletedImport()]
                + SVerticalBox::Slot().AutoHeight()
                [
                    Section(LOCTEXT("PackageContentSection", "包体摘要"), SNew(SVerticalBox)
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("SelectedPackage", "选中包体"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetSelectedAssetName))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("Dcc", "来源 DCC"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetSelectedSourceDcc))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("TargetPath", "UE 目标路径"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetSelectedTargetPath))]
                        + SVerticalBox::Slot().AutoHeight()
                        [SNew(SBox).Visibility_Lambda([this](){ return HasDeclaredAssetBudgets() ? EVisibility::Visible : EVisibility::Collapsed; })
                            [PropertyRow(LOCTEXT("DeclaredAssetBudget", "包体预算"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetDeclaredAssetBudgets))]]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("Mesh", "网格"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetMeshSummary))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("Materials", "材质实例"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetMaterialSummary))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("Textures", "贴图"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetTextureSummary))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("Bindings", "材质 / 贴图映射"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetMaterialBindings))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("SelectedPackageState", "风险状态"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetSelectedPackageStateText))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("GateMessage", "操作结果"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetGateMessage))]
                        + SVerticalBox::Slot().AutoHeight()[BuildGateNotices()]
                    )
                ]
                + SVerticalBox::Slot().AutoHeight().Padding(0.0f, 8.0f, 0.0f, 0.0f)
                [
                    Section(
                        LOCTEXT("ImportStrategySection", "导入策略设置"),
                        SNew(SVerticalBox)
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("WriteContentSummary", "写入内容"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetWriteContentSummaryText))]
                        + SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Left).Padding(0,3)
                        [CompactButton(TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetDryRunButtonText), "Icons.Search", FOnClicked::CreateSP(this, &SAssetForgeGatePanel::HandleDryRunClicked), TAttribute<bool>::CreateSP(this, &SAssetForgeGatePanel::HasSelectedPackage), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetDryRunTooltipText))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("ImportCombineMeshes", "Combine Meshes"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetCombineMeshesText))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("ImportNormalMethod", "法线导入"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetNormalImportText))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("ImportLodPolicy", "LOD 策略"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetLodPolicyText))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("ImportNanitePolicy", "Nanite"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetNanitePolicyText))]
                        + SVerticalBox::Slot().AutoHeight().Padding(0.0f, 8.0f, 0.0f, 0.0f)
                        [
                            PropertyRow(LOCTEXT("GateBasicImportGroup", "基础导入"), BuildBasicImportSummaryRow())
                        ]
                        + SVerticalBox::Slot().AutoHeight()
                        [
                            PropertyRow(LOCTEXT("GateContentImportGroup", "材质贴图"), BuildContentImportOptionRow())
                        ]
                        + SVerticalBox::Slot().AutoHeight()
                        [
                            FullWidthPolicyRow(LOCTEXT("GateTransformGroup", "高级设置：变换 / 单位"), BuildTransformOptionRow())
                        ]
                        + SVerticalBox::Slot().AutoHeight()
                        [
                            FullWidthPolicyRow(LOCTEXT("GateTransformOffsetGroup", "导入偏移"), BuildTransformOffsetOptionRow())
                        ]
                        + SVerticalBox::Slot().AutoHeight().Padding(0.0f, 8.0f, 0.0f, 0.0f)
                        [
                            PropertyRow(LOCTEXT("GateNormalImportMode", "法线 / 生成"), BuildNormalOptionRow())
                        ]
                        + SVerticalBox::Slot().AutoHeight()
                        [
                            PropertyRow(LOCTEXT("GateLodGroup", "网格 LODGroup"), BuildLodGroupCombo())
                        ]
                        + SVerticalBox::Slot().AutoHeight()
                        [
                            PropertyRow(LOCTEXT("GateVertexColor", "顶点色导入"), BuildVertexColorCombo())
                        ]
                        + SVerticalBox::Slot().AutoHeight()
                        [
                            SNew(SBox)
                            .Visibility(TAttribute<EVisibility>::CreateSP(this, &SAssetForgeGatePanel::GetVertexOverrideColorVisibility))
                            [
                                PropertyRow(LOCTEXT("GateVertexOverrideColor", "覆盖色"), BuildVertexOverrideColorRow())
                            ]
                        ]
                        + SVerticalBox::Slot().AutoHeight().Padding(0.0f, 8.0f, 0.0f, 0.0f)
                        [
                            PropertyRow(LOCTEXT("GateMeshBuildGroup", "网格构建"), BuildMeshBuildOptionRow())
                        ]
                        + SVerticalBox::Slot().AutoHeight()
                        [
                            PropertyRow(LOCTEXT("GateMeshQualityGroup", "网格质量"), BuildMeshQualityOptionRow())
                        ]
                        + SVerticalBox::Slot().AutoHeight()
                        [
                            PropertyRow(LOCTEXT("GateOutputBuildGroup", "高级设置：构建输出"), BuildOutputBuildOptionRow())
                        ],
                        true, TEXT("Gate.Fold.Policy")
                    )
                ]
                + SVerticalBox::Slot().AutoHeight()
                [
                    Section(
                        LOCTEXT("PackageSourceRecord", "来源记录"),
                        SNew(SVerticalBox)
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("PackageUpdatedAt", "包体时间"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetPackageTimeText))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("ReportUpdatedAt", "报告时间"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetReportTimeText))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("ManifestPath", "Manifest"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetManifestPath))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("PackageNote", "备注"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetPackageNoteText))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("PackageNaming", "包体/版本"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetSelectedPackageNamingText))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("ProjectPreset", "项目预设"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetSelectedProjectPresetText))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("Schema", "Schema"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetSchemaSummary))],
                        true
                    )
                ]
                + SVerticalBox::Slot().AutoHeight().Padding(0.0f, 8.0f, 0.0f, 0.0f)
                [
                    Section(
                        LOCTEXT("HistorySection", "历史与报告"),
                        SNew(SVerticalBox)
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("ToolVersion", "工具版本"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetToolVersionText))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("LastRefresh", "最近刷新"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetLastRefreshText))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("ImportHistory", "最近导入"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetHistorySummary))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("ReportState", "报告状态"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetReportStateText))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("ReportPermission", "导入许可"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetReportPermissionText))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("ReportRisk", "风险计数"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetReportRiskText))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("ReportPath", "报告路径"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetReportPath))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("DebugExportPath", "调试导出"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetDebugExportPathText))]
                        + SVerticalBox::Slot().AutoHeight().Padding(0.0f, 8.0f, 0.0f, 0.0f)
                        [
                            SNew(SHorizontalBox)
                            + SHorizontalBox::Slot().FillWidth(1.0f)
                            [
                                CompactButton(
                                    TAttribute<FText>(LOCTEXT("LocateReport", "定位完整报告")),
                                    "Icons.Visibility",
                                    FOnClicked::CreateSP(this, &SAssetForgeGatePanel::HandleOpenReportClicked),
                                    TAttribute<bool>::CreateSP(this, &SAssetForgeGatePanel::HasSelectedReport),
                                    TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetOpenReportTooltipText)
                                )
                            ]
                            + SHorizontalBox::Slot().FillWidth(1.0f).Padding(6.0f, 0.0f, 0.0f, 0.0f)
                            [
                                CompactButton(
                                    TAttribute<FText>(LOCTEXT("ExportDebugInfo", "导出调试信息")),
                                    "Icons.Save",
                                    FOnClicked::CreateSP(this, &SAssetForgeGatePanel::HandleExportDebugClicked),
                                    TAttribute<bool>(true),
                                    TAttribute<FText>(LOCTEXT("ExportDebugTooltip", "保存当前 Gate 状态、包体列表、选中包体和报告路径，便于交给 TA 或 AI 排查。"))
                                )
                            ]
                        ], true
                    )
                ]
            ];
    }

    FText GetImportButtonText() const
    {
        if (GateOperation == EGateOperation::AwaitConfirm)
        {
            return LOCTEXT("GateWaitingForConfirm", "等待确认…");
        }
        if (GateOperation == EGateOperation::Import)
        {
            return LOCTEXT("ImportingPackage", "正在导入资产…");
        }
        if (GateOperation == EGateOperation::PrepareWrite)
        {
            return LOCTEXT("PreparingGateWrite", "正在核对目标…");
        }
        return LOCTEXT("ConfirmImport", "确认导入");
    }

    FText GetWriteCounts() const
    {
        return FText::Format(LOCTEXT("GateConfirmCounts", "网格 {0} · 贴图 {1} · 材质实例 {2}"),
            FText::AsNumber(JsonIntField(WriteSummary, TEXT("mesh_count"))),
            FText::AsNumber(JsonIntField(WriteSummary, TEXT("texture_count"))),
            FText::AsNumber(JsonIntField(WriteSummary, TEXT("material_count"))));
    }

    FText GetWriteTarget() const
    {
        FString Target;
        if (WriteSummary)
        {
            WriteSummary->TryGetStringField(TEXT("target_path"), Target);
        }
        return FText::FromString(Target);
    }

    FText GetWriteConflicts() const
    {
        FString Policy;
        if (WriteSummary)
        {
            WriteSummary->TryGetStringField(TEXT("policy_summary"), Policy);
        }
        return FText::Format(LOCTEXT("GateConfirmTargetAssets", "目标现有 {0} 项资产　{1}"),
            FText::AsNumber(JsonIntField(WriteSummary, TEXT("existing_count"))), FText::FromString(Policy));
    }

    FText GetWriteRisk() const
    {
        return FText::Format(LOCTEXT("GateConfirmRisk", "{0} 阻断 · {1} 项非阻断提醒"),
            FText::AsNumber(JsonIntField(WriteSummary, TEXT("error_count"))),
            FText::AsNumber(JsonIntField(WriteSummary, TEXT("warning_count"))));
    }

    TSharedRef<SWidget> BuildWriteConfirmation()
    {
        const auto Target = TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetWriteTarget);
        return SNew(SBorder).Tag(TEXT("Gate.ConfirmPanel"))
            .Visibility_Lambda([this](){ return GateOperation == EGateOperation::AwaitConfirm
                && WriteSummary.IsValid() ? EVisibility::Visible : EVisibility::Collapsed; })
            .BorderImage(FAppStyle::GetBrush("ToolPanel.GroupBorder")).Padding(FMargin(12,9))
            [SNew(SVerticalBox)
                + SVerticalBox::Slot().AutoHeight()
                [SNew(STextBlock).Text(LOCTEXT("GateInlineConfirmTitle", "核对本次写入")).Font(StrongFont())]
                + SVerticalBox::Slot().AutoHeight().Padding(0,5,0,2)
                [WrappedTextBlock(TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetWriteCounts))]
                + SVerticalBox::Slot().AutoHeight().Padding(0,2)
                [SNew(STextBlock).Text(Target).ToolTipText(Target).Font(DetailFont()).OverflowPolicy(ETextOverflowPolicy::Ellipsis)
                    .Clipping(EWidgetClipping::ClipToBounds)]
                + SVerticalBox::Slot().AutoHeight().Padding(0,2)
                [WrappedTextBlock(TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetWriteConflicts))]
                + SVerticalBox::Slot().AutoHeight().Padding(0,2,0,6)
                [WrappedTextBlock(TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetWriteRisk))]
                + SVerticalBox::Slot().AutoHeight()
                [SNew(SWrapBox).UseAllottedSize(true).InnerSlotPadding(FVector2D(6,4))
                    + SWrapBox::Slot()
                    [SNew(SButton).Tag(TEXT("Gate.ConfirmWrite")).ButtonStyle(FAppStyle::Get(),"PrimaryButton")
                        .Text(LOCTEXT("GateConfirmWrite", "确认写入"))
                        .OnClicked(this, &SAssetForgeGatePanel::HandleConfirmWriteClicked)]
                    + SWrapBox::Slot()
                    [SNew(SButton).Tag(TEXT("Gate.CancelWrite")).Text(LOCTEXT("GateCancelWrite", "取消"))
                        .OnClicked(this, &SAssetForgeGatePanel::HandleCancelWriteClicked)]]];
    }

    bool HasDeclaredAssetBudgets() const
    {
        return SelectedPackage && SelectedPackage->TriangleBudget > 0 && SelectedPackage->MaterialSlotBudget > 0;
    }

    FText GetDeclaredAssetBudgets() const
    {
        return HasDeclaredAssetBudgets()
            ? FText::Format(LOCTEXT("DeclaredAssetBudgetValues", "{0} 三角面 / {1} 个材质槽"),
                FText::AsNumber(SelectedPackage->TriangleBudget), FText::AsNumber(SelectedPackage->MaterialSlotBudget))
            : FText::GetEmpty();
    }

    TSharedPtr<FJsonObject> GetCompletedImportCounts() const
    {
        return CanReviewSelectedImport() ? JsonObjectField(SelectedPackage->HandoffReceipt, TEXT("result_counts")) : nullptr;
    }

    TSharedRef<SWidget> BuildCompletedImport()
    {
        return SNew(SBorder).Tag(TEXT("Gate.ImportReceipt"))
            .Visibility_Lambda([this](){ return GetCompletedImportCounts() ? EVisibility::Visible : EVisibility::Collapsed; })
            .BorderImage(FAppStyle::GetBrush("ToolPanel.GroupBorder")).Padding(FMargin(12,9))
            [SNew(SVerticalBox)
                + SVerticalBox::Slot().AutoHeight()
                [SNew(STextBlock).Text(LOCTEXT("GateImportCompleted", "✓ 导入完成")).Font(StrongFont()).ColorAndOpacity(FStyleColors::Success)]
                + SVerticalBox::Slot().AutoHeight().Padding(0,5,0,2)
                [WrappedTextBlock(TAttribute<FText>::CreateLambda([this]()
                {
                    const auto Counts = GetCompletedImportCounts();
                    return FText::Format(LOCTEXT("GateImportedCounts", "网格 {0} · 贴图 {1} · 材质实例 {2}"),
                        FText::AsNumber(JsonIntField(Counts, TEXT("mesh_count"))),
                        FText::AsNumber(JsonIntField(Counts, TEXT("texture_count"))),
                        FText::AsNumber(JsonIntField(Counts, TEXT("material_count"))));
                }))]
                + SVerticalBox::Slot().AutoHeight().Padding(0,2,0,6)
                [WrappedTextBlock(TAttribute<FText>::CreateLambda([this]()
                {
                    FString Target;
                    if (SelectedPackage && SelectedPackage->HandoffReceipt)
                    {
                        SelectedPackage->HandoffReceipt->TryGetStringField(TEXT("target_path"), Target);
                    }
                    return FText::FromString(Target);
                }))]
                + SVerticalBox::Slot().AutoHeight()
                [SNew(SWrapBox).UseAllottedSize(true).InnerSlotPadding(FVector2D(6,4))
                    + SWrapBox::Slot()
                    [SNew(SButton).Tag(TEXT("Gate.ReceiptHandoff")).ButtonStyle(FAppStyle::Get(),"PrimaryButton")
                        .Text(LOCTEXT("ImportedReview", "前往「入库批审」查验本次资产 →"))
                        .OnClicked(this, &SAssetForgeGatePanel::HandleImportedReviewClicked)]
                    + SWrapBox::Slot()
                    [SNew(SButton).Tag(TEXT("Gate.OpenImportedMesh"))
                        .Text(LOCTEXT("GateOpenImportedMesh", "打开静态网格"))
                        .OnClicked(this, &SAssetForgeGatePanel::HandleOpenImportedMeshClicked)]]];
    }

    TArray<FString> const& GetGateNotices(bool bErrors) const
    {
        static const TArray<FString> Empty;
        if (!SelectedPackage)
        {
            return Empty;
        }
        return bErrors ? SelectedPackage->OperatorErrors : SelectedPackage->OperatorWarnings;
    }

    TSharedRef<SWidget> GateNoticeText(const FText& Label, bool bErrors)
    {
        return SNew(SVerticalBox)
            .Visibility_Lambda([this, bErrors](){ return GetGateNotices(bErrors).IsEmpty() ? EVisibility::Collapsed : EVisibility::Visible; })
            + SVerticalBox::Slot().AutoHeight().Padding(0,4,0,2)
            [TextBlock(Label, bErrors ? FStyleColors::Error : FStyleColors::Warning)]
            + SVerticalBox::Slot().AutoHeight()
            [WrappedTextBlock(TAttribute<FText>::CreateLambda([this, bErrors]()
            {
                const auto& Notices = GetGateNotices(bErrors);
                return Notices.IsEmpty() ? FText::GetEmpty()
                    : FText::FromString(TEXT("• ") + FString::Join(Notices, TEXT("\n• ")));
            }))];
    }

    TSharedRef<SWidget> BuildGateNotices()
    {
        return SNew(SVerticalBox).Tag(TEXT("Gate.CheckNotices"))
            .Visibility_Lambda([this](){ return HasSelectedReport() ? EVisibility::Visible : EVisibility::Collapsed; })
            + SVerticalBox::Slot().AutoHeight().Padding(8,0)
            [GateNoticeText(LOCTEXT("GateBlockingNotices", "需修复"), true)]
            + SVerticalBox::Slot().AutoHeight().Padding(8,0)
            [GateNoticeText(LOCTEXT("GateReviewNotices", "非阻断提醒"), false)]
            + SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Left).Padding(8,5,0,5)
            [SNew(SButton).Tag(TEXT("Gate.FullReport")).ButtonStyle(FAppStyle::Get(),"SimpleButton")
                .IsEnabled_Lambda([this](){ return HasSelectedReport(); })
                .Text(LOCTEXT("LocateReport", "定位完整报告"))
                .ToolTipText(this, &SAssetForgeGatePanel::GetOpenReportTooltipText)
                .OnClicked(this, &SAssetForgeGatePanel::HandleOpenReportClicked)];
    }

    TSharedRef<SWidget> FullWidthPolicyRow(const FText& Label, const TSharedRef<SWidget>& Control)
    {
        return SNew(SBorder).BorderImage(FAppStyle::GetBrush("DetailsView.GridLine")).Padding(FMargin(8,5))
            [SNew(SVerticalBox)
                + SVerticalBox::Slot().AutoHeight().Padding(0,0,0,4)[TextBlock(Label,FSlateColor::UseSubduedForeground())]
                + SVerticalBox::Slot().AutoHeight()[Control]];
    }

    TSharedRef<ITableRow> MakePackageRow(TSharedPtr<FAssetForgePackageItem> Item, const TSharedRef<STableViewBase>& OwnerTable)
    {
        const FText AssetName = Item.IsValid() ? FText::FromString(Item->AssetName) : FText::GetEmpty();
        const FText PackageMeta = Item.IsValid() ? FText::FromString(Item->ListCompactMetaLabel()) : FText::GetEmpty();
        const TAttribute<bool> bSelected = TAttribute<bool>::CreateLambda([this, Item]()
        {
            if (!Item.IsValid())
            {
                return false;
            }
            if (PackageListView.IsValid() && PackageListView->IsItemSelected(Item))
            {
                return true;
            }
            return SelectedPackage.IsValid() && SelectedPackage->PackageDir == Item->PackageDir;
        });
        return SNew(STableRow<TSharedPtr<FAssetForgePackageItem>>, OwnerTable)
            .Padding(FMargin(4.0f, 4.0f))
            [
                SNew(SBorder)
                .BorderImage(FAppStyle::GetBrush("ToolPanel.GroupBorder"))
                .Padding(FMargin(8.0f, 7.0f))
                [
                    SNew(SVerticalBox)
                    + SVerticalBox::Slot().AutoHeight()
                    [
                        SNew(SHorizontalBox)
                        + SHorizontalBox::Slot()
                        .AutoWidth()
                        .VAlign(VAlign_Center)
                        [
                            SNew(SBox)
                            .WidthOverride(18.0f)
                            [
                                SelectionDot(bSelected)
                            ]
                        ]
                        + SHorizontalBox::Slot()
                        .FillWidth(1.0f)
                        .VAlign(VAlign_Center)
                        [
                            SNew(SButton).Tag(FName(*(TEXT("Gate.Package.") + Item->PackageDir)))
                            .ButtonStyle(FAppStyle::Get(), "SimpleButton")
                            .ContentPadding(FMargin(0.0f))
                            .ToolTipText(FText::Format(LOCTEXT("SelectPackageDetails", "{0}\n{1}\n选择包体；右侧会显示来源记录、包内资产和导入策略"), AssetName, PackageMeta))
                            .OnClicked(this, &SAssetForgeGatePanel::HandlePackageRowSelect, Item)
                            [
                                SNew(SVerticalBox)
                                + SVerticalBox::Slot().AutoHeight()
                                [
                                    SNew(STextBlock).Text(AssetName)
                                    .TextStyle(FAppStyle::Get(), "NormalText")
                                    .OverflowPolicy(ETextOverflowPolicy::Ellipsis)
                                    .Clipping(EWidgetClipping::ClipToBounds)
                                ]
                                + SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Left).Padding(0,2,0,0)
                                [
                                    StatusPill(
                                        TAttribute<FText>(FText::FromString(Item->StatePrefix().Replace(TEXT("["), TEXT("")).Replace(TEXT("]"), TEXT("")))),
                                        PackageRiskColor(*Item)
                                    )
                                ]
                                + SVerticalBox::Slot().AutoHeight().Padding(0.0f, 2.0f, 0.0f, 0.0f)
                                [
                                    SNew(STextBlock).Text(PackageMeta).Font(DetailFont())
                                    .ColorAndOpacity(FSlateColor::UseSubduedForeground())
                                    .OverflowPolicy(ETextOverflowPolicy::Ellipsis)
                                    .Clipping(EWidgetClipping::ClipToBounds)
                                ]
                            ]
                        ]
                    ]
                ]
            ];
    }

    void OnPackageSelected(TSharedPtr<FAssetForgePackageItem> Item, ESelectInfo::Type SelectInfo)
    {
        SelectedPackage = Item;
        LoadSelectedReportDetails();
        if (PackageListView.IsValid())
        {
            PackageListView->RequestListRefresh();
        }
        GateMessage = CanReviewSelectedImport()
            ? FString(ImportedSelectionMessage)
            : (Item.IsValid()
                ? FString::Printf(TEXT("已选择 %s。右侧已显示来源记录、包内资产和导入策略；下一步建议先检查。"), *Item->AssetName)
                : TEXT("请先在左侧选择一个 AF 包体。"));
    }

    FReply HandlePackageRowSelect(TSharedPtr<FAssetForgePackageItem> Item)
    {
        if (!Item.IsValid())
        {
            return FReply::Handled();
        }
        OnPackageSelected(Item, ESelectInfo::OnMouseClick);
        if (PackageListView.IsValid())
        {
            PackageListView->SetSelection(Item);
        }
        return FReply::Handled();
    }

    void LoadSelectedReportDetails(bool bRevalidate = false)
    {
        if (!HasSelectedPackage() || !HasSelectedReport() || (!bRevalidate && SelectedPackage->bReportViewLoaded))
        {
            return;
        }
        FAssetForgePackageItem& Item = *SelectedPackage;
        FString Error;
        const auto Result = ExecuteGatePythonCommand(TEXT("workbench_read_reports"), Item.PackageDir,
            TEXT("{}"), FString(), Error, Item.ImportReportPath);
        Item.bReportViewLoaded = Result.IsValid();
        if (Result)
        {
            AttachOperatorNotices(Item, Result);
            AttachHandoffReceipt(Item, Result);
        }
        else if (bRevalidate)
        {
            Item.HandoffReceipt.Reset();
        }
    }

    FReply HandleRefreshClicked()
    {
        RefreshPackages();
        if (PackageListView.IsValid())
        {
            PackageListView->RequestListRefresh();
            if (SelectedPackage.IsValid())
            {
                PackageListView->SetSelection(SelectedPackage);
            }
        }
        return FReply::Handled();
    }

    FReply HandleChoosePackageRootClicked()
    {
        IDesktopPlatform* DesktopPlatform = FDesktopPlatformModule::Get();
        if (!DesktopPlatform)
        {
            GateMessage = TEXT("无法打开目录选择器；请确认 DesktopPlatform 模块可用。");
            return FReply::Handled();
        }

        FString SelectedDirectory;
        const FString DefaultPath = !ManualPackageRoot.IsEmpty()
            ? ManualPackageRoot
            : (ScanRoots.Num() > 0 ? ScanRoots[0] : FPaths::ProjectDir());
        const bool bPicked = DesktopPlatform->OpenDirectoryDialog(
            nullptr,
            TEXT("选择 DCC AssetForge Package 导出目录"),
            DefaultPath,
            SelectedDirectory
        );
        if (!bPicked || SelectedDirectory.IsEmpty())
        {
            GateMessage = TEXT("未更改包体目录。");
            return FReply::Handled();
        }

        ManualPackageRoot = FPaths::ConvertRelativePathToFull(SelectedDirectory);
        FPaths::NormalizeDirectoryName(ManualPackageRoot);
        bScanManualRootOnly = false;
        RefreshPackages();
        if (PackageListView.IsValid())
        {
            PackageListView->RequestListRefresh();
        }
        GateMessage = FString::Printf(TEXT("已选择包体目录：%s。历史包体会保留；默认会同时显示自动扫描结果和已选目录。如只想看这个目录，勾选“只看已选目录”。"), *ManualPackageRoot);
        return FReply::Handled();
    }

    FReply HandleClearListClicked()
    {
        Packages.Reset();
        FilteredPackages.Reset();
        History.Reset();
        SelectedPackage.Reset();
        if (PackageListView.IsValid())
        {
            PackageListView->ClearSelection();
            PackageListView->RequestListRefresh();
        }
        GateMessage = TEXT("已清理当前 Gate 导入历史列表；这不会删除磁盘 Package 或 UE 资产。点击“刷新列表”可重新扫描。");
        return FReply::Handled();
    }

    void HandleSearchChanged(const FText& NewText)
    {
        SearchText = NewText.ToString();
        ApplyPackageFilter();
        if (PackageListView.IsValid())
        {
            PackageListView->RequestListRefresh();
            TSharedPtr<FAssetForgePackageItem> MatchedSelection = FindFilteredPackageByDir(SelectedPackage.IsValid() ? SelectedPackage->PackageDir : FString());
            if (MatchedSelection.IsValid())
            {
                SelectedPackage = MatchedSelection;
                PackageListView->SetSelection(SelectedPackage);
            }
            else if (FilteredPackages.Num() > 0)
            {
                SelectedPackage.Reset();
                PackageListView->ClearSelection();
                GateMessage = TEXT("当前搜索结果不包含原选中包体；请在左侧明确选择要检查或导入的包体。");
            }
            else
            {
                SelectedPackage.Reset();
                PackageListView->ClearSelection();
                GateMessage = Packages.Num() > 0
                    ? TEXT("当前筛选没有匹配包体；清空搜索词可回到完整列表。")
                    : TEXT("还没有发现 AF 包体，请先刷新扫描。");
            }
        }
    }

    FReply HandlePreviewClicked()
    {
        if (!HasSelectedPackage())
        {
            GateMessage = TEXT("未选择包体，无法检查。请先在左侧包体列表选中一项。");
            return FReply::Handled();
        }
        return QueueGateOperation(EGateOperation::Check);
    }

    FReply HandleDryRunClicked()
    {
        return HasSelectedPackage() ? QueueGateOperation(EGateOperation::DryRun) : FReply::Handled();
    }

    FReply HandleImportClicked()
    {
        if (!CanImportSelectedPackage())
        {
            GateMessage = TEXT("当前包体未放行，未写入 UE。请先执行检查。");
            return FReply::Handled();
        }
        return QueueGateOperation(EGateOperation::PrepareWrite);
    }

    FReply HandleConfirmWriteClicked()
    {
        if (GateOperation != EGateOperation::AwaitConfirm || !WriteSummary.IsValid() || !SelectedPackage.IsValid())
        {
            return FReply::Handled();
        }
        return QueueGateOperation(EGateOperation::Import);
    }

    FReply HandleCancelWriteClicked()
    {
        WriteSummary.Reset();
        ConfirmedOptions.Reset();
        GateOperation = EGateOperation::Idle;
        GateMessage = TEXT("已取消确认，本次未写入 UE。");
        return FReply::Handled();
    }

    FReply QueueGateOperation(EGateOperation Operation)
    {
        const bool bImport = Operation == EGateOperation::Import;
        const bool bPrepare = Operation == EGateOperation::PrepareWrite;
        const FString PackageDir = SelectedPackage->PackageDir;
        const FString Options = bImport ? ConfirmedOptions : BuildGateImportOptionsJson();
        FString Token;
        if (bImport)
        {
            WriteSummary->TryGetStringField(TEXT("token"), Token);
            SelectedPackage->HandoffReceipt.Reset();
            SelectedPackage->bReportViewLoaded = false;
            SelectedPackage->bImported = false;
        }
        const TCHAR* FunctionName = bImport ? TEXT("workbench_apply_package")
            : bPrepare ? TEXT("workbench_prepare_package")
            : Operation == EGateOperation::DryRun ? TEXT("workbench_dry_run_package") : TEXT("workbench_check_package");
        GateOperation = Operation;
        GateMessage = bImport ? TEXT("正在导入资产…")
            : bPrepare ? TEXT("正在核对目标…")
            : Operation == EGateOperation::DryRun ? TEXT("正在验证，不写入资产…") : TEXT("正在检查包体…");
        const double ClickStart = FPlatformTime::Seconds();

        // Let Slate render the new operation state before running editor-thread Python.
        RegisterActiveTimer(0.12f, FWidgetActiveTimerDelegate::CreateLambda(
            [this, bImport, bPrepare, PackageDir, Options, Token, FunctionName, ClickStart](double, float)
            {
                const double RpcStart = FPlatformTime::Seconds();
                FString Message;
                const auto Result = ExecuteGatePythonCommand(FunctionName, PackageDir, Options, Token, Message);
                const double RpcEnd = FPlatformTime::Seconds();
                WriteSummary.Reset();
                ConfirmedOptions.Reset();
                GateOperation = EGateOperation::Idle;
                if (Result)
                {
                    Result->TryGetStringField(TEXT("message"), Message);
                    if (bPrepare)
                    {
                        bool bCacheHit = false;
                        if (!Result->TryGetBoolField(TEXT("cache_hit"), bCacheHit) || !bCacheHit)
                        {
                            RefreshSelectedPackageReport(PackageDir, Result);
                        }
                        const auto Confirmation = JsonObjectField(Result, TEXT("confirmation"));
                        FString ReadyToken;
                        bool bCanImport = false;
                        if (Confirmation && Confirmation->TryGetStringField(TEXT("token"), ReadyToken) && !ReadyToken.IsEmpty()
                            && Result->TryGetBoolField(TEXT("can_import"), bCanImport) && bCanImport
                            && JsonIntField(Confirmation, TEXT("error_count"), INDEX_NONE) == 0)
                        {
                            WriteSummary = Confirmation;
                            ConfirmedOptions = Options;
                            GateOperation = EGateOperation::AwaitConfirm;
                        }
                    }
                    else
                    {
                        RefreshSelectedPackageReport(PackageDir, Result);
                        bool bImported = false;
                        if (bImport && Result->TryGetBoolField(TEXT("import_succeeded"), bImported) && bImported && Message.IsEmpty())
                        {
                            Message = TEXT("导入完成。");
                        }
                    }
                    if (Message.IsEmpty())
                    {
                        bool bPassed = false;
                        Result->TryGetBoolField(TEXT("can_import"), bPassed);
                        if (!bPassed)
                        {
                            Message = TEXT("当前未获放行，请查看下方原因。");
                        }
                        else if (GateOperation == EGateOperation::AwaitConfirm)
                        {
                            Message = TEXT("已核对目标，等待确认写入。");
                        }
                        else
                        {
                            Message = TEXT("检查完成，当前包体可以导入。");
                        }
                    }
                }
                GateMessage = MoveTemp(Message);
                FString PhaseTimings;
                if (const auto Timing = JsonObjectField(Result, TEXT("timings_ms")))
                {
                    FJsonSerializer::Serialize(Timing.ToSharedRef(), TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&PhaseTimings));
                }
                const double Ready = FPlatformTime::Seconds();
                UE_LOG(LogAssetForgeEditor, Display, TEXT("AssetForgeGateTiming action=%s rpc_ms=%.1f selected_update_ms=%.1f total_ms=%.1f python_ms=%s"),
                    FunctionName, (RpcEnd - RpcStart) * 1000.0, (Ready - RpcEnd) * 1000.0,
                    (Ready - ClickStart) * 1000.0, *PhaseTimings);
                return EActiveTimerReturnType::Stop;
            }));
        return FReply::Handled();
    }

    void RefreshSelectedPackageReport(const FString& PackageDir, const TSharedPtr<FJsonObject>& Result)
    {
        if (!SelectedPackage || SelectedPackage->PackageDir != PackageDir)
        {
            return;
        }
        if (const auto Fresh = BuildPackageItemFromManifest(SelectedPackage->ManifestPath))
        {
            if (Fresh->ModifiedTime == SelectedPackage->ModifiedTime)
            {
                Fresh->HandoffReceipt = SelectedPackage->HandoffReceipt;
                Fresh->bReportViewLoaded = SelectedPackage->bReportViewLoaded;
            }
            *SelectedPackage = MoveTemp(*Fresh);
        }
        if (Result->HasField(TEXT("handoff_receipt")))
        {
            AttachHandoffReceipt(*SelectedPackage, Result);
            SelectedPackage->bReportViewLoaded = true;
        }
        else if (SelectedPackage->HandoffReceipt)
        {
            SelectedPackage->bImported = true;
        }
        bool bCanImport = false;
        if (Result->TryGetBoolField(TEXT("can_import"), bCanImport))
        {
            SelectedPackage->bReportCanImportKnown = true;
            SelectedPackage->bReportCanImport = bCanImport;
        }
        bool bImportSucceeded = false;
        if (Result->TryGetBoolField(TEXT("import_succeeded"), bImportSucceeded) && bImportSucceeded)
        {
            SelectedPackage->bImported = true;
        }
        AttachOperatorNotices(*SelectedPackage, Result);
        if (PackageListView)
        {
            PackageListView->RebuildList();
        }
    }

    bool CanReviewSelectedImport() const
    {
        return CanImportSelectedPackage() && SelectedPackage->bImported && SelectedPackage->HandoffReceipt.IsValid();
    }

    FReply HandleImportedReviewClicked()
    {
        if (!CanReviewSelectedImport())
        {
            return FReply::Handled();
        }
        LoadSelectedReportDetails(true);
        if (!CanReviewSelectedImport())
        {
            GateMessage = TEXT("无法核实本次导入记录，请刷新列表，或在入库批审中手动选择资产。");
            return FReply::Handled();
        }
        FString ReceiptJson;
        if (FJsonSerializer::Serialize(SelectedPackage->HandoffReceipt.ToSharedRef(), TJsonWriterFactory<>::Create(&ReceiptJson)))
        {
            AssetForgeReview::OpenImported(ReceiptJson);
        }
        return FReply::Handled();
    }

    FReply HandleOpenImportedMeshClicked()
    {
        if (!CanReviewSelectedImport())
        {
            return FReply::Handled();
        }
        TArray<FString> OriginalPaths;
        SelectedPackage->HandoffReceipt->TryGetStringArrayField(TEXT("meshes"), OriginalPaths);
        LoadSelectedReportDetails(true);
        TArray<FString> Paths;
        if (!CanReviewSelectedImport()
            || !SelectedPackage->HandoffReceipt->TryGetStringArrayField(TEXT("meshes"), Paths)
            || Paths.IsEmpty() || Paths != OriginalPaths)
        {
            GateMessage = TEXT("本次导入的网格记录已变化，请刷新后重新核对。");
            return FReply::Handled();
        }

        TArray<UObject*> Assets;
        for (const FString& Path : Paths)
        {
            UStaticMesh* Mesh = Cast<UStaticMesh>(FSoftObjectPath(Path).TryLoad());
            if (!Mesh || !Mesh->GetPathName().Equals(Path, ESearchCase::IgnoreCase))
            {
                GateMessage = TEXT("无法打开本次静态网格，请在内容浏览器核对导入目标。");
                return FReply::Handled();
            }
            Assets.Add(Mesh);
        }
        UAssetEditorSubsystem* AssetEditor = GEditor ? GEditor->GetEditorSubsystem<UAssetEditorSubsystem>() : nullptr;
        GateMessage = AssetEditor && AssetEditor->OpenEditorForAssets(Assets)
            ? TEXT("已打开本次导入的静态网格。")
            : TEXT("无法打开静态网格编辑器，请在内容浏览器核对导入目标。");
        return FReply::Handled();
    }

    FReply HandleOpenReportClicked()
    {
        if (!SelectedPackage.IsValid() || SelectedPackage->ImportReportPath.IsEmpty())
        {
            GateMessage = TEXT("当前包体还没有可打开的报告；请先执行检查。");
            return FReply::Handled();
        }
        const FString ReportFile = FPaths::ConvertRelativePathToFull(SelectedPackage->ImportReportPath);
        if (!FPaths::FileExists(ReportFile))
        {
            GateMessage = TEXT("报告文件已移走或删除，请重新检查包体生成报告。");
            return FReply::Handled();
        }
        FPlatformProcess::ExploreFolder(*ReportFile);
        return FReply::Handled();
    }

    FReply HandleExportDebugClicked()
    {
        const FString DebugDir = FPaths::ProjectSavedDir() / TEXT("AssetForge/GateDebug");
        IFileManager::Get().MakeDirectory(*DebugDir, true);
        const FString DebugPath = DebugDir / FString::Printf(TEXT("AssetForgeGateDebug_%s.txt"), *FDateTime::Now().ToString(TEXT("%Y%m%d_%H%M%S")));
        if (FFileHelper::SaveStringToFile(BuildDebugExportText(), *DebugPath))
        {
            LastDebugExportPath = DebugPath;
            GateMessage = FString::Printf(TEXT("调试信息已导出：%s"), *DebugPath);
        }
        else
        {
            GateMessage = FString::Printf(TEXT("调试信息导出失败：%s"), *DebugPath);
        }
        return FReply::Handled();
    }

    FString BuildDebugExportText() const
    {
        TArray<FString> Lines;
        Lines.Add(FString(GateVersionLabel));
        Lines.Add(FString::Printf(TEXT("generated_at: %s"), *FDateTime::Now().ToString(TEXT("%Y-%m-%d %H:%M:%S"))));
        Lines.Add(FString::Printf(TEXT("last_refresh: %s"), *GetLastRefreshText().ToString()));
        Lines.Add(FString::Printf(TEXT("status: %s"), *GetStatusText().ToString()));
        Lines.Add(FString::Printf(TEXT("gate_message: %s"), *GateMessage));
        Lines.Add(FString::Printf(TEXT("visible_packages: %d / %d"), FilteredPackages.Num(), Packages.Num()));
        Lines.Add(FString::Printf(TEXT("package_counts: %s"), *PackageCountsLabel()));
        Lines.Add(FString::Printf(TEXT("selected_package_dir: %s"), SelectedPackage.IsValid() ? *SelectedPackage->PackageDir : TEXT("未选择")));
        Lines.Add(TEXT(""));
        Lines.Add(TEXT("[scan_roots]"));
        Lines.Add(ScanRoots.Num() > 0 ? FString::Join(ScanRoots, TEXT("\n")) : TEXT("未发现扫描目录"));
        Lines.Add(TEXT(""));
        Lines.Add(TEXT("[selected_package]"));
        if (SelectedPackage.IsValid())
        {
            Lines.Add(FString::Printf(TEXT("asset_name: %s"), *SelectedPackage->AssetName));
            Lines.Add(FString::Printf(TEXT("source_dcc: %s"), *SelectedPackage->SourceDcc));
            Lines.Add(FString::Printf(TEXT("target_path: %s"), *SelectedPackage->TargetPath));
            Lines.Add(FString::Printf(TEXT("package_naming: %s"), *SelectedPackage->PackageIdentityLine()));
            Lines.Add(FString::Printf(TEXT("project_preset: %s"), *SelectedPackage->ProjectPresetLine()));
            Lines.Add(FString::Printf(TEXT("package_dir: %s"), *SelectedPackage->PackageDir));
            Lines.Add(FString::Printf(TEXT("manifest: %s"), *SelectedPackage->ManifestPath));
            Lines.Add(FString::Printf(TEXT("report: %s"), *SelectedPackage->ImportReportPath));
            Lines.Add(FString::Printf(TEXT("state: %s"), *SelectedPackage->StatePrefix()));
            Lines.Add(FString::Printf(TEXT("risk: %s"), *SelectedPackage->RiskSummary()));
            Lines.Add(FString::Printf(TEXT("next_action: %s"), *SelectedPackage->ReportNextAction));
        }
        else
        {
            Lines.Add(TEXT("未选择包体"));
        }
        Lines.Add(TEXT(""));
        Lines.Add(TEXT("[packages]"));
        for (const TSharedPtr<FAssetForgePackageItem>& Item : Packages)
        {
            if (Item.IsValid())
            {
                Lines.Add(FString::Printf(
                    TEXT("%s | %s | %s | source_mesh=%d fbx=%d texture=%d material=%d | %s | report=%s"),
                    *Item->StatePrefix(),
                    *Item->AssetName,
                    *Item->TargetPath,
                    Item->SourceMeshDisplayCount(),
                    Item->FbxDisplayCount(),
                    Item->TextureCount,
                    Item->MaterialCount,
                    *Item->RiskSummary(),
                    *Item->ImportReportPath
                ));
            }
        }
        Lines.Add(TEXT(""));
        Lines.Add(TEXT("[history]"));
        for (const TSharedPtr<FString>& Item : History)
        {
            if (Item.IsValid())
            {
                Lines.Add(*Item);
            }
        }
        return FString::Join(Lines, TEXT("\n"));
    }

    void RefreshPackages()
    {
        const FString PreviousPackageDir = SelectedPackage.IsValid() ? SelectedPackage->PackageDir : FString();
        LastRefreshTime = FDateTime::Now();
        ScanRoots.Reset();
        if (bScanManualRootOnly && !ManualPackageRoot.IsEmpty())
        {
            AddRootIfValid(ScanRoots, ManualPackageRoot);
        }
        else
        {
            ScanRoots = CollectExportRoots();
            if (!ManualPackageRoot.IsEmpty())
            {
                AddRootIfValid(ScanRoots, ManualPackageRoot);
            }
        }
        Packages.Reset();
        History.Reset();

        TSet<FString> Manifests;
        for (const FString& Root : ScanRoots)
        {
            FindManifestsRecursive(Root, 0, Manifests);
        }

        for (const FString& Manifest : Manifests)
        {
            TSharedPtr<FAssetForgePackageItem> Item = BuildPackageItemFromManifest(Manifest);
            if (Item.IsValid())
            {
                Packages.Add(Item);
            }
        }

        Packages.Sort([](const TSharedPtr<FAssetForgePackageItem>& A, const TSharedPtr<FAssetForgePackageItem>& B)
        {
            return A.IsValid() && B.IsValid() ? A->ModifiedTime > B->ModifiedTime : A.IsValid();
        });

        if (Packages.Num() > 50)
        {
            Packages.SetNum(50);
        }

        for (const TSharedPtr<FAssetForgePackageItem>& Item : Packages)
        {
            if (Item.IsValid() && !Item->ImportReportPath.IsEmpty())
            {
                History.Add(MakeShared<FString>(FString::Printf(TEXT("%s | %s：%s"), *Item->ReportTimeLabel(), *Item->AssetName, *Item->LastImportStatus)));
            }
        }

        ApplyPackageFilter();
        TSharedPtr<FAssetForgePackageItem> RestoredPackage = FindFilteredPackageByDir(PreviousPackageDir);
        SelectedPackage = RestoredPackage.IsValid() ? RestoredPackage : nullptr;
        if (PackageListView.IsValid())
        {
            if (SelectedPackage.IsValid())
            {
                PackageListView->SetSelection(SelectedPackage);
            }
            else
            {
                PackageListView->ClearSelection();
            }
        }
        LoadSelectedReportDetails();
        if (CanReviewSelectedImport())
        {
            GateMessage = ImportedSelectionMessage;
        }
        else if (SelectedPackage)
        {
            GateMessage = FString::Printf(TEXT("已扫描到 %d 个 AF 包体，并恢复选中 %s。请先检查，再按报告结果导入。"),
                Packages.Num(), *SelectedPackage->AssetName);
        }
        else
        {
            GateMessage = FilteredPackages.Num() > 0
                ? FString::Printf(TEXT("已扫描到 %d 个 AF 包体；请在左侧明确选择一个包体后再检查或导入。"), Packages.Num())
                : TEXT("未扫描到 AF 包体：请确认 Maya 导出已完成，或设置 ASSET_FORGE_EXPORT_ROOT 指向导出目录。");
        }
    }

    TSharedPtr<FAssetForgePackageItem> FindFilteredPackageByDir(const FString& PackageDir) const
    {
        if (PackageDir.IsEmpty())
        {
            return nullptr;
        }
        for (const TSharedPtr<FAssetForgePackageItem>& Item : FilteredPackages)
        {
            if (Item.IsValid() && Item->PackageDir == PackageDir)
            {
                return Item;
            }
        }
        return nullptr;
    }

    void ApplyPackageFilter()
    {
        FilteredPackages.Reset();
        const FString Query = SearchText.TrimStartAndEnd();
        for (const TSharedPtr<FAssetForgePackageItem>& Item : Packages)
        {
            if (!Item.IsValid())
            {
                continue;
            }
            if (Query.IsEmpty()
                || Item->AssetName.Contains(Query, ESearchCase::IgnoreCase)
                || Item->SourceDcc.Contains(Query, ESearchCase::IgnoreCase)
                || Item->TargetPath.Contains(Query, ESearchCase::IgnoreCase)
                || Item->PackageDir.Contains(Query, ESearchCase::IgnoreCase)
                || Item->ManifestPath.Contains(Query, ESearchCase::IgnoreCase))
            {
                FilteredPackages.Add(Item);
            }
        }
    }

    FText GetStatusText() const
    {
        if (Packages.Num() > 0 && FilteredPackages.Num() == 0)
        {
            return FText::FromString(FString::Printf(TEXT("状态：筛选无结果 / %s"), *PackageCountsLabel()));
        }
        return Packages.Num() > 0
            ? FText::FromString(FString::Printf(TEXT("状态：%s"), *PackageCountsLabel()))
            : LOCTEXT("StatusEmpty", "状态：等待扫描");
    }

    FString PackageCountsLabel() const
    {
        int32 ReadyCount = 0;
        int32 WarningCount = 0;
        int32 BlockedCount = 0;
        int32 WaitingCount = 0;
        for (const TSharedPtr<FAssetForgePackageItem>& Item : FilteredPackages)
        {
            if (!Item.IsValid())
            {
                continue;
            }
            if (!Item->HasReport())
            {
                ++WaitingCount;
            }
            else if ((Item->bReportCanImportKnown && !Item->bReportCanImport) || Item->ReportErrorCount > 0)
            {
                ++BlockedCount;
            }
            else if (Item->ReportWarningCount > 0 || !Item->bReportCanImportKnown)
            {
                ++WarningCount;
            }
            else
            {
                ++ReadyCount;
            }
        }
        return FString::Printf(
            TEXT("显示 %d / 已发现 %d 个包体 | 放行 %d / 警告 %d / 阻断 %d / 待检查 %d"),
            FilteredPackages.Num(),
            Packages.Num(),
            ReadyCount,
            WarningCount,
            BlockedCount,
            WaitingCount
        );
    }

    FText GetToolVersionText() const
    {
        return FText::FromString(FString(GateVersionLabel));
    }

    FText GetLastRefreshText() const
    {
        if (LastRefreshTime == FDateTime::MinValue())
        {
            return LOCTEXT("LastRefreshEmpty", "最近刷新：尚未扫描");
        }
        return FText::FromString(FString::Printf(TEXT("最近刷新：%s"), *LastRefreshTime.ToString(TEXT("%Y-%m-%d %H:%M"))));
    }

    FText GetScanRootsText() const
    {
        if (ScanRoots.Num() == 0)
        {
            return LOCTEXT("ScanRootsEmpty", "未发现可扫描目录；请选择包体目录，或设置 ASSET_FORGE_EXPORT_ROOT。");
        }
        TArray<FString> Lines;
        Lines.Add(bScanManualRootOnly ? TEXT("模式：只看已选目录") : TEXT("模式：已选目录 + 自动扫描"));
        Lines.Add(FString::Printf(TEXT("目录数：%d"), ScanRoots.Num()));
        for (const FString& Root : ScanRoots)
        {
            Lines.Add(FString::Printf(TEXT("- %s"), *Root));
        }
        return FText::FromString(FString::Join(Lines, TEXT("\n")));
    }

    FText GetScanSourceSummaryText() const
    {
        if (ScanRoots.Num() == 0)
        {
            return LOCTEXT("ScanSourceSummaryEmpty", "未扫描到包体目录");
        }
        return FText::FromString(FString::Printf(
            TEXT("%s · %d 个目录"),
            bScanManualRootOnly ? TEXT("只看已选目录") : TEXT("自动 + 已选"),
            ScanRoots.Num()
        ));
    }

    FText GetManualPackageRootText() const
    {
        return FText::FromString(ManualPackageRoot.IsEmpty() ? TEXT("未设置；点击“选择包体目录”后会固定扫描边界。") : ManualPackageRoot);
    }

    FText GetManualPackageRootShortText() const
    {
        if (ManualPackageRoot.IsEmpty())
        {
            return LOCTEXT("ManualPackageRootShortEmpty", "未设置");
        }
        return FText::FromString(FPaths::GetCleanFilename(ManualPackageRoot));
    }

    FText GetManualPackageRootTooltip() const
    {
        return GetManualPackageRootText();
    }

    ECheckBoxState IsManualRootOnlyChecked() const
    {
        return bScanManualRootOnly ? ECheckBoxState::Checked : ECheckBoxState::Unchecked;
    }

    void OnManualRootOnlyChanged(ECheckBoxState NewState)
    {
        bScanManualRootOnly = NewState == ECheckBoxState::Checked;
        RefreshPackages();
        if (PackageListView.IsValid())
        {
            PackageListView->RequestListRefresh();
        }
        GateMessage = bScanManualRootOnly
            ? TEXT("已切换为只看已选目录；若未设置目录，请先点击“选择包体目录”。")
            : TEXT("已切换为已选目录 + 自动扫描。");
    }

    void InitializeGateImportOptionLists()
    {
        NormalImportOptions = {
            MakeShared<FString>(TEXT("import_normals_and_tangents")),
            MakeShared<FString>(TEXT("import_normals")),
            MakeShared<FString>(TEXT("compute_normals")),
        };
        NormalGenerationOptions = {
            MakeShared<FString>(TEXT("mikk_t_space")),
            MakeShared<FString>(TEXT("built_in")),
        };
        StaticMeshLodGroupOptions = {
            MakeShared<FString>(TEXT("project_default")),
            MakeShared<FString>(TEXT("None")),
            MakeShared<FString>(TEXT("SmallProp")),
            MakeShared<FString>(TEXT("LargeProp")),
            MakeShared<FString>(TEXT("LevelArchitecture")),
            MakeShared<FString>(TEXT("Foliage")),
        };
        VertexColorImportOptions = {
            MakeShared<FString>(TEXT("replace")),
            MakeShared<FString>(TEXT("ignore")),
            MakeShared<FString>(TEXT("override")),
        };
    }

    TSharedPtr<FString> FindOption(const TArray<TSharedPtr<FString>>& Options, const FString& Value) const
    {
        for (const TSharedPtr<FString>& Option : Options)
        {
            if (Option.IsValid() && Option->Equals(Value, ESearchCase::IgnoreCase))
            {
                return Option;
            }
        }
        return Options.Num() > 0 ? Options[0] : nullptr;
    }

    FText GateOptionLabel(const FString& Value) const
    {
        if (Value == TEXT("import_normals_and_tangents")) { return LOCTEXT("NormalImportTangents", "导入法线和切线"); }
        if (Value == TEXT("import_normals")) { return LOCTEXT("NormalImportNormals", "仅导入法线"); }
        if (Value == TEXT("compute_normals")) { return LOCTEXT("NormalCompute", "由 UE 重新计算"); }
        if (Value == TEXT("mikk_t_space")) { return LOCTEXT("NormalGenerationMikk", "MikkTSpace"); }
        if (Value == TEXT("built_in")) { return LOCTEXT("NormalGenerationBuiltIn", "Built-in"); }
        if (Value == TEXT("project_default")) { return LOCTEXT("ProjectDefaultOption", "使用项目默认"); }
        if (Value == TEXT("replace")) { return LOCTEXT("VertexColorReplace", "替换为 FBX 顶点色"); }
        if (Value == TEXT("ignore")) { return LOCTEXT("VertexColorIgnore", "保留现有顶点色"); }
        if (Value == TEXT("override")) { return LOCTEXT("VertexColorOverride", "用覆盖色重写"); }
        return FText::FromString(Value);
    }

    TSharedRef<SWidget> GenerateGateOptionWidget(TSharedPtr<FString> Option) const
    {
        return SNew(STextBlock)
            .Text(GateOptionLabel(Option.IsValid() ? *Option : FString()))
            .Font(DetailFont());
    }

    TSharedRef<SWidget> BuildNormalImportCombo()
    {
        return SNew(SComboBox<TSharedPtr<FString>>)
            .OptionsSource(&NormalImportOptions)
            .InitiallySelectedItem(FindOption(NormalImportOptions, GateNormalImportMethod))
            .OnGenerateWidget(this, &SAssetForgeGatePanel::GenerateGateOptionWidget)
            .OnSelectionChanged(this, &SAssetForgeGatePanel::OnNormalImportSelectionChanged)
            .ToolTipText(LOCTEXT("NormalImportComboTooltip", "决定 FBX 导入时使用源法线/切线，还是由 UE 重新计算。"))
            [
                SNew(STextBlock)
                .Text(TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetNormalImportOptionText))
                .Font(DetailFont())
            ];
    }

    TSharedRef<SWidget> BuildNormalGenerationCombo()
    {
        return SNew(SComboBox<TSharedPtr<FString>>)
            .OptionsSource(&NormalGenerationOptions)
            .InitiallySelectedItem(FindOption(NormalGenerationOptions, GateNormalGenerationMethod))
            .OnGenerateWidget(this, &SAssetForgeGatePanel::GenerateGateOptionWidget)
            .OnSelectionChanged(this, &SAssetForgeGatePanel::OnNormalGenerationSelectionChanged)
            .IsEnabled(TAttribute<bool>::CreateSP(this, &SAssetForgeGatePanel::IsNormalGenerationEnabled))
            .ToolTipText(TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetNormalGenerationTooltipText))
            [
                SNew(STextBlock)
                .Text(TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetNormalGenerationOptionText))
                .Font(DetailFont())
            ];
    }

    TSharedRef<SWidget> BuildNormalOptionRow()
    {
        return SNew(SHorizontalBox)
            + SHorizontalBox::Slot().AutoWidth()
            [
                SNew(SBox)
                .WidthOverride(190.0f)
                [
                    BuildNormalImportCombo()
                ]
            ]
            + SHorizontalBox::Slot().AutoWidth().Padding(12.0f, 0.0f, 4.0f, 0.0f).VAlign(VAlign_Center)
            [
                TextBlock(LOCTEXT("GateNormalGenerationInlineLabel", "法线生成"))
            ]
            + SHorizontalBox::Slot().AutoWidth()
            [
                SNew(SBox)
                .WidthOverride(130.0f)
                [
                    BuildNormalGenerationCombo()
                ]
            ];
    }

    TSharedRef<SWidget> BuildLodGroupCombo()
    {
        return SNew(SComboBox<TSharedPtr<FString>>)
            .OptionsSource(&StaticMeshLodGroupOptions)
            .InitiallySelectedItem(FindOption(StaticMeshLodGroupOptions, GateStaticMeshLodGroup))
            .OnGenerateWidget(this, &SAssetForgeGatePanel::GenerateGateOptionWidget)
            .OnSelectionChanged(this, &SAssetForgeGatePanel::OnLodGroupSelectionChanged)
            .ToolTipText(LOCTEXT("LodGroupComboTooltip", "导入后写入 Static Mesh LODGroup；项目默认表示不强制覆盖。"))
            [
                SNew(STextBlock)
                .Text(TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetLodGroupOptionText))
                .Font(DetailFont())
            ];
    }

    TSharedRef<SWidget> BuildVertexColorCombo()
    {
        return SNew(SComboBox<TSharedPtr<FString>>)
            .OptionsSource(&VertexColorImportOptions)
            .InitiallySelectedItem(FindOption(VertexColorImportOptions, GateVertexColorImportOption))
            .OnGenerateWidget(this, &SAssetForgeGatePanel::GenerateGateOptionWidget)
            .OnSelectionChanged(this, &SAssetForgeGatePanel::OnVertexColorSelectionChanged)
            .ToolTipText(LOCTEXT("VertexColorComboTooltip", "控制 FBX 顶点色导入：替换、忽略或用覆盖色重写。"))
            [
                SNew(STextBlock)
                .Text(TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetVertexColorOptionText))
                .Font(DetailFont())
            ];
    }

    TSharedRef<SWidget> BuildImportUniformScaleWidget()
    {
        return SNew(SBox)
            .WidthOverride(90.0f)
            [
                SNew(SNumericEntryBox<float>)
                .MinValue(0.001f)
                .MaxValue(1000.0f)
                .MinSliderValue(0.01f)
                .MaxSliderValue(10.0f)
                .AllowSpin(true)
                .Value(this, &SAssetForgeGatePanel::GetGateImportUniformScale)
                .OnValueChanged(this, &SAssetForgeGatePanel::OnGateImportUniformScaleChanged)
                .IsEnabled(TAttribute<bool>::CreateSP(this, &SAssetForgeGatePanel::HasSelectedPackage))
                .ToolTipText(LOCTEXT("ImportUniformScaleTooltip", "导入 FBX 时应用的统一缩放；默认 1.0，不改变 DCC 尺度。"))
            ];
    }

    TSharedRef<SWidget> BuildVertexOverrideColorRow()
    {
        return SNew(SHorizontalBox)
            .IsEnabled(TAttribute<bool>::CreateSP(this, &SAssetForgeGatePanel::IsVertexOverrideColorEnabled))
            + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)[TextBlock(LOCTEXT("VertexOverrideR", "R"))]
            + SHorizontalBox::Slot().AutoWidth().Padding(4.0f, 0.0f, 12.0f, 0.0f)[BuildColorChannelEntry(0)]
            + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)[TextBlock(LOCTEXT("VertexOverrideG", "G"))]
            + SHorizontalBox::Slot().AutoWidth().Padding(4.0f, 0.0f, 12.0f, 0.0f)[BuildColorChannelEntry(1)]
            + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)[TextBlock(LOCTEXT("VertexOverrideB", "B"))]
            + SHorizontalBox::Slot().AutoWidth().Padding(4.0f, 0.0f, 0.0f, 0.0f)[BuildColorChannelEntry(2)];
    }

    TSharedRef<SWidget> BuildColorChannelEntry(const int32 Channel)
    {
        return SNew(SBox)
            .WidthOverride(84.0f)
            [
                SNew(SNumericEntryBox<float>)
                .MinValue(0.0f)
                .MaxValue(1.0f)
                .MinSliderValue(0.0f)
                .MaxSliderValue(1.0f)
                .AllowSpin(true)
                .Value_Lambda([this, Channel]() { return GetGateVertexOverrideChannel(Channel); })
                .OnValueChanged_Lambda([this, Channel](float NewValue) { SetGateVertexOverrideChannel(Channel, NewValue); })
                .ToolTipText(LOCTEXT("VertexOverrideChannelTooltip", "顶点色 Override 模式下写入的 0-1 颜色通道。"))
            ];
    }

    TSharedRef<SWidget> BuildBasicImportSummaryRow()
    {
        return SNew(STextBlock)
            .Text(LOCTEXT("GateBasicImportSummary", "导入静态网格。AssetForge 根据下方选项导入贴图、创建材质实例并绑定材质槽。FBX 的自动材质和贴图导入保持关闭。"))
            .Font(DetailFont())
            .ColorAndOpacity(FSlateColor::UseSubduedForeground())
            .AutoWrapText(true);
    }

    TSharedRef<SWidget> BuildContentImportOptionRow()
    {
        return SNew(SHorizontalBox)
            + SHorizontalBox::Slot().AutoWidth()[SNew(SCheckBox).IsChecked(TAttribute<ECheckBoxState>::CreateSP(this, &SAssetForgeGatePanel::IsGateImportMaterialsChecked)).OnCheckStateChanged(this, &SAssetForgeGatePanel::OnGateImportMaterialsChanged).IsEnabled(TAttribute<bool>::CreateSP(this, &SAssetForgeGatePanel::HasSelectedPackage))]
            + SHorizontalBox::Slot().AutoWidth().Padding(4.0f, 0.0f, 18.0f, 0.0f)[TextBlock(LOCTEXT("GateImportMaterials", "创建材质实例"))]
            + SHorizontalBox::Slot().AutoWidth()[SNew(SCheckBox).IsChecked(TAttribute<ECheckBoxState>::CreateSP(this, &SAssetForgeGatePanel::IsGateImportTexturesChecked)).OnCheckStateChanged(this, &SAssetForgeGatePanel::OnGateImportTexturesChanged).IsEnabled(TAttribute<bool>::CreateSP(this, &SAssetForgeGatePanel::HasSelectedPackage))]
            + SHorizontalBox::Slot().AutoWidth().Padding(4.0f, 0.0f, 0.0f, 0.0f)[TextBlock(LOCTEXT("GateImportTextures", "导入贴图资产"))];
    }

    TSharedRef<SWidget> BuildTransformOptionRow()
    {
        return SNew(SWrapBox).Tag(TEXT("Gate.Policy.Transform")).UseAllottedSize(true).InnerSlotPadding(FVector2D(13,5))
            + SWrapBox::Slot()
            [SNew(SCheckBox).IsChecked(this, &SAssetForgeGatePanel::IsGateConvertSceneChecked)
                .OnCheckStateChanged(this, &SAssetForgeGatePanel::OnGateConvertSceneChanged)
                .IsEnabled(this, &SAssetForgeGatePanel::HasSelectedPackage)[TextBlock(LOCTEXT("GateConvertScene", "转换场景"))]]
            + SWrapBox::Slot()
            [SNew(SCheckBox).IsChecked(this, &SAssetForgeGatePanel::IsGateForceFrontXAxisChecked)
                .OnCheckStateChanged(this, &SAssetForgeGatePanel::OnGateForceFrontXAxisChanged)
                .IsEnabled(this, &SAssetForgeGatePanel::HasSelectedPackage)[TextBlock(LOCTEXT("GateForceFrontXAxis", "强制 X 前向"))]]
            + SWrapBox::Slot()
            [SNew(SCheckBox).IsChecked(this, &SAssetForgeGatePanel::IsGateConvertSceneUnitChecked)
                .OnCheckStateChanged(this, &SAssetForgeGatePanel::OnGateConvertSceneUnitChanged)
                .IsEnabled(this, &SAssetForgeGatePanel::HasSelectedPackage)[TextBlock(LOCTEXT("GateConvertSceneUnit", "转换单位"))]]
            + SWrapBox::Slot()
            [SNew(SHorizontalBox)
                + SHorizontalBox::Slot().AutoWidth().Padding(0,0,5,0).VAlign(VAlign_Center)
                [TextBlock(LOCTEXT("GateImportUniformScaleInline", "统一缩放"))]
                + SHorizontalBox::Slot().AutoWidth()[BuildImportUniformScaleWidget()]]
            + SWrapBox::Slot()
            [SNew(SCheckBox).IsChecked(this, &SAssetForgeGatePanel::IsGateTransformVertexToAbsoluteChecked)
                .OnCheckStateChanged(this, &SAssetForgeGatePanel::OnGateTransformVertexToAbsoluteChanged)
                .IsEnabled(this, &SAssetForgeGatePanel::HasSelectedPackage)[TextBlock(LOCTEXT("GateTransformVertexToAbsolute", "顶点转绝对坐标"))]]
            + SWrapBox::Slot()
            [SNew(SCheckBox).IsChecked(this, &SAssetForgeGatePanel::IsGateBakePivotInVertexChecked)
                .OnCheckStateChanged(this, &SAssetForgeGatePanel::OnGateBakePivotInVertexChanged)
                .IsEnabled(this, &SAssetForgeGatePanel::HasSelectedPackage)[TextBlock(LOCTEXT("GateBakePivotInVertex", "烘焙 Pivot"))]];
    }

    TSharedRef<SWidget> BuildTransformOffsetOptionRow()
    {
        auto Channels = [this](const FText& Label, bool bTranslation)
        {
            return SNew(SVerticalBox)
                + SVerticalBox::Slot().AutoHeight().Padding(0,0,0,2)[TextBlock(Label)]
                + SVerticalBox::Slot().AutoHeight()
                [SNew(SHorizontalBox)
                    + SHorizontalBox::Slot().AutoWidth().Padding(0,0,4,0)[BuildTransformNumberEntry(0, bTranslation)]
                    + SHorizontalBox::Slot().AutoWidth().Padding(0,0,4,0)[BuildTransformNumberEntry(1, bTranslation)]
                    + SHorizontalBox::Slot().AutoWidth()[BuildTransformNumberEntry(2, bTranslation)]];
        };
        return SNew(SWrapBox).Tag(TEXT("Gate.Policy.Offset")).UseAllottedSize(true).InnerSlotPadding(FVector2D(14,4))
            + SWrapBox::Slot()[Channels(LOCTEXT("GateImportTranslationLabel", "平移 XYZ"), true)]
            + SWrapBox::Slot()[Channels(LOCTEXT("GateImportRotationLabel", "旋转 P/Y/R"), false)];
    }

    TSharedRef<SWidget> BuildTransformNumberEntry(const int32 Channel, const bool bTranslation)
    {
        return SNew(SBox)
            .WidthOverride(76.0f)
            [
                SNew(SNumericEntryBox<float>)
                .MinValue(bTranslation ? -100000.0f : -3600.0f)
                .MaxValue(bTranslation ? 100000.0f : 3600.0f)
                .AllowSpin(true)
                .Value_Lambda([this, Channel, bTranslation]() { return GetGateTransformChannel(Channel, bTranslation); })
                .OnValueChanged_Lambda([this, Channel, bTranslation](float NewValue) { SetGateTransformChannel(Channel, bTranslation, NewValue); })
                .IsEnabled(TAttribute<bool>::CreateSP(this, &SAssetForgeGatePanel::HasSelectedPackage))
                .ToolTipText(bTranslation
                    ? LOCTEXT("GateImportTranslationTooltip", "写入 UFbxAssetImportData.ImportTranslation，单位沿用 UE 导入设置。")
                    : LOCTEXT("GateImportRotationTooltip", "写入 UFbxAssetImportData.ImportRotation，Pitch / Yaw / Roll，单位为度。"))
            ];
    }

    TSharedRef<SWidget> BuildMeshBuildOptionRow()
    {
        return SNew(SHorizontalBox)
            + SHorizontalBox::Slot().AutoWidth()[SNew(SCheckBox).IsChecked(TAttribute<ECheckBoxState>::CreateSP(this, &SAssetForgeGatePanel::IsGateCombineMeshesChecked)).OnCheckStateChanged(this, &SAssetForgeGatePanel::OnGateCombineMeshesChanged).IsEnabled(TAttribute<bool>::CreateSP(this, &SAssetForgeGatePanel::HasSelectedPackage))]
            + SHorizontalBox::Slot().AutoWidth().Padding(4.0f, 0.0f, 18.0f, 0.0f)[TextBlock(LOCTEXT("GateCombineMeshes", "合并 Meshes"))]
            + SHorizontalBox::Slot().AutoWidth()[SNew(SCheckBox).IsChecked(TAttribute<ECheckBoxState>::CreateSP(this, &SAssetForgeGatePanel::IsGateImportLodsChecked)).OnCheckStateChanged(this, &SAssetForgeGatePanel::OnGateImportLodsChanged).IsEnabled(TAttribute<bool>::CreateSP(this, &SAssetForgeGatePanel::HasSelectedPackage))]
            + SHorizontalBox::Slot().AutoWidth().Padding(4.0f, 0.0f, 18.0f, 0.0f)[TextBlock(LOCTEXT("GateImportLods", "导入 LODs"))]
            + SHorizontalBox::Slot().AutoWidth()[SNew(SCheckBox).IsChecked(TAttribute<ECheckBoxState>::CreateSP(this, &SAssetForgeGatePanel::IsGateAutoCollisionChecked)).OnCheckStateChanged(this, &SAssetForgeGatePanel::OnGateAutoCollisionChanged).IsEnabled(TAttribute<bool>::CreateSP(this, &SAssetForgeGatePanel::HasSelectedPackage))]
            + SHorizontalBox::Slot().AutoWidth().Padding(4.0f, 0.0f, 18.0f, 0.0f)[TextBlock(LOCTEXT("GateAutoCollision", "自动碰撞"))]
            + SHorizontalBox::Slot().AutoWidth()[SNew(SCheckBox).IsChecked(TAttribute<ECheckBoxState>::CreateSP(this, &SAssetForgeGatePanel::IsGateOneConvexHullPerUcxChecked)).OnCheckStateChanged(this, &SAssetForgeGatePanel::OnGateOneConvexHullPerUcxChanged).IsEnabled(TAttribute<bool>::CreateSP(this, &SAssetForgeGatePanel::HasSelectedPackage))]
            + SHorizontalBox::Slot().AutoWidth().Padding(4.0f, 0.0f, 0.0f, 0.0f)[TextBlock(LOCTEXT("GateOneConvexHullPerUcx", "每个 UCX 一个凸包"))];
    }

    TSharedRef<SWidget> BuildMeshQualityOptionRow()
    {
        return SNew(SHorizontalBox)
            + SHorizontalBox::Slot().AutoWidth()[SNew(SCheckBox).IsChecked(TAttribute<ECheckBoxState>::CreateSP(this, &SAssetForgeGatePanel::IsGateRemoveDegeneratesChecked)).OnCheckStateChanged(this, &SAssetForgeGatePanel::OnGateRemoveDegeneratesChanged).IsEnabled(TAttribute<bool>::CreateSP(this, &SAssetForgeGatePanel::HasSelectedPackage))]
            + SHorizontalBox::Slot().AutoWidth().Padding(4.0f, 0.0f, 18.0f, 0.0f)[TextBlock(LOCTEXT("GateRemoveDegenerates", "移除退化三角形"))]
            + SHorizontalBox::Slot().AutoWidth()[SNew(SCheckBox).IsChecked(TAttribute<ECheckBoxState>::CreateSP(this, &SAssetForgeGatePanel::IsGateComputeWeightedNormalsChecked)).OnCheckStateChanged(this, &SAssetForgeGatePanel::OnGateComputeWeightedNormalsChanged).IsEnabled(TAttribute<bool>::CreateSP(this, &SAssetForgeGatePanel::HasSelectedPackage))]
            + SHorizontalBox::Slot().AutoWidth().Padding(4.0f, 0.0f, 18.0f, 0.0f)[TextBlock(LOCTEXT("GateComputeWeightedNormals", "加权法线"))]
            + SHorizontalBox::Slot().AutoWidth()[SNew(SCheckBox).IsChecked(TAttribute<ECheckBoxState>::CreateSP(this, &SAssetForgeGatePanel::IsGateBuildReversedIndexBufferChecked)).OnCheckStateChanged(this, &SAssetForgeGatePanel::OnGateBuildReversedIndexBufferChanged).IsEnabled(TAttribute<bool>::CreateSP(this, &SAssetForgeGatePanel::HasSelectedPackage))]
            + SHorizontalBox::Slot().AutoWidth().Padding(4.0f, 0.0f, 0.0f, 0.0f)[TextBlock(LOCTEXT("GateBuildReversedIndexBuffer", "反向索引缓冲"))];
    }

    TSharedRef<SWidget> BuildOutputBuildOptionRow()
    {
        return SNew(SHorizontalBox)
            + SHorizontalBox::Slot().AutoWidth()[SNew(SCheckBox).IsChecked(TAttribute<ECheckBoxState>::CreateSP(this, &SAssetForgeGatePanel::IsGateLightmapUvsChecked)).OnCheckStateChanged(this, &SAssetForgeGatePanel::OnGateLightmapUvsChanged).IsEnabled(TAttribute<bool>::CreateSP(this, &SAssetForgeGatePanel::HasSelectedPackage))]
            + SHorizontalBox::Slot().AutoWidth().Padding(4.0f, 0.0f, 18.0f, 0.0f)[TextBlock(LOCTEXT("GateLightmapUvs", "生成 Lightmap UV"))]
            + SHorizontalBox::Slot().AutoWidth()[SNew(SCheckBox).IsChecked(TAttribute<ECheckBoxState>::CreateSP(this, &SAssetForgeGatePanel::IsGateNaniteChecked)).OnCheckStateChanged(this, &SAssetForgeGatePanel::OnGateNaniteChanged).IsEnabled(TAttribute<bool>::CreateSP(this, &SAssetForgeGatePanel::HasSelectedPackage))]
            + SHorizontalBox::Slot().AutoWidth().Padding(4.0f, 0.0f, 0.0f, 0.0f)[TextBlock(LOCTEXT("GateNanite", "构建 Nanite"))];
    }

    void OnNormalImportSelectionChanged(TSharedPtr<FString> NewValue, ESelectInfo::Type)
    {
        if (NewValue.IsValid())
        {
            GateNormalImportMethod = *NewValue;
        }
    }

    void OnNormalGenerationSelectionChanged(TSharedPtr<FString> NewValue, ESelectInfo::Type)
    {
        if (NewValue.IsValid())
        {
            GateNormalGenerationMethod = *NewValue;
        }
    }

    void OnLodGroupSelectionChanged(TSharedPtr<FString> NewValue, ESelectInfo::Type)
    {
        if (NewValue.IsValid())
        {
            GateStaticMeshLodGroup = *NewValue;
        }
    }

    void OnVertexColorSelectionChanged(TSharedPtr<FString> NewValue, ESelectInfo::Type)
    {
        if (NewValue.IsValid())
        {
            GateVertexColorImportOption = *NewValue;
        }
    }

    FText GetNormalImportOptionText() const { return GateOptionLabel(GateNormalImportMethod); }
    FText GetNormalGenerationOptionText() const { return GateOptionLabel(GateNormalGenerationMethod); }
    FText GetNormalGenerationTooltipText() const
    {
        if (!HasSelectedPackage())
        {
            return LOCTEXT("NormalGenerationNoPackageTooltip", "先选择包体，再设置法线生成方式。");
        }
        if (GateNormalImportMethod == TEXT("import_normals_and_tangents"))
        {
            return LOCTEXT("NormalGenerationDisabledTooltip", "当前导入源法线和切线，UE 会忽略法线生成器；切到计算法线或仅导入法线后可选择。");
        }
        return LOCTEXT("NormalGenerationComboTooltip", "控制 UE 生成法线/切线时使用 MikkTSpace 或内置生成器。");
    }
    FText GetLodGroupOptionText() const { return GateOptionLabel(GateStaticMeshLodGroup); }
    FText GetVertexColorOptionText() const { return GateOptionLabel(GateVertexColorImportOption); }

    bool HasSelectedPackage() const { return GateOperation == EGateOperation::Idle && SelectedPackage.IsValid(); }
    bool HasSelectedReport() const { return SelectedPackage.IsValid() && !SelectedPackage->ImportReportPath.IsEmpty(); }
    bool CanImportSelectedPackage() const
    {
        return HasSelectedPackage()
            && SelectedPackage->HasReport()
            && SelectedPackage->bReportCanImportKnown
            && SelectedPackage->bReportCanImport
            && SelectedPackage->ReportErrorCount <= 0;
    }
    bool IsNormalGenerationEnabled() const { return HasSelectedPackage() && GateNormalImportMethod != TEXT("import_normals_and_tangents"); }
    bool IsVertexOverrideColorEnabled() const { return HasSelectedPackage() && GateVertexColorImportOption == TEXT("override"); }
    EVisibility GetVertexOverrideColorVisibility() const { return IsVertexOverrideColorEnabled() ? EVisibility::Visible : EVisibility::Collapsed; }
    TOptional<float> GetGateImportUniformScale() const { return GateImportUniformScale; }
    void OnGateImportUniformScaleChanged(float NewValue) { GateImportUniformScale = FMath::Clamp(NewValue, 0.001f, 1000.0f); }
    TOptional<float> GetGateTransformChannel(const int32 Channel, const bool bTranslation) const
    {
        if (bTranslation)
        {
            if (Channel == 0) { return GateImportTranslationX; }
            if (Channel == 1) { return GateImportTranslationY; }
            return GateImportTranslationZ;
        }
        if (Channel == 0) { return GateImportRotationPitch; }
        if (Channel == 1) { return GateImportRotationYaw; }
        return GateImportRotationRoll;
    }
    void SetGateTransformChannel(const int32 Channel, const bool bTranslation, float NewValue)
    {
        const float ClampedValue = FMath::Clamp(NewValue, bTranslation ? -100000.0f : -3600.0f, bTranslation ? 100000.0f : 3600.0f);
        if (bTranslation)
        {
            if (Channel == 0) { GateImportTranslationX = ClampedValue; }
            else if (Channel == 1) { GateImportTranslationY = ClampedValue; }
            else { GateImportTranslationZ = ClampedValue; }
            return;
        }
        if (Channel == 0) { GateImportRotationPitch = ClampedValue; }
        else if (Channel == 1) { GateImportRotationYaw = ClampedValue; }
        else { GateImportRotationRoll = ClampedValue; }
    }
    TOptional<float> GetGateVertexOverrideChannel(const int32 Channel) const
    {
        if (Channel == 0) { return GateVertexOverrideColorR; }
        if (Channel == 1) { return GateVertexOverrideColorG; }
        return GateVertexOverrideColorB;
    }
    void SetGateVertexOverrideChannel(const int32 Channel, float NewValue)
    {
        const float ClampedValue = FMath::Clamp(NewValue, 0.0f, 1.0f);
        if (Channel == 0)
        {
            GateVertexOverrideColorR = ClampedValue;
        }
        else if (Channel == 1)
        {
            GateVertexOverrideColorG = ClampedValue;
        }
        else
        {
            GateVertexOverrideColorB = ClampedValue;
        }
    }
    ECheckBoxState IsGateImportMaterialsChecked() const { return bGateImportMaterials ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; }
    ECheckBoxState IsGateImportTexturesChecked() const { return bGateImportTextures ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; }
    ECheckBoxState IsGateImportMeshChecked() const { return HasSelectedPackage() ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; }
    ECheckBoxState IsGateCombineMeshesChecked() const { return bGateCombineMeshes ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; }
    ECheckBoxState IsGateImportLodsChecked() const { return bGateImportLods ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; }
    ECheckBoxState IsGateAutoCollisionChecked() const { return bGateAutoGenerateCollision ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; }
    ECheckBoxState IsGateOneConvexHullPerUcxChecked() const { return bGateOneConvexHullPerUcx ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; }
    ECheckBoxState IsGateRemoveDegeneratesChecked() const { return bGateRemoveDegenerates ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; }
    ECheckBoxState IsGateComputeWeightedNormalsChecked() const { return bGateComputeWeightedNormals ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; }
    ECheckBoxState IsGateLightmapUvsChecked() const { return bGateGenerateLightmapUvs ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; }
    ECheckBoxState IsGateNaniteChecked() const { return bGateBuildNanite ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; }
    ECheckBoxState IsGateBuildReversedIndexBufferChecked() const { return bGateBuildReversedIndexBuffer ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; }
    ECheckBoxState IsGateConvertSceneChecked() const { return bGateConvertScene ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; }
    ECheckBoxState IsGateForceFrontXAxisChecked() const { return bGateForceFrontXAxis ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; }
    ECheckBoxState IsGateConvertSceneUnitChecked() const { return bGateConvertSceneUnit ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; }
    ECheckBoxState IsGateTransformVertexToAbsoluteChecked() const { return bGateTransformVertexToAbsolute ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; }
    ECheckBoxState IsGateBakePivotInVertexChecked() const { return bGateBakePivotInVertex ? ECheckBoxState::Checked : ECheckBoxState::Unchecked; }
    void OnGateImportMaterialsChanged(ECheckBoxState NewState) { bGateImportMaterials = NewState == ECheckBoxState::Checked; }
    void OnGateImportTexturesChanged(ECheckBoxState NewState) { bGateImportTextures = NewState == ECheckBoxState::Checked; }
    void OnGateCombineMeshesChanged(ECheckBoxState NewState) { bGateCombineMeshes = NewState == ECheckBoxState::Checked; }
    void OnGateImportLodsChanged(ECheckBoxState NewState) { bGateImportLods = NewState == ECheckBoxState::Checked; }
    void OnGateAutoCollisionChanged(ECheckBoxState NewState) { bGateAutoGenerateCollision = NewState == ECheckBoxState::Checked; }
    void OnGateOneConvexHullPerUcxChanged(ECheckBoxState NewState) { bGateOneConvexHullPerUcx = NewState == ECheckBoxState::Checked; }
    void OnGateRemoveDegeneratesChanged(ECheckBoxState NewState) { bGateRemoveDegenerates = NewState == ECheckBoxState::Checked; }
    void OnGateComputeWeightedNormalsChanged(ECheckBoxState NewState) { bGateComputeWeightedNormals = NewState == ECheckBoxState::Checked; }
    void OnGateLightmapUvsChanged(ECheckBoxState NewState) { bGateGenerateLightmapUvs = NewState == ECheckBoxState::Checked; }
    void OnGateNaniteChanged(ECheckBoxState NewState) { bGateBuildNanite = NewState == ECheckBoxState::Checked; }
    void OnGateBuildReversedIndexBufferChanged(ECheckBoxState NewState) { bGateBuildReversedIndexBuffer = NewState == ECheckBoxState::Checked; }
    void OnGateConvertSceneChanged(ECheckBoxState NewState) { bGateConvertScene = NewState == ECheckBoxState::Checked; }
    void OnGateForceFrontXAxisChanged(ECheckBoxState NewState) { bGateForceFrontXAxis = NewState == ECheckBoxState::Checked; }
    void OnGateConvertSceneUnitChanged(ECheckBoxState NewState) { bGateConvertSceneUnit = NewState == ECheckBoxState::Checked; }
    void OnGateTransformVertexToAbsoluteChanged(ECheckBoxState NewState)
    {
        bGateTransformVertexToAbsolute = NewState == ECheckBoxState::Checked;
        if (bGateTransformVertexToAbsolute)
        {
            bGateBakePivotInVertex = false;
        }
    }
    void OnGateBakePivotInVertexChanged(ECheckBoxState NewState)
    {
        bGateBakePivotInVertex = NewState == ECheckBoxState::Checked;
        if (bGateBakePivotInVertex)
        {
            bGateTransformVertexToAbsolute = false;
        }
    }

    FString BuildGateImportOptionsJson() const
    {
        TSharedRef<FJsonObject> Options = MakeShared<FJsonObject>();
        Options->SetBoolField(TEXT("import_mesh"), true);
        Options->SetBoolField(TEXT("import_materials"), bGateImportMaterials);
        Options->SetBoolField(TEXT("import_textures"), bGateImportTextures);
        Options->SetBoolField(TEXT("fbx_import_materials"), false);
        Options->SetBoolField(TEXT("fbx_import_textures"), false);
        Options->SetBoolField(TEXT("combine_meshes"), bGateCombineMeshes);
        Options->SetBoolField(TEXT("import_mesh_lods"), bGateImportLods);
        Options->SetBoolField(TEXT("auto_generate_collision"), bGateAutoGenerateCollision);
        Options->SetBoolField(TEXT("one_convex_hull_per_ucx"), bGateOneConvexHullPerUcx);
        Options->SetBoolField(TEXT("remove_degenerates"), bGateRemoveDegenerates);
        Options->SetBoolField(TEXT("compute_weighted_normals"), bGateComputeWeightedNormals);
        Options->SetBoolField(TEXT("generate_lightmap_uvs"), bGateGenerateLightmapUvs);
        Options->SetBoolField(TEXT("build_nanite"), bGateBuildNanite);
        Options->SetBoolField(TEXT("build_reversed_index_buffer"), bGateBuildReversedIndexBuffer);
        Options->SetBoolField(TEXT("convert_scene"), bGateConvertScene);
        Options->SetBoolField(TEXT("force_front_x_axis"), bGateForceFrontXAxis);
        Options->SetBoolField(TEXT("convert_scene_unit"), bGateConvertSceneUnit);
        Options->SetBoolField(TEXT("transform_vertex_to_absolute"), bGateTransformVertexToAbsolute);
        Options->SetBoolField(TEXT("bake_pivot_in_vertex"), bGateBakePivotInVertex);
        TArray<TSharedPtr<FJsonValue>> ImportTranslation;
        ImportTranslation.Add(MakeShared<FJsonValueNumber>(GateImportTranslationX));
        ImportTranslation.Add(MakeShared<FJsonValueNumber>(GateImportTranslationY));
        ImportTranslation.Add(MakeShared<FJsonValueNumber>(GateImportTranslationZ));
        Options->SetArrayField(TEXT("import_translation"), ImportTranslation);
        TArray<TSharedPtr<FJsonValue>> ImportRotation;
        ImportRotation.Add(MakeShared<FJsonValueNumber>(GateImportRotationPitch));
        ImportRotation.Add(MakeShared<FJsonValueNumber>(GateImportRotationYaw));
        ImportRotation.Add(MakeShared<FJsonValueNumber>(GateImportRotationRoll));
        Options->SetArrayField(TEXT("import_rotation"), ImportRotation);
        Options->SetNumberField(TEXT("import_uniform_scale"), GateImportUniformScale);
        Options->SetStringField(TEXT("normal_import_method"), GateNormalImportMethod);
        Options->SetStringField(TEXT("normal_generation_method"), GateNormalGenerationMethod);
        Options->SetStringField(TEXT("static_mesh_lod_group"), GateStaticMeshLodGroup);
        Options->SetStringField(TEXT("vertex_color_import_option"), GateVertexColorImportOption);
        if (GateVertexColorImportOption == TEXT("override"))
        {
            TArray<TSharedPtr<FJsonValue>> VertexOverrideColor;
            VertexOverrideColor.Add(MakeShared<FJsonValueNumber>(GateVertexOverrideColorR));
            VertexOverrideColor.Add(MakeShared<FJsonValueNumber>(GateVertexOverrideColorG));
            VertexOverrideColor.Add(MakeShared<FJsonValueNumber>(GateVertexOverrideColorB));
            Options->SetArrayField(TEXT("vertex_override_color"), VertexOverrideColor);
        }

        FString Output;
        const TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&Output);
        FJsonSerializer::Serialize(Options, Writer);
        return Output;
    }

    FText GetSelectedAssetName() const { return FText::FromString(SelectedPackage.IsValid() ? SelectedPackage->AssetName : TEXT("尚未选择")); }
    FText GetSelectedPackageStateText() const { return FText::FromString(SelectedPackage.IsValid() ? FString::Printf(TEXT("%s 当前选中包体；%s"), *SelectedPackage->StatePrefix(), *SelectedPackage->RiskSummary()) : TEXT("[未选择] 左侧选择包体后才显示状态")); }
    FText GetSelectedSourceDcc() const { return FText::FromString(SelectedPackage.IsValid() && !SelectedPackage->SourceDcc.IsEmpty() ? SelectedPackage->SourceDcc : TEXT("未记录")); }
    FText GetSelectedPackageNamingText() const { return FText::FromString(SelectedPackage.IsValid() ? SelectedPackage->PackageIdentityLine() : TEXT("选择包体后显示")); }
    FText GetSelectedProjectPresetText() const { return FText::FromString(SelectedPackage.IsValid() ? SelectedPackage->ProjectPresetLine() : TEXT("选择包体后显示")); }
    FText GetSelectedTargetPath() const { return FText::FromString(SelectedPackage.IsValid() ? SelectedPackage->TargetPath : TEXT("选择包体后显示")); }
    FText GetSelectedPackageDir() const { return FText::FromString(SelectedPackage.IsValid() ? SelectedPackage->PackageDir : TEXT("选择包体后显示")); }
    FText GetManifestPath() const { return FText::FromString(SelectedPackage.IsValid() ? SelectedPackage->ManifestPath : TEXT("选择包体后显示")); }
    FText GetPackageTimeText() const { return FText::FromString(SelectedPackage.IsValid() ? SelectedPackage->ModifiedTimeLabel() : TEXT("未选择包体")); }
    FText GetReportTimeText() const { return FText::FromString(SelectedPackage.IsValid() ? SelectedPackage->ReportTimeLabel() : TEXT("未选择包体")); }
    FText GetPackageNoteText() const { return FText::FromString(SelectedPackage.IsValid() ? SelectedPackage->OperatorNote() : TEXT("备注：选择包体后显示来源、风险和下一步。")); }
    FText GetMeshSummary() const { return FText::FromString(SelectedPackage.IsValid() ? SelectedPackage->MeshSummaryLine() : TEXT("未检查")); }
    FText GetMaterialBindings() const { return FText::FromString(SelectedPackage && !SelectedPackage->MaterialBindings.IsEmpty() ? SelectedPackage->MaterialBindings : TEXT("未记录映射")); }
    FText GetTextureSummary() const { return FText::FromString(SelectedPackage.IsValid() ? FString::Printf(TEXT("%d 张贴图"), SelectedPackage->TextureCount) : TEXT("未检查")); }
    FText GetMaterialSummary() const { return FText::FromString(SelectedPackage.IsValid() ? SelectedPackage->MaterialSummaryLine() : TEXT("未检查")); }
    FText GetSchemaSummary() const { return FText::FromString(SelectedPackage.IsValid() && !SelectedPackage->SchemaVersion.IsEmpty() ? SelectedPackage->SchemaVersion : TEXT("未记录")); }
    FText GetCombineMeshesText() const
    {
        if (!SelectedPackage.IsValid())
        {
            return LOCTEXT("CombineMeshesEmpty", "选择包体后显示");
        }
        if (!SelectedPackage->bCombineMeshesKnown)
        {
            return LOCTEXT("CombineMeshesUnknown", "未记录；导入前按项目默认值确认");
        }
        return SelectedPackage->bCombineMeshes
            ? LOCTEXT("CombineMeshesEnabled", "开启：多个 FBX 节点会合并为 1 个 Static Mesh")
            : LOCTEXT("CombineMeshesDisabled", "关闭：按 FBX 节点拆分导入");
    }
    FText GetNormalImportText() const { return FText::FromString(SelectedPackage.IsValid() && !SelectedPackage->NormalImportMethod.IsEmpty() ? SelectedPackage->NormalImportMethod : TEXT("未记录 / 使用项目默认")); }
    FText GetLodPolicyText() const { return FText::FromString(SelectedPackage.IsValid() && !SelectedPackage->StaticMeshLodPolicy.IsEmpty() ? SelectedPackage->StaticMeshLodPolicy : TEXT("未记录 / 使用项目默认")); }
    FText GetNanitePolicyText() const { return FText::FromString(SelectedPackage.IsValid() && !SelectedPackage->NanitePolicy.IsEmpty() ? SelectedPackage->NanitePolicy : TEXT("未记录 / 使用项目默认")); }
    FText GetGateMessage() const
    {
        return FText::FromString(GateMessage);
    }
    FText GetWriteContentSummaryText() const
    {
        if (!SelectedPackage.IsValid())
        {
            return LOCTEXT("WriteContentSummaryEmpty", "未选择包体；不会写入任何 UE 资产。");
        }

        const FString MaterialState = bGateImportMaterials ? TEXT("创建 AF 材质实例并绑定 slot") : TEXT("跳过 AF 材质实例和 slot 绑定");
        const FString TextureState = bGateImportTextures ? TEXT("导入 AF 打包贴图") : TEXT("跳过 AF 打包贴图");
        return FText::FromString(FString::Printf(TEXT("只写入当前选中包体；Static Mesh 始终导入；%s；%s；UE FBX 自动材质/贴图导入保持关闭。"), *MaterialState, *TextureState));
    }
    FText GetFlowSummaryText() const
    {
        if (!SelectedPackage.IsValid())
        {
            return LOCTEXT("FlowSummaryEmpty", "状态：未选择包体；导入动作禁用。");
        }
        if (!SelectedPackage->HasReport())
        {
            return LOCTEXT("FlowSummaryNoReport", "状态：已选择包体；可先检查，导入等待报告放行。");
        }
        if (SelectedPackage->bReportCanImportKnown && SelectedPackage->bReportCanImport)
        {
            return LOCTEXT("FlowSummaryReady", "状态：报告已放行；可以导入当前包体。");
        }
        if ((SelectedPackage->bReportCanImportKnown && !SelectedPackage->bReportCanImport) || SelectedPackage->ReportErrorCount > 0)
        {
            return LOCTEXT("FlowSummaryBlocked", "状态：报告未放行；请修复阻断项后重新检查。");
        }
        return LOCTEXT("FlowSummaryReview", "状态：报告需要复核；导入前请确认报告结论。");
    }
    FText GetNextActionText() const
    {
        if (!SelectedPackage.IsValid())
        {
            return LOCTEXT("NextActionEmpty", "未选择包体；刷新扫描并在左侧选择一个 AF 包体。");
        }
        if (!SelectedPackage->ImportReportPath.IsEmpty())
        {
            if (SelectedPackage->bReportCanImportKnown && SelectedPackage->bReportCanImport)
            {
                if (!SelectedPackage->ReportNextAction.IsEmpty())
                {
                    return FText::FromString(FString::Printf(TEXT("报告放行：%s"), *SelectedPackage->ReportNextAction));
                }
                return LOCTEXT("NextActionReportReady", "报告已放行；确认当前包体无误后，可执行导入。");
            }
            if ((SelectedPackage->bReportCanImportKnown && !SelectedPackage->bReportCanImport) || SelectedPackage->ReportErrorCount > 0)
            {
                if (!SelectedPackage->ReportNextAction.IsEmpty())
                {
                    return FText::FromString(FString::Printf(TEXT("报告阻断：%s"), *SelectedPackage->ReportNextAction));
                }
                return LOCTEXT("NextActionReportBlocked", "报告未放行；修复阻断项后重新检查。");
            }
            if (!SelectedPackage->ReportNextAction.IsEmpty())
            {
                return FText::FromString(FString::Printf(TEXT("报告待判定：%s"), *SelectedPackage->ReportNextAction));
            }
            return LOCTEXT("NextActionReportReview", "报告已生成但未记录导入许可；请复核报告后再决定是否导入。");
        }
        return LOCTEXT("NextActionSelected", "请先检查包体，报告放行后可确认导入。");
    }
    FText GetDryRunButtonText() const { return SelectedPackage.IsValid() ? LOCTEXT("DryRunSelectedPackage", "不写入验证") : LOCTEXT("DryRunNeedsPackage", "先选择包体"); }
    FText GetPreviewTooltipText() const { return SelectedPackage.IsValid() ? LOCTEXT("PreviewTooltipSelected", "检查包体结构、风险和目标路径，生成检查报告；不创建 UE 资产。") : LOCTEXT("PreviewTooltipEmpty", "左侧选择 AF 包体后才能生成检查报告。"); }
    FText GetDryRunTooltipText() const { return SelectedPackage.IsValid() ? LOCTEXT("DryRunTooltipSelected", "按当前导入选项验证一次；检查 FBX、贴图、材质实例和目标路径，但不创建 UE 资产。") : LOCTEXT("DryRunTooltipEmpty", "左侧选择 AF 包体后才能验证。"); }
    FText GetImportTooltipText() const
    {
        if (GateOperation != EGateOperation::Idle)
        {
            return FText::GetEmpty();
        }
        if (!SelectedPackage.IsValid())
        {
            return LOCTEXT("ImportTooltipEmpty", "选择包体并完成检查后再导入。");
        }
        if (!SelectedPackage->HasReport())
        {
            return LOCTEXT("ImportTooltipNoReport", "当前包体还没有报告；先执行检查。");
        }
        if (!CanImportSelectedPackage())
        {
            return LOCTEXT("ImportTooltipBlocked", "请在包体摘要中处理阻断项，再重新检查。");
        }
        return LOCTEXT("ImportTooltipSelected", "先核对目标和写入影响，再确认导入当前包体。");
    }
    FText GetOpenReportTooltipText() const { return HasSelectedReport() ? LOCTEXT("OpenReportTooltipReady", "在文件管理器中选中当前包体的报告文件。") : LOCTEXT("OpenReportTooltipEmpty", "当前包体还没有报告；先执行检查。"); }
    FText GetHistorySummary() const
    {
        if (SelectedPackage.IsValid() && !SelectedPackage->ImportReportPath.IsEmpty())
        {
            return FText::FromString(FString::Printf(TEXT("%s | %s：%s"), *SelectedPackage->ReportTimeLabel(), *SelectedPackage->AssetName, *ReportDecisionLine(*SelectedPackage)));
        }
        return FText::FromString(History.Num() > 0 ? *History[0] : TEXT("暂无导入记录；导入完成后这里显示最近结果。"));
    }
    FText GetReportStateText() const
    {
        if (!SelectedPackage.IsValid())
        {
            return LOCTEXT("ReportStateNoPackage", "未选择包体；左侧选择后才会显示报告状态。");
        }
        if (SelectedPackage.IsValid() && !SelectedPackage->ImportReportPath.IsEmpty())
        {
            return FText::FromString(ReportDecisionLine(*SelectedPackage));
        }
        return LOCTEXT("ReportStateEmpty", "暂无报告；先执行检查，报告会写入包体目录。");
    }
    FText GetReportPath() const { return FText::FromString(SelectedPackage.IsValid() && !SelectedPackage->ImportReportPath.IsEmpty() ? SelectedPackage->ImportReportPath : TEXT("选择包体并执行检查后生成报告")); }
    FText GetDebugExportPathText() const { return FText::FromString(LastDebugExportPath.IsEmpty() ? TEXT("尚未导出；点击“导出调试信息”生成文本快照") : LastDebugExportPath); }
    FText GetReportPermissionText() const
    {
        if (!SelectedPackage.IsValid())
        {
            return LOCTEXT("ReportPermissionNoPackage", "未选择包体；导入许可不可判定。");
        }
        if (SelectedPackage.IsValid() && SelectedPackage->HasReport())
        {
            return FText::FromString(ReportImportPermissionText(*SelectedPackage));
        }
        return LOCTEXT("ReportPermissionEmpty", "暂无报告；导入许可未生成，当前不应执行导入。");
    }
    FText GetReportRiskText() const
    {
        if (!SelectedPackage.IsValid())
        {
            return LOCTEXT("ReportRiskNoPackage", "未选择包体");
        }
        if (SelectedPackage->HasReport())
        {
            return FText::FromString(SelectedPackage->RiskSummary());
        }
        return LOCTEXT("ReportRiskEmpty", "暂无报告；先检查后显示警告与阻断计数");
    }
};

class SWorkbench : public SCompoundWidget
{
public:
    SLATE_BEGIN_ARGS(SWorkbench) {}
    SLATE_END_ARGS()

    void Construct(const FArguments&)
    {
        ChildSlot[SNew(SVerticalBox)
            + SVerticalBox::Slot().AutoHeight().Padding(8,6)
            [SNew(SHorizontalBox)
                + SHorizontalBox::Slot().FillWidth(1).HAlign(HAlign_Left)
                [SNew(SHorizontalBox)
                    + SHorizontalBox::Slot().AutoWidth().Padding(0,0,4,0)
                    [ModeButton(0, TEXT("Workbench.Mode.Import"), "Icons.Import",
                        LOCTEXT("ImportPage", "包体导入"), LOCTEXT("ImportScope", "DCC → UE"),
                        LOCTEXT("ImportModeTip", "从 DCC 导出包检查并导入资产"))]
                    + SHorizontalBox::Slot().AutoWidth()
                    [ModeButton(1, TEXT("Workbench.Mode.Review"), "Icons.Search",
                        LOCTEXT("ReviewPage", "入库批审"), LOCTEXT("ReviewScope", "UE 存量体检"),
                        LOCTEXT("ReviewModeTip", "检查工程内的网格、材质和贴图"))]]
                + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(8,0,2,0)
                [SNew(STextBlock).Text(FText::FromString(GateVersionLabel)).TextStyle(FAppStyle::Get(),"SmallText.Subdued")]
                + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(4,0,0,0)
                [SNew(SComboButton).Tag(TEXT("Workbench.Settings"))
                    .ButtonStyle(&FAppStyle::Get().GetWidgetStyle<FButtonStyle>("SimpleButton"))
                    .HasDownArrow(false).MenuPlacement(MenuPlacement_ComboBoxRight).ContentPadding(FMargin(6))
                    .ToolTipText(LOCTEXT("WorkbenchSettings", "AssetForge 设置"))
                    .OnGetMenuContent(this, &SWorkbench::BuildSettingsMenu)
                    .ButtonContent()
                    [SNew(SBox).WidthOverride(18).HeightOverride(18)
                        [SNew(SImage).Image(FAppStyle::GetBrush("Icons.Settings")).ColorAndOpacity(FSlateColor::UseForeground())]]]]
            + SVerticalBox::Slot().AutoHeight()[SNew(SSeparator)]
            + SVerticalBox::Slot().FillHeight(1).Padding(6)
            [SAssignNew(Pages,SWidgetSwitcher)
                + SWidgetSwitcher::Slot()[SNew(SAssetForgeGatePanel)]
                + SWidgetSwitcher::Slot()[SAssignNew(ReviewHost,SBox)]]];
    }

    void Show(int32 Page)
    {
        if (Page == 1 && !ReviewPanel.IsValid())
        {
            ReviewPanel = AssetForgeReview::CreatePanel();
            ReviewHost->SetContent(ReviewPanel.ToSharedRef());
        }
        Pages->SetActiveWidgetIndex(Page);
    }
private:
    int32 ActivePage() const { return Pages ? Pages->GetActiveWidgetIndex() : 0; }

    struct FCacheDirectory
    {
        FString Path;
        FText Size;
        bool bExists = false;
    };

    void RefreshCacheStatus(bool bClear)
    {
        CacheDirectories.Reset();
        FString Error;
        const auto Result = ExecuteWorkbenchPythonCommand(FString::Printf(
            TEXT("from asset_forge.shared.workbench_cache import manage_cache\n")
            TEXT("_af_result = manage_cache('unreal', clear=%s)"), bClear ? TEXT("True") : TEXT("False")), Error);
        bCacheHasHistory = false;
        double TotalBytes = 0, EligibleBytes = 0, RemovedBytes = 0;
        if (!Result || !Result->TryGetNumberField(TEXT("bytes"), TotalBytes)
            || !Result->TryGetNumberField(TEXT("eligible_bytes"), EligibleBytes))
        {
            CacheSizeText = LOCTEXT("CacheSizeUnavailable", "暂时无法统计 AssetForge 缓存。");
            CacheFeedback = bClear ? LOCTEXT("CacheClearUnavailable", "清理状态未返回，请重新打开设置查看。") : FText::GetEmpty();
            return;
        }
        bCacheHasHistory = JsonIntField(Result, TEXT("eligible_files")) > 0;
        CacheSizeText = FText::Format(LOCTEXT("CacheSizeStatus", "当前大小 {0} · 可清理 {1}"),
            FText::AsMemory(static_cast<uint64>(TotalBytes)), FText::AsMemory(static_cast<uint64>(EligibleBytes)));
        const TArray<TSharedPtr<FJsonValue>>* Directories = nullptr;
        if (Result->TryGetArrayField(TEXT("directories"), Directories))
        {
            for (const auto& Value : *Directories)
            {
                if (!Value || Value->Type != EJson::Object)
                {
                    continue;
                }
                const auto Entry = Value->AsObject();
                FString DirectoryId;
                FCacheDirectory Directory;
                double DirectoryBytes = 0, DirectoryEligibleBytes = 0;
                if (!Entry || !Entry->TryGetStringField(TEXT("id"), DirectoryId)
                    || (DirectoryId != TEXT("logs") && DirectoryId != TEXT("reports"))
                    || !Entry->TryGetStringField(TEXT("path"), Directory.Path)
                    || Directory.Path.IsEmpty() || FPaths::IsRelative(Directory.Path)
                    || !Entry->TryGetBoolField(TEXT("exists"), Directory.bExists)
                    || !Entry->TryGetNumberField(TEXT("bytes"), DirectoryBytes)
                    || !Entry->TryGetNumberField(TEXT("eligible_bytes"), DirectoryEligibleBytes))
                {
                    continue;
                }
                Directory.Size = FText::Format(LOCTEXT("CacheDirectorySize", "当前 {0} · 可清理 {1}"),
                    FText::AsMemory(static_cast<uint64>(DirectoryBytes)), FText::AsMemory(static_cast<uint64>(DirectoryEligibleBytes)));
                CacheDirectories.Add(DirectoryId, MoveTemp(Directory));
            }
        }
        if (bClear)
        {
            Result->TryGetNumberField(TEXT("removed_bytes"), RemovedBytes);
            const int32 RemovedFiles = JsonIntField(Result, TEXT("removed_files"));
            const int32 FailedFiles = JsonIntField(Result, TEXT("failed_files"));
            const FText Size = FText::AsMemory(static_cast<uint64>(RemovedBytes));
            CacheFeedback = FailedFiles > 0
                ? FText::Format(LOCTEXT("CacheClearPartial", "已清理 {0} 个文件（{1}）。{2} 个文件未能清理。"), RemovedFiles, Size, FailedFiles)
                : FText::Format(LOCTEXT("CacheClearDone", "已清理 {0} 个文件（{1}）。"), RemovedFiles, Size);
        }
    }

    FReply OpenCacheDirectory(const FString& DirectoryId)
    {
        FCacheDirectory* Directory = CacheDirectories.Find(DirectoryId);
        if (Directory && Directory->bExists)
        {
            if (FPaths::DirectoryExists(Directory->Path))
            {
                FPlatformProcess::ExploreFolder(*Directory->Path);
            }
            else
            {
                Directory->bExists = false;
                CacheFeedback = LOCTEXT("CacheDirectoryUnavailable", "目录已移动或不可用，请重新打开设置查看。");
            }
        }
        return FReply::Handled();
    }

    TSharedRef<SWidget> BuildCacheDirectoryRow(const FString& DirectoryId, FName OpenTag, const FText& Label)
    {
        return SNew(SVerticalBox)
            + SVerticalBox::Slot().AutoHeight().Padding(0,1)
            [SNew(SHorizontalBox)
                + SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center)
                [SNew(STextBlock).Text(Label)]
                + SHorizontalBox::Slot().AutoWidth()
                [SNew(SButton).Tag(OpenTag)
                    .Text(LOCTEXT("OpenCacheFolder", "打开目录"))
                    .IsEnabled_Lambda([this, DirectoryId]()
                    {
                        const auto* Directory = CacheDirectories.Find(DirectoryId);
                        return Directory && Directory->bExists;
                    })
                    .OnClicked_Lambda([this, DirectoryId](){ return OpenCacheDirectory(DirectoryId); })]]
            + SVerticalBox::Slot().AutoHeight().Padding(0,2)
            [SNew(STextBlock).AutoWrapText(true).WrappingPolicy(ETextWrappingPolicy::AllowPerCharacterWrapping)
                .ColorAndOpacity(FSlateColor::UseSubduedForeground())
                .Text_Lambda([this, DirectoryId]()
                {
                    const auto* Directory = CacheDirectories.Find(DirectoryId);
                    return Directory ? FText::FromString(Directory->Path) : LOCTEXT("CacheDirectoryUnknown", "暂时无法获取目录路径");
                })]
            + SVerticalBox::Slot().AutoHeight()
            [SNew(STextBlock).Text_Lambda([this, DirectoryId]()
            {
                const auto* Directory = CacheDirectories.Find(DirectoryId);
                if (!Directory)
                {
                    return FText::GetEmpty();
                }
                return Directory->bExists ? Directory->Size : LOCTEXT("CacheDirectoryMissing", "目录尚未创建或不可用");
            })];
    }

    static FText ReadAboutLicenseName()
    {
        FString Document;
        if (const TSharedPtr<IPlugin> Plugin = IPluginManager::Get().FindPlugin(TEXT("AssetForge")))
        {
            const FString PluginRoot = Plugin->GetBaseDir();
            if (!FFileHelper::LoadFileToString(Document, *(PluginRoot / TEXT("LICENSE"))))
            {
                const FString SourceRoot = FPaths::Combine(PluginRoot, TEXT(".."), TEXT(".."));
                if (FPaths::FileExists(SourceRoot / TEXT("asset_forge/__init__.py")))
                {
                    FFileHelper::LoadFileToString(Document, *(SourceRoot / TEXT("LICENSE")));
                }
            }
        }
        FString Name;
        if (!Document.Split(TEXT("\n"), &Name, nullptr))
        {
            Name = Document;
        }
        Name.TrimStartAndEndInline();
        return Name.IsEmpty() ? LOCTEXT("WorkbenchLicenseUnavailable", "未找到许可文件") : FText::FromString(Name);
    }

    TSharedRef<SWidget> BuildSettingsMenu()
    {
        bCacheClearArmed = false;
        CacheFeedback = FText::GetEmpty();
        RefreshCacheStatus(false);
        const FSlateFontInfo Heading = FAppStyle::GetFontStyle("PropertyWindow.BoldFont");
        return SNew(SBox).WidthOverride(400)
            [SNew(SBorder).BorderImage(FAppStyle::GetBrush("Menu.Background")).Padding(FMargin(12,10))
                [SNew(SVerticalBox)
                    + SVerticalBox::Slot().AutoHeight().Padding(0,0,0,5)
                    [SNew(STextBlock).Text(LOCTEXT("WorkbenchPreferences", "通用偏好")).Font(Heading)]
                    + SVerticalBox::Slot().AutoHeight()
                    [WrappedTextBlock(LOCTEXT("WorkbenchFeedbackPreference", "检查结果和导入提醒显示在工作台内。存量检查的平台与材质偏好可在「入库批审」的「批审规则」中调整。"))]
                    + SVerticalBox::Slot().AutoHeight().Padding(0,9)
                    [SNew(SSeparator)]
                    + SVerticalBox::Slot().AutoHeight().Padding(0,0,0,5)
                    [SNew(STextBlock).Text(LOCTEXT("WorkbenchCache", "清理缓存")).Font(Heading)]
                    + SVerticalBox::Slot().AutoHeight()
                    [SNew(STextBlock).Tag(TEXT("Workbench.Cache.Size")).Text_Lambda([this](){ return CacheSizeText; })]
                    + SVerticalBox::Slot().AutoHeight().Padding(0,5,0,0)
                    [BuildCacheDirectoryRow(TEXT("logs"), TEXT("Workbench.Cache.Open.Logs"), LOCTEXT("CacheOperationLogs", "操作日志"))]
                    + SVerticalBox::Slot().AutoHeight().Padding(0,5,0,0)
                    [BuildCacheDirectoryRow(TEXT("reports"), TEXT("Workbench.Cache.Open.Reports"), LOCTEXT("CacheWorkbenchReports", "工作台报告缓存"))]
                    + SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Left).Padding(0,6,0,0)
                    [SNew(SButton).Tag(TEXT("Workbench.Cache.Clear"))
                        .Text(LOCTEXT("CacheClearHistory", "清理历史缓存与日志"))
                        .IsEnabled_Lambda([this](){ return bCacheHasHistory && !bCacheClearArmed; })
                        .OnClicked_Lambda([this](){ CacheFeedback = FText::GetEmpty(); bCacheClearArmed = true; return FReply::Handled(); })]
                    + SVerticalBox::Slot().AutoHeight()
                    [SNew(SVerticalBox)
                        .Visibility_Lambda([this](){ return bCacheClearArmed ? EVisibility::Visible : EVisibility::Collapsed; })
                        + SVerticalBox::Slot().AutoHeight().Padding(0,6,0,4)
                        [WrappedTextBlock(LOCTEXT("CacheClearConfirmation", "清理 AssetForge 的历史缓存与日志？包体、报告和工程资产将保留。"))]
                        + SVerticalBox::Slot().AutoHeight()
                        [SNew(SHorizontalBox)
                            + SHorizontalBox::Slot().AutoWidth().Padding(0,0,6,0)
                            [SNew(SButton).Tag(TEXT("Workbench.Cache.Confirm"))
                                .Text(LOCTEXT("CacheConfirmClear", "确认清理"))
                                .OnClicked_Lambda([this]()
                                {
                                    if (bCacheClearArmed)
                                    {
                                        bCacheClearArmed = false;
                                        RefreshCacheStatus(true);
                                    }
                                    return FReply::Handled();
                                })]
                            + SHorizontalBox::Slot().AutoWidth()
                            [SNew(SButton).Tag(TEXT("Workbench.Cache.Cancel"))
                                .Text(LOCTEXT("CacheCancelClear", "取消"))
                                .OnClicked_Lambda([this](){ bCacheClearArmed = false; return FReply::Handled(); })]]]
                    + SVerticalBox::Slot().AutoHeight()
                    [WrappedTextBlock(TAttribute<FText>::CreateLambda([this](){ return CacheFeedback; }))]
                    + SVerticalBox::Slot().AutoHeight().Padding(0,9)
                    [SNew(SSeparator)]
                    + SVerticalBox::Slot().AutoHeight().Padding(0,0,0,5)
                    [SNew(STextBlock).Text(LOCTEXT("WorkbenchAbout", "关于与更新")).Font(Heading)]
                    + SVerticalBox::Slot().AutoHeight()
                    [SNew(STextBlock).Text(LOCTEXT("WorkbenchAboutVersion", "DCC AssetForge v0.2.0"))]
                    + SVerticalBox::Slot().AutoHeight().Padding(0,3,0,0)
                    [SNew(STextBlock).Text(FText::Format(LOCTEXT("WorkbenchEngineVersion", "当前 Unreal Engine {0}"),
                        FText::FromString(FEngineVersion::Current().ToString(EVersionComponent::Patch))))]
                    + SVerticalBox::Slot().AutoHeight().Padding(0,3,0,0)
                    [SNew(STextBlock).Text(LOCTEXT("WorkbenchAboutDeveloper", "开发者：卓雨 (Elviszhuoyu)"))
                        .ColorAndOpacity(FSlateColor::UseSubduedForeground())]
                    + SVerticalBox::Slot().AutoHeight().Padding(0,3,0,0)
                    [SNew(STextBlock).Text(FText::Format(LOCTEXT("WorkbenchAboutLicense", "著作权与许可：© 2026 Elviszhuoyu · {0}"), ReadAboutLicenseName()))
                        .ColorAndOpacity(FSlateColor::UseSubduedForeground())]
                    + SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Left).Padding(0,6,0,0)
                    [SNew(SButton).Tag(TEXT("Workbench.About.Releases"))
                        .Text(LOCTEXT("WorkbenchReleaseNotes", "前往 GitHub Releases 检查更新"))
                        .OnClicked_Lambda([]()
                        {
                            FPlatformProcess::LaunchURL(TEXT("https://github.com/Elviszhuoyu/DCC-AssetForge/releases"), nullptr, nullptr);
                            return FReply::Handled();
                        })]
                    + SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Left).Padding(0,6,0,0)
                    [SNew(SHorizontalBox)
                        + SHorizontalBox::Slot().AutoWidth().Padding(0,0,6,0)
                        [SNew(SButton).Tag(TEXT("Workbench.About.Project"))
                            .Text(LOCTEXT("WorkbenchProjectHomepage", "项目主页"))
                            .OnClicked_Lambda([]()
                            {
                                FPlatformProcess::LaunchURL(TEXT("https://github.com/Elviszhuoyu/DCC-AssetForge"), nullptr, nullptr);
                                return FReply::Handled();
                            })]
                        + SHorizontalBox::Slot().AutoWidth()
                        [SNew(SButton).Tag(TEXT("Workbench.About.Author"))
                            .Text(LOCTEXT("WorkbenchAuthorHomepage", "作者主页"))
                            .OnClicked_Lambda([]()
                            {
                                FPlatformProcess::LaunchURL(TEXT("https://work.zhuoyulabs.com"), nullptr, nullptr);
                                return FReply::Handled();
                            })]]]];
    }

    TSharedRef<SWidget> ModeButton(int32 Page, FName ModeTag, FName Icon, const FText& Title, const FText& Scope, const FText& Tip)
    {
        return SNew(SButton).Tag(ModeTag).ButtonStyle(FAppStyle::Get(), "SimpleButton").ContentPadding(0)
            .ToolTipText(Tip)
            .OnClicked_Lambda([this, Page](){ Show(Page); return FReply::Handled(); })
            [ModeLabel(Page, Icon, Title, Scope)];
    }

    TSharedRef<SWidget> ModeLabel(int32 Page, FName Icon, const FText& Title, const FText& Scope)
    {
        FSlateFontInfo TitleFont = FAppStyle::GetFontStyle("PropertyWindow.BoldFont");
        TitleFont.Size = 13;
        return SNew(SVerticalBox)
            + SVerticalBox::Slot().AutoHeight().Padding(10,6,8,4)
            [SNew(SHorizontalBox)
                + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0,0,8,0)
                [SNew(SBox).WidthOverride(18).HeightOverride(18)
                    [SNew(SImage).Image(FAppStyle::GetBrush(Icon)).ColorAndOpacity(FSlateColor::UseForeground())]]
                + SHorizontalBox::Slot().FillWidth(1)
                [SNew(SVerticalBox)
                    + SVerticalBox::Slot().AutoHeight()[SNew(STextBlock).Text(Title).Font(TitleFont)]
                    + SVerticalBox::Slot().AutoHeight()[SNew(STextBlock).Text(Scope).TextStyle(FAppStyle::Get(),"SmallText.Subdued")]]]
            + SVerticalBox::Slot().AutoHeight()
            [SNew(SBox).HeightOverride(3)
                [SNew(SBorder).BorderImage(FAppStyle::GetBrush("WhiteBrush")).Padding(0)
                    .BorderBackgroundColor(FStyleColors::Primary)
                    .Visibility_Lambda([this,Page](){ return ActivePage() == Page ? EVisibility::HitTestInvisible : EVisibility::Hidden; })]];
    }

    TSharedPtr<SWidgetSwitcher> Pages;
    TSharedPtr<SBox> ReviewHost;
    TSharedPtr<SWidget> ReviewPanel;
    TMap<FString, FCacheDirectory> CacheDirectories;
    FText CacheSizeText;
    FText CacheFeedback;
    bool bCacheHasHistory = false;
    bool bCacheClearArmed = false;
};
static TWeakPtr<SWorkbench> CurrentWorkbench;
}

namespace AssetForgeReview
{
void Open(const TArray<FString>& Args)
{
    FGlobalTabmanager::Get()->TryInvokeTab(AssetForgeEditor::GateTabName);
    if (const auto Panel = AssetForgeEditor::CurrentWorkbench.Pin())
    {
        Panel->Show(1);
        if (Args.Num() && (Args[0] == TEXT("scan") || Args[0] == TEXT("folders"))) Run(Args[0], FString());
    }
}

void OpenImported(const FString& Receipt)
{
    if (Receipt.IsEmpty()) return;
    Open({});
    Run(TEXT("imported"), Receipt);
}
}

void FAssetForgeEditorModule::StartupModule()
{
    RegisterStyle();
    FGlobalTabmanager::Get()->AddLegacyTabType(TEXT("AssetForge.AssetReview"), AssetForgeEditor::GateTabName);
    ReviewConsoleCommand = IConsoleManager::Get().RegisterConsoleCommand(TEXT("AssetForge.Review"), TEXT("Open the AssetForge asset review page."),
        FConsoleCommandWithArgsDelegate::CreateStatic(&AssetForgeReview::Open), ECVF_Default);

    const FSlateIcon GateIcon = StyleSet.IsValid()
        ? FSlateIcon(StyleSet->GetStyleSetName(), AssetForgeEditor::WorkbenchIconName)
        : FSlateIcon(FAppStyle::GetAppStyleSetName(), "Icons.Import");

    FGlobalTabmanager::Get()->RegisterNomadTabSpawner(AssetForgeEditor::GateTabName, FOnSpawnTab::CreateRaw(this, &FAssetForgeEditorModule::SpawnGateTab))
        .SetDisplayName(LOCTEXT("GateTabDisplayName", "AssetForge 工作台"))
        .SetTooltipText(LOCTEXT("GateTabTooltip", "打开包体导入和入库批审工作台。"))
        .SetIcon(GateIcon);

    IConsoleManager::Get().UnregisterConsoleObject(TEXT("AssetForge.OpenGate"), false);
    GateConsoleCommand = IConsoleManager::Get().RegisterConsoleCommand(
        TEXT("AssetForge.OpenGate"),
        TEXT("Open the DCC AssetForge import gate workbench."),
        FConsoleCommandDelegate::CreateRaw(this, &FAssetForgeEditorModule::OpenGateWorkbench),
        ECVF_Default
    );

    UToolMenus::RegisterStartupCallback(FSimpleMulticastDelegate::FDelegate::CreateRaw(this, &FAssetForgeEditorModule::RegisterMenus));
    UE_LOG(LogAssetForgeEditor, Display, TEXT("DCC AssetForge editor module ready. Gate tab: %s"), *AssetForgeEditor::GateTabName.ToString());
}

void FAssetForgeEditorModule::ShutdownModule()
{
    if (GateConsoleCommand)
    {
        IConsoleManager::Get().UnregisterConsoleObject(GateConsoleCommand);
        GateConsoleCommand = nullptr;
    }
    UnregisterMenus();
    if (ReviewConsoleCommand) IConsoleManager::Get().UnregisterConsoleObject(ReviewConsoleCommand);
    FGlobalTabmanager::Get()->UnregisterNomadTabSpawner(AssetForgeEditor::GateTabName);
    UnregisterStyle();
}

void FAssetForgeEditorModule::RegisterStyle()
{
    if (StyleSet.IsValid())
    {
        return;
    }

    const TSharedPtr<IPlugin> Plugin = IPluginManager::Get().FindPlugin(TEXT("AssetForge"));
    if (!Plugin.IsValid())
    {
        UE_LOG(LogAssetForgeEditor, Warning, TEXT("DCC AssetForge plugin descriptor was not found; falling back to default editor icons."));
        return;
    }

    StyleSet = MakeShared<FSlateStyleSet>(AssetForgeEditor::StyleSetName);
    StyleSet->SetContentRoot(FPaths::Combine(Plugin->GetBaseDir(), TEXT("Resources")));
    StyleSet->Set(AssetForgeEditor::WorkbenchIconName, new FSlateImageBrush(
        StyleSet->RootToContentDir(TEXT("Workbench/brand/af_shelf"), TEXT(".png")), FVector2D(20,20)));
    FSlateStyleRegistry::RegisterSlateStyle(*StyleSet);
}

void FAssetForgeEditorModule::UnregisterStyle()
{
    if (!StyleSet.IsValid())
    {
        return;
    }

    FSlateStyleRegistry::UnRegisterSlateStyle(*StyleSet);
    StyleSet.Reset();
}

void FAssetForgeEditorModule::RegisterMenus()
{
    FToolMenuOwnerScoped OwnerScoped(this);
    const FSlateIcon GateIcon = StyleSet.IsValid()
        ? FSlateIcon(StyleSet->GetStyleSetName(), AssetForgeEditor::WorkbenchIconName)
        : FSlateIcon(FAppStyle::GetAppStyleSetName(), "Icons.Import");

    UToolMenu* ToolsMenu = UToolMenus::Get()->ExtendMenu("LevelEditor.MainMenu.Tools");
    FToolMenuSection& MenuSection = ToolsMenu->FindOrAddSection("AssetForge");
    MenuSection.AddMenuEntry(
        "AssetForge.OpenGateWorkbench.Tools",
        LOCTEXT("OpenGateMenu", "AssetForge 工作台"),
        LOCTEXT("OpenGateMenuTooltip", "打开包体导入和入库批审工作台。"),
        GateIcon,
        FUIAction(FExecuteAction::CreateRaw(this, &FAssetForgeEditorModule::OpenGateWorkbench))
    );

    UToolMenu* WindowMenu = UToolMenus::Get()->ExtendMenu("LevelEditor.MainMenu.Window");
    FToolMenuSection& WindowSection = WindowMenu->FindOrAddSection("AssetForge");
    WindowSection.AddMenuEntry(
        "AssetForge.OpenGateWorkbench.Window",
        LOCTEXT("OpenGateWindowMenu", "AssetForge 工作台"),
        LOCTEXT("OpenGateWindowMenuTooltip", "打开包体导入和入库批审工作台。"),
        GateIcon,
        FUIAction(FExecuteAction::CreateRaw(this, &FAssetForgeEditorModule::OpenGateWorkbench))
    );

    UToolMenu* Toolbar = UToolMenus::Get()->ExtendMenu("LevelEditor.LevelEditorToolBar.User");
    FToolMenuSection& ToolbarSection = Toolbar->FindOrAddSection("AssetForge");
    ToolbarSection.AddEntry(FToolMenuEntry::InitToolBarButton(
        "AssetForge.OpenGateWorkbench.Toolbar",
        FUIAction(FExecuteAction::CreateRaw(this, &FAssetForgeEditorModule::OpenGateWorkbench)),
        LOCTEXT("OpenGateToolbar", "AssetForge 工作台"),
        LOCTEXT("OpenGateToolbarTooltip", "打开包体导入和入库批审工作台。"),
        GateIcon
    ));
}

void FAssetForgeEditorModule::UnregisterMenus()
{
    if (UToolMenus::IsToolMenuUIEnabled())
    {
        UToolMenus::UnregisterOwner(this);
    }
}

void FAssetForgeEditorModule::OpenGateWorkbench()
{
    const TSharedPtr<SDockTab> GateTab = FGlobalTabmanager::Get()->TryInvokeTab(AssetForgeEditor::GateTabName);
    if (GateTab.IsValid())
    {
        return;
    }

    UE_LOG(LogAssetForgeEditor, Error, TEXT("Failed to open DCC AssetForge gate workbench tab: %s"), *AssetForgeEditor::GateTabName.ToString());
}

TSharedRef<SDockTab> FAssetForgeEditorModule::SpawnGateTab(const FSpawnTabArgs& Args)
{
    const auto Workbench = SNew(AssetForgeEditor::SWorkbench);
    AssetForgeEditor::CurrentWorkbench = Workbench;
    return AssetForgeReview::CreateTab(Workbench);
}

IMPLEMENT_MODULE(FAssetForgeEditorModule, AssetForgeEditor)

#undef LOCTEXT_NAMESPACE
