#include "AssetForgeEditorModule.h"

#include "Brushes/SlateImageBrush.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Framework/Docking/TabManager.h"
#include "HAL/FileManager.h"
#include "HAL/IConsoleManager.h"
#include "HAL/PlatformMisc.h"
#include "HAL/PlatformProcess.h"
#include "Interfaces/IPluginManager.h"
#include "IPythonScriptPlugin.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "Styling/AppStyle.h"
#include "Styling/SlateStyle.h"
#include "Styling/SlateStyleRegistry.h"
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
#include "Widgets/SCompoundWidget.h"
#include "Widgets/Text/STextBlock.h"
#include "Widgets/Views/SListView.h"

#define LOCTEXT_NAMESPACE "AssetForgeEditor"

DEFINE_LOG_CATEGORY_STATIC(LogAssetForgeEditor, Log, All);

namespace AssetForgeEditor
{
static const FName GateTabName(TEXT("AssetForge.GateWorkbench"));
static const FName StyleSetName(TEXT("AssetForgeEditorStyle"));
static const FName ToolbarIconName(TEXT("AssetForge.ToolbarIcon"));
static const FName TabIconName(TEXT("AssetForge.TabIcon"));
static const FName HeaderIconName(TEXT("AssetForge.HeaderIcon"));
static const TCHAR* GateVersionLabel = TEXT("Asset Forge Gate v0.1.5");
static const TCHAR* GateBuildLabel = TEXT("Build 2026-06-03-R7");
static const TCHAR* DccPackageRootName = TEXT("dcc_packages");

struct FAssetForgePackageItem
{
    FString AssetName;
    FString SourceDcc;
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
    bool bReportCanImportKnown = false;
    bool bReportCanImport = false;
    int32 ReportWarningCount = 0;
    int32 ReportErrorCount = 0;
    int32 MeshCount = 0;
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
        if (!HasReport())
        {
            return TEXT("[待预检]");
        }
        if (bReportCanImportKnown && bReportCanImport)
        {
            return TEXT("[放行]");
        }
        if (bReportCanImportKnown && !bReportCanImport)
        {
            return TEXT("[阻断]");
        }
        if (ReportErrorCount > 0)
        {
            return TEXT("[阻断]");
        }
        if (ReportWarningCount > 0)
        {
            return TEXT("[警告]");
        }
        return TEXT("[已报告]");
    }

    FString RiskSummary() const
    {
        if (!HasReport())
        {
            return TEXT("风险：等待预检报告");
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
        return FString::Printf(TEXT("%s  |  %s  |  %s  |  更新 %s"), *DccLabel, *TargetLabel, *PackageIdentityLine(), *ModifiedTimeLabel());
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
            return TEXT("备注：暂无报告；先生成入审证据，再决定是否导入。");
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
            return FString::Printf(TEXT("Combine Meshes 未记录，真实 Static Mesh 数需等 UE 预演确认%s"), *DetailText);
        }
        const FString Base = bCombineMeshes
            ? TEXT("Combine Meshes 开启，UE 会把多个 FBX 节点合并为 1 个 Static Mesh")
            : TEXT("Combine Meshes 关闭，UE 按 FBX 源节点拆分导入");
        return Base + DetailText;
    }

    static FString TimeLabel(const FDateTime& Time)
    {
        return Time == FDateTime::MinValue() ? TEXT("未记录") : Time.ToString(TEXT("%Y-%m-%d %H:%M"));
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

static const FSlateBrush* AssetForgeBrush(const FName BrushName)
{
    if (const ISlateStyle* Style = FSlateStyleRegistry::FindSlateStyle(StyleSetName))
    {
        return Style->GetBrush(BrushName);
    }
    return FAppStyle::GetBrush("Icons.Import");
}

static TSharedRef<STextBlock> TextBlock(const TAttribute<FText>& Text, const FSlateColor& Color = FSlateColor::UseForeground())
{
    return SNew(STextBlock)
        .Text(Text)
        .Font(DetailFont())
        .ColorAndOpacity(Color);
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
                TextBlock(Value)
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

static TSharedRef<SWidget> StatusPill(const TAttribute<FText>& Text, const FLinearColor& Color)
{
    return SNew(SBorder)
        .BorderImage(FAppStyle::GetBrush("ToolPanel.DarkGroupBorder"))
        .Padding(FMargin(10.0f, 4.0f))
        [
            TextBlock(Text, Color)
        ];
}

static TSharedRef<SWidget> StatusPillDynamic(const TAttribute<FText>& Text, const TAttribute<FSlateColor>& Color)
{
    return SNew(SBorder)
        .BorderImage(FAppStyle::GetBrush("ToolPanel.DarkGroupBorder"))
        .Padding(FMargin(10.0f, 4.0f))
        [
            SNew(STextBlock)
            .Text(Text)
            .Font(DetailFont())
            .ColorAndOpacity(Color)
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
                    ? FSlateColor(FLinearColor(0.70f, 0.90f, 0.82f, 1.0f))
                    : FSlateColor(FLinearColor(0.50f, 0.56f, 0.60f, 1.0f));
            }))
        ];
}

static FLinearColor PackageRiskColor(const FAssetForgePackageItem& Item)
{
    if (!Item.HasReport())
    {
        return FLinearColor(0.55f, 0.65f, 0.72f, 1.0f);
    }
    if ((Item.bReportCanImportKnown && !Item.bReportCanImport) || Item.ReportErrorCount > 0)
    {
        return FLinearColor(1.0f, 0.34f, 0.30f, 1.0f);
    }
    if (Item.ReportWarningCount > 0 || !Item.bReportCanImportKnown)
    {
        return FLinearColor(1.0f, 0.72f, 0.28f, 1.0f);
    }
    return FLinearColor(0.40f, 0.88f, 0.56f, 1.0f);
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

static FString BuildGatePythonCommand(const FString& FunctionName, const FString& PackageDir, const FString& ImportOptionsJson = TEXT("{}"))
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
        TEXT("from asset_forge.unreal.editor_menu import %s as _asset_forge_gate_action\n")
        TEXT("_asset_forge_import_options = json.loads(%s)\n")
        TEXT("_asset_forge_report = _asset_forge_gate_action(%s, import_options=_asset_forge_import_options)\n")
        TEXT("print('ASSET_FORGE_GATE_RESULT=' + json.dumps({'status': _asset_forge_report.get('status', ''), 'report_path': _asset_forge_report.get('report_path', ''), 'gate_passed': _asset_forge_report.get('gate_passed', None)}, ensure_ascii=False))\n"),
        *PythonStringLiteral(PluginPythonRoot),
        *PythonStringLiteral(PluginPythonRoot),
        *FunctionName,
        *PythonStringLiteral(ImportOptionsJson),
        *PythonStringLiteral(PackageDir)
    );
    return FString::Printf(TEXT("exec(%s)"), *PythonStringLiteral(Script));
}

static FString ExecuteGatePythonCommand(const FString& FunctionName, const FString& PackageDir, const FString& ImportOptionsJson = TEXT("{}"))
{
    IPythonScriptPlugin* PythonPlugin = IPythonScriptPlugin::Get();
    if (!PythonPlugin || !PythonPlugin->IsPythonAvailable())
    {
        return TEXT("UE Python 不可用，无法执行门禁动作。");
    }

    FPythonCommandEx PythonCommand;
    PythonCommand.Command = BuildGatePythonCommand(FunctionName, PackageDir, ImportOptionsJson);
    PythonCommand.ExecutionMode = EPythonCommandExecutionMode::ExecuteFile;
    PythonCommand.FileExecutionScope = EPythonFileExecutionScope::Public;
    const bool bSuccess = PythonPlugin->ExecPythonCommandEx(PythonCommand);

    FString Output;
    for (const FPythonLogOutputEntry& Entry : PythonCommand.LogOutput)
    {
        if (!Output.IsEmpty())
        {
            Output += TEXT("\n");
        }
        Output += Entry.Output;
    }

    if (!bSuccess)
    {
        return FString::Printf(TEXT("门禁动作执行失败：%s"), Output.IsEmpty() ? *PythonCommand.CommandResult : *Output);
    }
    return Output.IsEmpty() ? TEXT("门禁动作已执行，查看 latest_unreal.log。") : Output;
}

static TSharedRef<SWidget> Section(const FText& Title, TSharedRef<SWidget> Body, bool InitiallyCollapsed = false)
{
    return SNew(SExpandableArea)
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
        return TEXT("报告未完成：请重新预检");
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
    if (Item.ReportDecisionLabel.IsEmpty())
    {
        Item.ReportDecisionLabel = DecisionLabelFromCode(Item.ReportDecision, Status, Item.bReportCanImportKnown, Item.bReportCanImport);
    }
    Item.LastImportStatus = Item.ReportDecisionLabel;
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

    TArray<FString> Reports;
    IFileManager::Get().FindFiles(Reports, *(Item->PackageDir / TEXT("*import_report.json")), true, false);
    if (Reports.Num() > 0)
    {
        Reports.Sort();
        Item->ImportReportPath = Item->PackageDir / Reports.Last();
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

static void FindManifestsRecursive(const FString& Directory, int32 Depth, TArray<FString>& OutManifestPaths)
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
            SNew(SBorder)
            .BorderImage(FAppStyle::GetBrush("ToolPanel.GroupBorder"))
            .Padding(FMargin(12.0f))
            [
                SNew(SVerticalBox)
                + SVerticalBox::Slot()
                .AutoHeight()
                [
                    BuildHeader()
                ]
                + SVerticalBox::Slot()
                .AutoHeight()
                .Padding(0.0f, 8.0f)
                [
                    SNew(SSeparator)
                ]
                + SVerticalBox::Slot()
                .FillHeight(1.0f)
                [
                    SNew(SSplitter)
                    + SSplitter::Slot()
                    .Value(0.34f)
                    [
                        BuildPackageColumn()
                    ]
                    + SSplitter::Slot()
                    .Value(0.66f)
                    [
                        BuildReviewColumn()
                    ]
                ]
            ]
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
    FString LastDebugExportPath;
    FDateTime LastRefreshTime = FDateTime::MinValue();
    FString GateMessage = TEXT("请先刷新包体列表；找到 AF 包体后选中一项，再执行预检或审批导入。");
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
    FString GateVertexColorImportOption = TEXT("replace");

    TSharedRef<SWidget> BuildHeader()
    {
        return SNew(SVerticalBox)
            + SVerticalBox::Slot()
            .AutoHeight()
            [
                SNew(SHorizontalBox)
                + SHorizontalBox::Slot()
                .AutoWidth()
                .Padding(0.0f, 0.0f, 12.0f, 0.0f)
                [
                    SNew(SBox)
                    .WidthOverride(56.0f)
                    .HeightOverride(56.0f)
                    [
                        SNew(SImage)
                        .Image(AssetForgeBrush(HeaderIconName))
                    ]
                ]
                + SHorizontalBox::Slot()
                .FillWidth(1.0f)
                [
                    SNew(SVerticalBox)
                    + SVerticalBox::Slot().AutoHeight()
                    [
                        SNew(STextBlock)
                        .Text(LOCTEXT("Title", "Asset Forge 导入门禁工作台"))
                        .Font(FAppStyle::GetFontStyle("DetailsView.CategoryFontStyle"))
                    ]
                    + SVerticalBox::Slot().AutoHeight()
                    [
                        TextBlock(LOCTEXT("Subtitle", "扫描 DCC 导出的 AF 包体，先核对网格、贴图、材质实例和目标路径，再审批导入。"), FSlateColor::UseSubduedForeground())
                    ]
                    + SVerticalBox::Slot().AutoHeight().Padding(0.0f, 4.0f, 0.0f, 0.0f)
                    [
                        TextBlock(TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetToolVersionText), FSlateColor(FLinearColor(0.55f, 0.65f, 0.72f, 1.0f)))
                    ]
                    + SVerticalBox::Slot().AutoHeight().Padding(0.0f, 2.0f, 0.0f, 0.0f)
                    [
                        TextBlock(TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetLastRefreshText), FSlateColor::UseSubduedForeground())
                    ]
                ]
                + SHorizontalBox::Slot()
                .AutoWidth()
                .VAlign(VAlign_Center)
                [
                    StatusPillDynamic(
                        TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetStatusText),
                        TAttribute<FSlateColor>::CreateSP(this, &SAssetForgeGatePanel::GetHeaderStatusColor)
                    )
                ]
            ]
            + SVerticalBox::Slot()
            .AutoHeight()
            .Padding(0.0f, 8.0f, 0.0f, 0.0f)
            [
                SNew(SSearchBox)
                .HintText(LOCTEXT("SearchHint", "搜索包体名 / DCC / 目标路径 / 材质规则"))
                .OnTextChanged(this, &SAssetForgeGatePanel::HandleSearchChanged)
            ];
    }

    TSharedRef<SWidget> BuildPackageColumn()
    {
        return SNew(SBorder)
            .BorderImage(FAppStyle::GetBrush("ToolPanel.GroupBorder"))
            .Padding(FMargin(8.0f))
            [
                SNew(SVerticalBox)
                + SVerticalBox::Slot().AutoHeight()
                [
                    Section(
                        LOCTEXT("ScanSection", "1 包体来源"),
                        SNew(SVerticalBox)
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("ScanRoot", "扫描目录"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetScanRootsText))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("Signal", "识别信号"), LOCTEXT("SignalValue", "manifest / source_dcc / schema_version / import_report"))]
                        + SVerticalBox::Slot().AutoHeight().Padding(0.0f, 8.0f, 0.0f, 0.0f)
                        [
                            SNew(SHorizontalBox)
                            + SHorizontalBox::Slot().FillWidth(1.0f)[CompactButton(LOCTEXT("Refresh", "刷新包体"), "Icons.Refresh", FOnClicked::CreateSP(this, &SAssetForgeGatePanel::HandleRefreshClicked))]
                            + SHorizontalBox::Slot().FillWidth(1.0f).Padding(6.0f, 0.0f)[CompactButton(LOCTEXT("ScanDir", "重新扫描"), "Icons.Search", FOnClicked::CreateSP(this, &SAssetForgeGatePanel::HandleRefreshClicked))]
                            + SHorizontalBox::Slot().FillWidth(1.0f).Padding(6.0f, 0.0f)[CompactButton(LOCTEXT("PreviewOldImportsCleanup", "预览清理候选"), "Icons.Search", FOnClicked::CreateSP(this, &SAssetForgeGatePanel::HandleCleanupClicked))]
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
                + SVerticalBox::Slot().AutoHeight()
                [
                    Section(
                        LOCTEXT("PackageSourceRecord", "1 来源记录"),
                        SNew(SVerticalBox)
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("PackageUpdatedAt", "包体时间"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetPackageTimeText))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("ReportUpdatedAt", "报告时间"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetReportTimeText))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("ManifestPath", "Manifest"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetManifestPath))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("PackageNote", "备注"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetPackageNoteText))],
                        true
                    )
                ]
                + SVerticalBox::Slot().AutoHeight().Padding(0.0f, 8.0f, 0.0f, 0.0f)
                [
                    Section(
                        LOCTEXT("PackageDetail", "2 包体画像"),
                        SNew(SVerticalBox)
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("SelectedPackage", "选中包体"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetSelectedAssetName))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("SelectedPackageState", "当前状态"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetSelectedPackageStateText))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("Dcc", "来源 DCC"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetSelectedSourceDcc))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("PackageNaming", "包体/版本"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetSelectedPackageNamingText))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("ProjectPreset", "项目预设"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetSelectedProjectPresetText))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("TargetPath", "UE 目标路径"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetSelectedTargetPath))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("PackageDir", "包体目录"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetSelectedPackageDir))]
                    )
                ]
                + SVerticalBox::Slot().AutoHeight().Padding(0.0f, 8.0f, 0.0f, 0.0f)
                [
                    Section(
                        LOCTEXT("AssetContent", "3 包内资产"),
                        SNew(SVerticalBox)
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("Mesh", "网格"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetMeshSummary))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("Textures", "贴图"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetTextureSummary))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("Materials", "材质实例"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetMaterialSummary))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("Schema", "Schema"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetSchemaSummary))]
                    )
                ]
                + SVerticalBox::Slot().AutoHeight().Padding(0.0f, 8.0f, 0.0f, 0.0f)
                [
                    Section(
                        LOCTEXT("ImportStrategySection", "4 导入策略"),
                        SNew(SVerticalBox)
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
                            PropertyRow(LOCTEXT("GateTransformGroup", "高级设置：变换 / 单位"), BuildTransformOptionRow())
                        ]
                        + SVerticalBox::Slot().AutoHeight()
                        [
                            PropertyRow(LOCTEXT("GateTransformOffsetGroup", "导入偏移"), BuildTransformOffsetOptionRow())
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
                        false
                    )
                ]
                + SVerticalBox::Slot().AutoHeight().Padding(0.0f, 8.0f, 0.0f, 0.0f)
                [
                    Section(
                        LOCTEXT("WriteApprovalSection", "5 入审与导入"),
                        SNew(SVerticalBox)
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("GateMessage", "门禁状态"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetGateMessage))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("FlowSummary", "流程阶段"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetFlowSummaryText))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("ApprovalIntent", "审批范围"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetApprovalIntentText))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("ApprovalStage", "按钮分层"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetApprovalStageText))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("WriteContentSummary", "写入内容"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetWriteContentSummaryText))]
                        + SVerticalBox::Slot().AutoHeight()[PropertyRow(LOCTEXT("NextAction", "下一步"), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetNextActionText))]
                        + SVerticalBox::Slot().AutoHeight().Padding(0.0f, 8.0f, 0.0f, 0.0f)
                        [
                            SNew(SHorizontalBox)
                            + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0.0f, 0.0f, 8.0f, 0.0f)[TextBlock(LOCTEXT("CheckLayer", "检查层"), FSlateColor::UseSubduedForeground())]
                            + SHorizontalBox::Slot().FillWidth(1.0f)[CompactButton(TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetPreviewButtonText), "Icons.Visibility", FOnClicked::CreateSP(this, &SAssetForgeGatePanel::HandlePreviewClicked), TAttribute<bool>::CreateSP(this, &SAssetForgeGatePanel::HasSelectedPackage), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetPreviewTooltipText))]
                        ]
                        + SVerticalBox::Slot().AutoHeight().Padding(0.0f, 6.0f, 0.0f, 0.0f)
                        [
                            SNew(SHorizontalBox)
                            + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0.0f, 0.0f, 8.0f, 0.0f)[TextBlock(LOCTEXT("PreviewLayer", "预演层"), FSlateColor::UseSubduedForeground())]
                            + SHorizontalBox::Slot().FillWidth(1.0f)[CompactButton(TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetDryRunButtonText), "Icons.Play", FOnClicked::CreateSP(this, &SAssetForgeGatePanel::HandleDryRunClicked), TAttribute<bool>::CreateSP(this, &SAssetForgeGatePanel::HasSelectedPackage), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetDryRunTooltipText))]
                        ]
                        + SVerticalBox::Slot().AutoHeight().Padding(0.0f, 6.0f, 0.0f, 0.0f)
                        [
                            SNew(SHorizontalBox)
                            + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0.0f, 0.0f, 8.0f, 0.0f)[TextBlock(LOCTEXT("WriteLayer", "写入层"), FSlateColor::UseSubduedForeground())]
                            + SHorizontalBox::Slot().FillWidth(1.0f)[CompactButton(TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetImportButtonText), "Icons.Import", FOnClicked::CreateSP(this, &SAssetForgeGatePanel::HandleImportClicked), TAttribute<bool>::CreateSP(this, &SAssetForgeGatePanel::CanImportSelectedPackage), TAttribute<FText>::CreateSP(this, &SAssetForgeGatePanel::GetImportTooltipText))]
                        ]
                    )
                ]
                + SVerticalBox::Slot().AutoHeight().Padding(0.0f, 8.0f, 0.0f, 0.0f)
                [
                    Section(
                        LOCTEXT("HistorySection", "6 历史与报告"),
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
                                    TAttribute<FText>(LOCTEXT("OpenReport", "打开报告")),
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
                        ]
                    )
                ]
            ];
    }

    TSharedRef<ITableRow> MakePackageRow(TSharedPtr<FAssetForgePackageItem> Item, const TSharedRef<STableViewBase>& OwnerTable)
    {
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
                        .AutoWidth()
                        .VAlign(VAlign_Center)
                        .Padding(4.0f, 0.0f, 8.0f, 0.0f)
                        [
                            StatusPill(
                                TAttribute<FText>(FText::FromString(Item.IsValid() ? Item->StatePrefix().Replace(TEXT("["), TEXT("")).Replace(TEXT("]"), TEXT("")) : TEXT("未选择"))),
                                Item.IsValid() ? PackageRiskColor(*Item) : FLinearColor(0.55f, 0.65f, 0.72f, 1.0f)
                            )
                        ]
                        + SHorizontalBox::Slot()
                        .FillWidth(1.0f)
                        .VAlign(VAlign_Center)
                        [
                            SNew(SButton)
                            .ButtonStyle(FAppStyle::Get(), "SimpleButton")
                            .ContentPadding(FMargin(0.0f))
                            .ToolTipText(LOCTEXT("SelectPackageBody", "选择包体；右侧会显示来源记录、包内资产和导入策略"))
                            .OnClicked(this, &SAssetForgeGatePanel::HandlePackageRowSelect, Item)
                            [
                                SNew(SVerticalBox)
                                + SVerticalBox::Slot().AutoHeight()
                                [
                                    TextBlock(
                                        FText::FromString(Item.IsValid() ? Item->AssetName : TEXT("")),
                                        Item.IsValid() ? FSlateColor(PackageRiskColor(*Item)) : FSlateColor::UseForeground()
                                    )
                                ]
                                + SVerticalBox::Slot().AutoHeight().Padding(0.0f, 2.0f, 0.0f, 0.0f)
                                [
                                    TextBlock(
                                        FText::FromString(Item.IsValid() ? Item->ListCompactMetaLabel() : TEXT("")),
                                        FSlateColor::UseSubduedForeground()
                                    )
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
        if (PackageListView.IsValid())
        {
            PackageListView->RequestListRefresh();
        }
        GateMessage = Item.IsValid()
            ? FString::Printf(TEXT("已选择 %s。右侧已显示来源记录、包内资产和导入策略；下一步建议先预检。"), *Item->AssetName)
            : TEXT("请先在左侧选择一个 AF 包体。");
    }

    FReply HandlePackageRowSelect(TSharedPtr<FAssetForgePackageItem> Item)
    {
        if (!Item.IsValid())
        {
            return FReply::Handled();
        }
        SelectedPackage = Item;
        GateMessage = FString::Printf(TEXT("已选择 %s。右侧来源记录和导入策略已刷新。"), *Item->AssetName);
        if (PackageListView.IsValid())
        {
            PackageListView->SetSelection(Item);
            PackageListView->RequestListRefresh();
        }
        return FReply::Handled();
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

    FReply HandleCleanupClicked()
    {
        const FString TargetPackageDir = SelectedPackage.IsValid() ? SelectedPackage->PackageDir : FString();
        GateMessage = ExecuteGatePythonCommand(TEXT("preview_generated_props_cleanup"), TargetPackageDir, BuildGateImportOptionsJson());
        RefreshPackages();
        if (PackageListView.IsValid())
        {
            PackageListView->RequestListRefresh();
        }
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
        if (!SelectedPackage.IsValid())
        {
            GateMessage = TEXT("未选择包体，无法预检。请先在左侧包体列表选中一项。");
            return FReply::Handled();
        }
        GateMessage = ExecuteGatePythonCommand(TEXT("preview_gate_for_package_dir"), SelectedPackage->PackageDir, BuildGateImportOptionsJson());
        return FReply::Handled();
    }

    FReply HandleDryRunClicked()
    {
        if (!SelectedPackage.IsValid())
        {
            GateMessage = TEXT("未选择包体，无法导入预演。请先在左侧包体列表选中一项。");
            return FReply::Handled();
        }
        GateMessage = ExecuteGatePythonCommand(TEXT("dry_run_gate_for_package_dir"), SelectedPackage->PackageDir, BuildGateImportOptionsJson());
        return FReply::Handled();
    }

    FReply HandleImportClicked()
    {
        if (!CanImportSelectedPackage())
        {
            GateMessage = TEXT("当前包体未被报告放行，无法正式导入。请先生成入审报告，并按报告修复阻断项。");
            return FReply::Handled();
        }
        GateMessage = ExecuteGatePythonCommand(TEXT("import_approved_package_dir"), SelectedPackage->PackageDir, BuildGateImportOptionsJson());
        return FReply::Handled();
    }

    FReply HandleOpenReportClicked()
    {
        if (!SelectedPackage.IsValid() || SelectedPackage->ImportReportPath.IsEmpty())
        {
            GateMessage = TEXT("当前包体还没有可打开的报告；请先执行预检或导入预演。");
            return FReply::Handled();
        }
        if (!FPaths::FileExists(SelectedPackage->ImportReportPath))
        {
            GateMessage = FString::Printf(TEXT("报告文件不存在：%s"), *SelectedPackage->ImportReportPath);
            return FReply::Handled();
        }
        FPlatformProcess::LaunchFileInDefaultExternalApplication(*SelectedPackage->ImportReportPath);
        GateMessage = FString::Printf(TEXT("已打开报告：%s"), *SelectedPackage->ImportReportPath);
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
        Lines.Add(FString::Printf(TEXT("%s | %s"), GateVersionLabel, GateBuildLabel));
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
        ScanRoots = CollectExportRoots();
        Packages.Reset();
        History.Reset();

        TArray<FString> Manifests;
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
        GateMessage = SelectedPackage.IsValid()
            ? FString::Printf(TEXT("已扫描到 %d 个 AF 包体，并恢复选中 %s。请先检查，再按报告结果导入。"), Packages.Num(), *SelectedPackage->AssetName)
            : (FilteredPackages.Num() > 0
                ? FString::Printf(TEXT("已扫描到 %d 个 AF 包体；请在左侧明确选择一个包体后再检查或导入。"), Packages.Num())
                : TEXT("未扫描到 AF 包体：请确认 Maya 导出已完成，或设置 ASSET_FORGE_EXPORT_ROOT 指向导出目录。"));
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
            TEXT("显示 %d / 已发现 %d 个包体 | 放行 %d / 警告 %d / 阻断 %d / 待预检 %d"),
            FilteredPackages.Num(),
            Packages.Num(),
            ReadyCount,
            WarningCount,
            BlockedCount,
            WaitingCount
        );
    }

    FSlateColor GetHeaderStatusColor() const
    {
        if (SelectedPackage.IsValid())
        {
            return FSlateColor(PackageRiskColor(*SelectedPackage));
        }
        if (Packages.Num() > 0 && FilteredPackages.Num() == 0)
        {
            return FSlateColor(FLinearColor(1.0f, 0.72f, 0.28f, 1.0f));
        }
        return FSlateColor(FLinearColor(0.55f, 0.65f, 0.72f, 1.0f));
    }

    FText GetToolVersionText() const
    {
        return FText::FromString(FString::Printf(TEXT("%s | %s"), GateVersionLabel, GateBuildLabel));
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
        return FText::FromString(ScanRoots.Num() > 0 ? FString::Join(ScanRoots, TEXT(" | ")) : TEXT("未发现可扫描目录；请设置 ASSET_FORGE_EXPORT_ROOT 或检查 AssetForgeReports。"));
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
        return SNew(SBox)
            .MinDesiredWidth(520.0f)
            [
                TextBlock(LOCTEXT("GateBasicImportSummary", "默认导入 Static Mesh；FBX 自动材质/贴图保持关闭，由 Asset Forge 统一创建材质实例、导入贴图并绑定 slot。"), FSlateColor::UseSubduedForeground())
            ];
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
        return SNew(SHorizontalBox)
            + SHorizontalBox::Slot().AutoWidth()[SNew(SCheckBox).IsChecked(TAttribute<ECheckBoxState>::CreateSP(this, &SAssetForgeGatePanel::IsGateConvertSceneChecked)).OnCheckStateChanged(this, &SAssetForgeGatePanel::OnGateConvertSceneChanged).IsEnabled(TAttribute<bool>::CreateSP(this, &SAssetForgeGatePanel::HasSelectedPackage))]
            + SHorizontalBox::Slot().AutoWidth().Padding(4.0f, 0.0f, 18.0f, 0.0f)[TextBlock(LOCTEXT("GateConvertScene", "转换场景"))]
            + SHorizontalBox::Slot().AutoWidth()[SNew(SCheckBox).IsChecked(TAttribute<ECheckBoxState>::CreateSP(this, &SAssetForgeGatePanel::IsGateForceFrontXAxisChecked)).OnCheckStateChanged(this, &SAssetForgeGatePanel::OnGateForceFrontXAxisChanged).IsEnabled(TAttribute<bool>::CreateSP(this, &SAssetForgeGatePanel::HasSelectedPackage))]
            + SHorizontalBox::Slot().AutoWidth().Padding(4.0f, 0.0f, 18.0f, 0.0f)[TextBlock(LOCTEXT("GateForceFrontXAxis", "强制 X 前向"))]
            + SHorizontalBox::Slot().AutoWidth()[SNew(SCheckBox).IsChecked(TAttribute<ECheckBoxState>::CreateSP(this, &SAssetForgeGatePanel::IsGateConvertSceneUnitChecked)).OnCheckStateChanged(this, &SAssetForgeGatePanel::OnGateConvertSceneUnitChanged).IsEnabled(TAttribute<bool>::CreateSP(this, &SAssetForgeGatePanel::HasSelectedPackage))]
            + SHorizontalBox::Slot().AutoWidth().Padding(4.0f, 0.0f, 18.0f, 0.0f)[TextBlock(LOCTEXT("GateConvertSceneUnit", "转换单位"))]
            + SHorizontalBox::Slot().AutoWidth().Padding(0.0f, 0.0f, 4.0f, 0.0f).VAlign(VAlign_Center)[TextBlock(LOCTEXT("GateImportUniformScaleInline", "统一缩放"))]
            + SHorizontalBox::Slot().AutoWidth().Padding(0.0f, 0.0f, 18.0f, 0.0f)[BuildImportUniformScaleWidget()]
            + SHorizontalBox::Slot().AutoWidth()[SNew(SCheckBox).IsChecked(TAttribute<ECheckBoxState>::CreateSP(this, &SAssetForgeGatePanel::IsGateTransformVertexToAbsoluteChecked)).OnCheckStateChanged(this, &SAssetForgeGatePanel::OnGateTransformVertexToAbsoluteChanged).IsEnabled(TAttribute<bool>::CreateSP(this, &SAssetForgeGatePanel::HasSelectedPackage))]
            + SHorizontalBox::Slot().AutoWidth().Padding(4.0f, 0.0f, 18.0f, 0.0f)[TextBlock(LOCTEXT("GateTransformVertexToAbsolute", "顶点转绝对坐标"))]
            + SHorizontalBox::Slot().AutoWidth()[SNew(SCheckBox).IsChecked(TAttribute<ECheckBoxState>::CreateSP(this, &SAssetForgeGatePanel::IsGateBakePivotInVertexChecked)).OnCheckStateChanged(this, &SAssetForgeGatePanel::OnGateBakePivotInVertexChanged).IsEnabled(TAttribute<bool>::CreateSP(this, &SAssetForgeGatePanel::HasSelectedPackage))]
            + SHorizontalBox::Slot().AutoWidth().Padding(4.0f, 0.0f, 0.0f, 0.0f)[TextBlock(LOCTEXT("GateBakePivotInVertex", "烘焙 Pivot"))];
    }

    TSharedRef<SWidget> BuildTransformOffsetOptionRow()
    {
        return SNew(SHorizontalBox)
            + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)[TextBlock(LOCTEXT("GateImportTranslationLabel", "平移 XYZ"))]
            + SHorizontalBox::Slot().AutoWidth().Padding(6.0f, 0.0f, 4.0f, 0.0f)[BuildTransformNumberEntry(0, true)]
            + SHorizontalBox::Slot().AutoWidth().Padding(0.0f, 0.0f, 4.0f, 0.0f)[BuildTransformNumberEntry(1, true)]
            + SHorizontalBox::Slot().AutoWidth().Padding(0.0f, 0.0f, 16.0f, 0.0f)[BuildTransformNumberEntry(2, true)]
            + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)[TextBlock(LOCTEXT("GateImportRotationLabel", "旋转 P/Y/R"))]
            + SHorizontalBox::Slot().AutoWidth().Padding(6.0f, 0.0f, 4.0f, 0.0f)[BuildTransformNumberEntry(0, false)]
            + SHorizontalBox::Slot().AutoWidth().Padding(0.0f, 0.0f, 4.0f, 0.0f)[BuildTransformNumberEntry(1, false)]
            + SHorizontalBox::Slot().AutoWidth()[BuildTransformNumberEntry(2, false)];
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

    bool HasSelectedPackage() const { return SelectedPackage.IsValid(); }
    bool HasSelectedReport() const { return SelectedPackage.IsValid() && !SelectedPackage->ImportReportPath.IsEmpty(); }
    bool CanImportSelectedPackage() const
    {
        return SelectedPackage.IsValid()
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
            return LOCTEXT("CombineMeshesUnknown", "未记录；预演时按项目默认值确认");
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
        if (SelectedPackage.IsValid() && !SelectedPackage->ImportReportPath.IsEmpty())
        {
            return FText::FromString(FString::Printf(TEXT("入审报告：%s"), *ReportDecisionLine(*SelectedPackage)));
        }
        return FText::FromString(GateMessage);
    }
    FText GetApprovalIntentText() const { return SelectedPackage.IsValid() ? LOCTEXT("ApprovalIntentSelected", "仅审批当前选中包体；不会自动导入“最近导出包”，也不会影响列表中的其他包体。") : LOCTEXT("ApprovalIntentEmpty", "选择包体后才进入审批；当前不会执行任何导入动作。"); }
    FText GetApprovalStageText() const { return SelectedPackage.IsValid() ? LOCTEXT("ApprovalStageSelected", "检查层只生成入审报告；预演层按当前设置生成 dry-run 计划但不写资产；写入层只导入当前选中包体。") : LOCTEXT("ApprovalStageEmpty", "未选择包体时检查、预演与写入都保持禁用。"); }
    FText GetWriteContentSummaryText() const
    {
        if (!SelectedPackage.IsValid())
        {
            return LOCTEXT("WriteContentSummaryEmpty", "未选择包体；不会写入任何 UE 资产。");
        }

        const FString MaterialState = bGateImportMaterials ? TEXT("创建 AF 材质实例并绑定 slot") : TEXT("跳过 AF 材质实例和 slot 绑定");
        const FString TextureState = bGateImportTextures ? TEXT("导入 AF 打包贴图") : TEXT("跳过 AF 打包贴图");
        return FText::FromString(FString::Printf(TEXT("正式导入只写入当前选中包体；Static Mesh 始终导入；%s；%s；UE FBX 自动材质/贴图导入保持关闭。"), *MaterialState, *TextureState));
    }
    FText GetFlowSummaryText() const
    {
        if (!SelectedPackage.IsValid())
        {
            return LOCTEXT("FlowSummaryEmpty", "包体选择：未选择 -> 入审报告：等待 -> 导入预演：禁用 -> 正式导入：禁用");
        }
        if (!SelectedPackage->HasReport())
        {
            return LOCTEXT("FlowSummaryNoReport", "包体选择：已选择 -> 入审报告：未生成 -> 导入预演：可复核 -> 正式导入：等待报告");
        }
        if (SelectedPackage->bReportCanImportKnown && SelectedPackage->bReportCanImport)
        {
            return LOCTEXT("FlowSummaryReady", "包体选择：已选择 -> 入审报告：已放行 -> 导入预演：可复核 -> 正式导入：可执行");
        }
        if ((SelectedPackage->bReportCanImportKnown && !SelectedPackage->bReportCanImport) || SelectedPackage->ReportErrorCount > 0)
        {
            return LOCTEXT("FlowSummaryBlocked", "包体选择：已选择 -> 入审报告：阻断 -> 导入预演：用于复查 -> 正式导入：禁止");
        }
        return LOCTEXT("FlowSummaryReview", "包体选择：已选择 -> 入审报告：需复核 -> 导入预演：先复核 -> 正式导入：等待判断");
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
                return LOCTEXT("NextActionReportReady", "报告已放行；确认当前包体无误后，可正式导入选中包体。");
            }
            if ((SelectedPackage->bReportCanImportKnown && !SelectedPackage->bReportCanImport) || SelectedPackage->ReportErrorCount > 0)
            {
                if (!SelectedPackage->ReportNextAction.IsEmpty())
                {
                    return FText::FromString(FString::Printf(TEXT("报告阻断：%s"), *SelectedPackage->ReportNextAction));
                }
                return LOCTEXT("NextActionReportBlocked", "报告未放行；修复阻断项后重新预检。");
            }
            if (!SelectedPackage->ReportNextAction.IsEmpty())
            {
                return FText::FromString(FString::Printf(TEXT("报告待判定：%s"), *SelectedPackage->ReportNextAction));
            }
            return LOCTEXT("NextActionReportReview", "报告已生成但未记录导入许可；请复核报告后再决定是否导入。");
        }
        return LOCTEXT("NextActionSelected", "已选择包体但暂无报告；先生成入审报告，再预演导入计划，最后按报告结果正式导入。");
    }
    FText GetPreviewButtonText() const { return SelectedPackage.IsValid() ? LOCTEXT("PreviewSelectedPackage", "生成入审报告") : LOCTEXT("PreviewNeedsPackage", "先选择包体"); }
    FText GetDryRunButtonText() const { return SelectedPackage.IsValid() ? LOCTEXT("DryRunSelectedPackage", "预演导入计划（不写入）") : LOCTEXT("DryRunNeedsPackage", "先选择包体"); }
    FText GetImportButtonText() const { return SelectedPackage.IsValid() ? LOCTEXT("ImportSelectedPackage", "正式导入选中包体") : LOCTEXT("ImportNeedsPackage", "等待包体选择"); }
    FText GetPreviewTooltipText() const { return SelectedPackage.IsValid() ? LOCTEXT("PreviewTooltipSelected", "检查包体结构、风险和目标路径，生成入审报告；不创建 UE 资产。") : LOCTEXT("PreviewTooltipEmpty", "左侧选择 AF 包体后才能生成入审报告。"); }
    FText GetDryRunTooltipText() const { return SelectedPackage.IsValid() ? LOCTEXT("DryRunTooltipSelected", "按当前导入选项生成 dry-run 计划；验证 FBX、贴图、材质实例和目标路径，但不创建 UE 资产。") : LOCTEXT("DryRunTooltipEmpty", "左侧选择 AF 包体后才能预演导入计划。"); }
    FText GetImportTooltipText() const
    {
        if (!SelectedPackage.IsValid())
        {
            return LOCTEXT("ImportTooltipEmpty", "选择包体并完成检查后再导入。");
        }
        if (!SelectedPackage->HasReport())
        {
            return LOCTEXT("ImportTooltipNoReport", "当前包体还没有报告；先生成入审报告。");
        }
        if (!CanImportSelectedPackage())
        {
            return LOCTEXT("ImportTooltipBlocked", "当前报告未放行或仍有错误，正式导入已禁用。");
        }
        return LOCTEXT("ImportTooltipSelected", "报告已放行；只导入当前选中包体。");
    }
    FText GetOpenReportTooltipText() const { return HasSelectedReport() ? LOCTEXT("OpenReportTooltipReady", "用系统默认程序打开当前包体的入审报告。") : LOCTEXT("OpenReportTooltipEmpty", "当前包体还没有报告；先生成入审报告或预演导入计划。"); }
    FText GetHistorySummary() const
    {
        if (SelectedPackage.IsValid() && !SelectedPackage->ImportReportPath.IsEmpty())
        {
            return FText::FromString(FString::Printf(TEXT("%s | %s：%s"), *SelectedPackage->ReportTimeLabel(), *SelectedPackage->AssetName, *ReportDecisionLine(*SelectedPackage)));
        }
        return FText::FromString(History.Num() > 0 ? *History[0] : TEXT("暂无导入记录；正式导入完成后这里显示最近结果。"));
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
        return LOCTEXT("ReportStateEmpty", "暂无报告；先执行预检，报告会写入包体目录。");
    }
    FText GetReportPath() const { return FText::FromString(SelectedPackage.IsValid() && !SelectedPackage->ImportReportPath.IsEmpty() ? SelectedPackage->ImportReportPath : TEXT("选择包体并执行预检后生成报告")); }
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
        return LOCTEXT("ReportRiskEmpty", "暂无报告；先预检后显示警告与阻断计数");
    }
};
}

void FAssetForgeEditorModule::StartupModule()
{
    RegisterStyle();

    const FSlateIcon GateIcon = StyleSet.IsValid()
        ? FSlateIcon(StyleSet->GetStyleSetName(), AssetForgeEditor::TabIconName)
        : FSlateIcon(FAppStyle::GetAppStyleSetName(), "Icons.Import");

    FGlobalTabmanager::Get()->RegisterNomadTabSpawner(AssetForgeEditor::GateTabName, FOnSpawnTab::CreateRaw(this, &FAssetForgeEditorModule::SpawnGateTab))
        .SetDisplayName(LOCTEXT("GateTabDisplayName", "Asset Forge 导入门禁"))
        .SetTooltipText(LOCTEXT("GateTabTooltip", "打开 Asset Forge 导出包扫描、预检、审批和导入历史工作台。"))
        .SetIcon(GateIcon);

    IConsoleManager::Get().UnregisterConsoleObject(TEXT("AssetForge.OpenGate"), false);
    GateConsoleCommand = IConsoleManager::Get().RegisterConsoleCommand(
        TEXT("AssetForge.OpenGate"),
        TEXT("Open the Asset Forge import gate workbench."),
        FConsoleCommandDelegate::CreateRaw(this, &FAssetForgeEditorModule::OpenGateWorkbench),
        ECVF_Default
    );

    UToolMenus::RegisterStartupCallback(FSimpleMulticastDelegate::FDelegate::CreateRaw(this, &FAssetForgeEditorModule::RegisterMenus));
    UE_LOG(LogAssetForgeEditor, Display, TEXT("Asset Forge editor module ready. Gate tab: %s"), *AssetForgeEditor::GateTabName.ToString());
}

void FAssetForgeEditorModule::ShutdownModule()
{
    if (GateConsoleCommand)
    {
        IConsoleManager::Get().UnregisterConsoleObject(GateConsoleCommand);
        GateConsoleCommand = nullptr;
    }
    UnregisterMenus();
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
        UE_LOG(LogAssetForgeEditor, Warning, TEXT("Asset Forge plugin descriptor was not found; falling back to default editor icons."));
        return;
    }

    StyleSet = MakeShared<FSlateStyleSet>(AssetForgeEditor::StyleSetName);
    StyleSet->SetContentRoot(FPaths::Combine(Plugin->GetBaseDir(), TEXT("Resources")));
    StyleSet->Set(AssetForgeEditor::ToolbarIconName, new FSlateImageBrush(StyleSet->RootToContentDir(TEXT("IconToolbar"), TEXT(".png")), FVector2D(40.0f, 40.0f)));
    StyleSet->Set(AssetForgeEditor::TabIconName, new FSlateImageBrush(StyleSet->RootToContentDir(TEXT("IconToolbar"), TEXT(".png")), FVector2D(20.0f, 20.0f)));
    StyleSet->Set(AssetForgeEditor::HeaderIconName, new FSlateImageBrush(StyleSet->RootToContentDir(TEXT("IconHeader"), TEXT(".png")), FVector2D(56.0f, 56.0f)));
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
        ? FSlateIcon(StyleSet->GetStyleSetName(), AssetForgeEditor::ToolbarIconName)
        : FSlateIcon(FAppStyle::GetAppStyleSetName(), "Icons.Import");

    UToolMenu* ToolsMenu = UToolMenus::Get()->ExtendMenu("LevelEditor.MainMenu.Tools");
    FToolMenuSection& MenuSection = ToolsMenu->FindOrAddSection("AssetForge");
    MenuSection.AddMenuEntry(
        "AssetForge.OpenGateWorkbench.Tools",
        LOCTEXT("OpenGateMenu", "Asset Forge 导入门禁工作台"),
        LOCTEXT("OpenGateMenuTooltip", "打开 Asset Forge 导出包扫描、预检、审批和导入历史工作台。"),
        GateIcon,
        FUIAction(FExecuteAction::CreateRaw(this, &FAssetForgeEditorModule::OpenGateWorkbench))
    );

    UToolMenu* WindowMenu = UToolMenus::Get()->ExtendMenu("LevelEditor.MainMenu.Window");
    FToolMenuSection& WindowSection = WindowMenu->FindOrAddSection("AssetForge");
    WindowSection.AddMenuEntry(
        "AssetForge.OpenGateWorkbench.Window",
        LOCTEXT("OpenGateWindowMenu", "Asset Forge 导入门禁工作台"),
        LOCTEXT("OpenGateWindowMenuTooltip", "打开 Asset Forge 导出包扫描、预检、审批和导入历史工作台。"),
        GateIcon,
        FUIAction(FExecuteAction::CreateRaw(this, &FAssetForgeEditorModule::OpenGateWorkbench))
    );

    UToolMenu* Toolbar = UToolMenus::Get()->ExtendMenu("LevelEditor.LevelEditorToolBar.User");
    FToolMenuSection& ToolbarSection = Toolbar->FindOrAddSection("AssetForge");
    ToolbarSection.AddEntry(FToolMenuEntry::InitToolBarButton(
        "AssetForge.OpenGateWorkbench.Toolbar",
        FUIAction(FExecuteAction::CreateRaw(this, &FAssetForgeEditorModule::OpenGateWorkbench)),
        LOCTEXT("OpenGateToolbar", "AF 门禁"),
        LOCTEXT("OpenGateToolbarTooltip", "打开 Asset Forge 导入门禁工作台。"),
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
        UE_LOG(LogAssetForgeEditor, Display, TEXT("Asset Forge gate workbench opened."));
        return;
    }

    UE_LOG(LogAssetForgeEditor, Error, TEXT("Failed to open Asset Forge gate workbench tab: %s"), *AssetForgeEditor::GateTabName.ToString());
}

TSharedRef<SDockTab> FAssetForgeEditorModule::SpawnGateTab(const FSpawnTabArgs& Args)
{
    return SNew(SDockTab)
        .TabRole(ETabRole::NomadTab)
        [
            SNew(AssetForgeEditor::SAssetForgeGatePanel)
        ];
}

IMPLEMENT_MODULE(FAssetForgeEditorModule, AssetForgeEditor)

#undef LOCTEXT_NAMESPACE
