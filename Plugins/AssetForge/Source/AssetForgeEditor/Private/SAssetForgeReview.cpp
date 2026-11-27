#include "SAssetForgeReview.h"
#include "SAssetForgeReviewAnnotationEditor.h"
#include "AssetRegistry/AssetRegistryModule.h"
#include "Brushes/SlateRoundedBoxBrush.h"
#include "ContentBrowserModule.h"
#include "IContentBrowserSingleton.h"
#include "HAL/PlatformApplicationMisc.h"
#include "Widgets/Layout/SWrapBox.h"
#include "Framework/MultiBox/MultiBoxBuilder.h"

#include "Dom/JsonObject.h"
#include "Framework/Application/SlateApplication.h"
#include "Framework/Docking/TabManager.h"
#include "Framework/Notifications/NotificationManager.h"
#include "HAL/IConsoleManager.h"
#include "IPythonScriptPlugin.h"
#include "Misc/Base64.h"
#include "Misc/PackageName.h"
#include "Misc/Paths.h"
#include "Modules/ModuleManager.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Styling/AppStyle.h"
#include "Styling/StyleColors.h"
#include "UObject/SoftObjectPath.h"
#include "Widgets/Docking/SDockTab.h"
#include "Widgets/Images/SImage.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Input/SComboButton.h"
#include "Widgets/Input/SNumericEntryBox.h"
#include "Widgets/Input/SSearchBox.h"
#include "Widgets/Layout/SExpandableArea.h"
#include "Widgets/Layout/SSeparator.h"
#include "Widgets/Notifications/SNotificationList.h"
#include "Widgets/Views/SListView.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/Layout/SSplitter.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SCompoundWidget.h"
#include "Widgets/Text/STextBlock.h"

namespace AssetForgeReview
{
namespace
{
using FObject = TSharedPtr<FJsonObject>;

FString Str(FObject Data, const TCHAR* Name)
{
    FString Result;
    if (Data) { Data->TryGetStringField(Name, Result); }
    return Result;
}

TArray<FObject> Items(FObject Data, const TCHAR* Name)
{
    TArray<FObject> Result;
    const TArray<TSharedPtr<FJsonValue>>* Values;
    if (Data && Data->TryGetArrayField(Name, Values))
    {
        for (const auto& Value : *Values) { Result.Add(Value->AsObject()); }
    }
    return Result;
}

TSharedRef<STextBlock> Label(const FString& Text, FName Style = "NormalText")
{
    return SNew(STextBlock).Text(FText::FromString(Text)).TextStyle(&FAppStyle::Get(), Style).AutoWrapText(true);
}

TSharedRef<SWidget> Icon(FName Brush, float Size = 16)
{
    return SNew(SBox).WidthOverride(Size).HeightOverride(Size)
        [SNew(SImage).Image(FAppStyle::GetBrush(Brush))];
}

TSharedRef<SWidget> ActionLabel(const FString& Caption, FName Brush)
{
    return SNew(SHorizontalBox)
        + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0,0,5,0)[Icon(Brush)]
        + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)[SNew(STextBlock).Text(FText::FromString(Caption))];
}

TSharedRef<SWidget> StatusLabel(const FString& Caption, const FString& Status)
{
    FName Brush = "Icons.Info";
    if (Status == TEXT("pass")) Brush = "Icons.SuccessWithColor";
    else if (Status == TEXT("fixable") || Status == TEXT("warning")) Brush = "Icons.WarningWithColor";
    else if (Status == TEXT("blocked")) Brush = "Icons.ErrorWithColor";
    return ActionLabel(Caption, Brush);
}

FString Leaf(const FString& Path) { return FPaths::GetCleanFilename(Path); }

class SReviewWorkbench : public SCompoundWidget
{
public:
    SLATE_BEGIN_ARGS(SReviewWorkbench) {}
    SLATE_END_ARGS()

    void Construct(const FArguments&)
    {
        SetTag(TEXT("AssetForge.Review.Panel"));
        SetCanTick(true);
        ChildSlot
        [SNew(SVerticalBox)
            + SVerticalBox::Slot().AutoHeight()[Toolbar()]
            + SVerticalBox::Slot().AutoHeight()[SNew(SSeparator)]
            + SVerticalBox::Slot().FillHeight(1)
            [SNew(SSplitter)
                + SSplitter::Slot().Value(.31f).MinSize(185)
                [SNew(SBorder).BorderImage(FAppStyle::GetBrush("ToolPanel.GroupBorder")).Padding(5)
                    .Visibility_Lambda([this](){return bNarrow && bDetailPage ? EVisibility::Collapsed : EVisibility::Visible;})
                    [SNew(SVerticalBox)
                        + SVerticalBox::Slot().AutoHeight().Padding(4,4,4,8)
                        [SNew(SHorizontalBox)
                            + SHorizontalBox::Slot().FillWidth(1)[Label(TEXT("批次资产"), "DetailsView.CategoryTextStyle")]
                            + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)[SAssignNew(ListTitle,STextBlock).TextStyle(&FAppStyle::Get(), "SmallText.Subdued")]
                            + SHorizontalBox::Slot().AutoWidth().Padding(3,0,0,0)
                            [SNew(SButton).Tag(TEXT("Review.NewGroup")).ButtonStyle(FAppStyle::Get(),"SimpleButton").ContentPadding(3)
                                .ToolTipText(FText::FromString(TEXT("新建分组"))).IsEnabled_Lambda([this](){return !Str(State,TEXT("selected")).IsEmpty();})
                                .OnClicked_Lambda([this](){EditAnnotation(false);return FReply::Handled();})[Icon("Icons.Plus",14)]]]
                        + SVerticalBox::Slot().AutoHeight().Padding(2,0,2,5)
                        [SAssignNew(SearchBox,SSearchBox).Tag(TEXT("Review.Search"))
                            .HintText(FText::FromString(TEXT("搜索资产名或标签")))
                            .DelayChangeNotificationsWhileTyping(false)
                            .OnTextChanged_Lambda([this](const FText& Text){
                                Query = Text.ToString().TrimStartAndEnd();
                                SearchFolded.Reset();
                                RebuildAssetList();
                            })]
                        + SVerticalBox::Slot().AutoHeight()
                        [SNew(STextBlock).Tag(TEXT("Review.Search.Empty")).Margin(FMargin(4,6))
                            .Text(FText::FromString(TEXT("没有匹配的资产")))
                            .ColorAndOpacity(FSlateColor::UseSubduedForeground())
                            .Visibility_Lambda([this](){return !Query.IsEmpty() && MatchCount == 0 ? EVisibility::Visible : EVisibility::Collapsed;})]
                        + SVerticalBox::Slot().AutoHeight()[SAssignNew(EditorHost,SBox).Visibility(EVisibility::Collapsed)]
                        + SVerticalBox::Slot().FillHeight(1)
                        [SAssignNew(AssetList,SListView<FObject>).ListItemsSource(&AssetItems).SelectionMode(ESelectionMode::Single)
                            .OnGenerateRow(this, &SReviewWorkbench::AssetRow)
                            .OnContextMenuOpening(this,&SReviewWorkbench::ContextMenu)
                            .OnMouseButtonClick_Lambda([this](FObject Row){if (Str(Row,TEXT("path")).IsEmpty()) ToggleGroup(Row); else SelectAsset(Row);})
                            .OnSelectionChanged_Lambda([this](FObject Item, ESelectInfo::Type Source){
                                if (Item && !Str(Item,TEXT("path")).IsEmpty() && (Source == ESelectInfo::OnNavigation || Source == ESelectInfo::OnKeyPress)) SelectAsset(Item);
                            })]]]
                + SSplitter::Slot().Value(.69f).MinSize(300)
                [SNew(SBorder).BorderImage(FAppStyle::GetBrush("ToolPanel.GroupBorder")).Padding(6)
                    .Visibility_Lambda([this](){return bNarrow && !bDetailPage ? EVisibility::Collapsed : EVisibility::Visible;})
                    [SNew(SVerticalBox)
                        + SVerticalBox::Slot().AutoHeight()
                        [SNew(STextBlock).Text(FText::FromString(TEXT("请从搜索结果中选择资产"))).Margin(8)
                            .ColorAndOpacity(FSlateColor::UseSubduedForeground())
                            .Visibility_Lambda([this](){return bSelectionFiltered && MatchCount > 0 ? EVisibility::Visible : EVisibility::Collapsed;})]
                        + SVerticalBox::Slot().FillHeight(1)
                        [SAssignNew(Details,SScrollBox)
                            .Visibility_Lambda([this](){return bSelectionFiltered ? EVisibility::Collapsed : EVisibility::Visible;})]]]]
            + SVerticalBox::Slot().AutoHeight()[SNew(SSeparator)]
            + SVerticalBox::Slot().AutoHeight().Padding(8,4)
            [SNew(SHorizontalBox)
                + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0,0,12,0)[SAssignNew(HeaderStatus,STextBlock)]
                + SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center)
                [SAssignNew(Feedback,STextBlock).AutoWrapText(true).TextStyle(&FAppStyle::Get(), "SmallText.Subdued")]]];
        Run(TEXT("open"));
    }

    virtual void Tick(const FGeometry& Geometry, const double InCurrentTime, const float InDeltaTime) override
    {
        SCompoundWidget::Tick(Geometry, InCurrentTime, InDeltaTime);
        bNarrow = Geometry.GetLocalSize().X < 650;
    }

    void Run(const FString& Action, const FString& Argument = FString())
    {
        if (!PendingAction.IsEmpty()) return;
        FString BusyText;
        if (Action == TEXT("apply")) BusyText = TEXT("正在修改贴图并复扫…");
        else if (Action == TEXT("preview")) BusyText = TEXT("正在读取贴图和受影响引用…");
        else if (Action == TEXT("recheck")) BusyText = TEXT("正在复验当前资产…");
        else if (Action == TEXT("rules_batch_budget")) BusyText = TEXT("正在按新预算复验本批次…");
        else if (Action == TEXT("scan") || Action == TEXT("folders") || Action == TEXT("imported"))
            BusyText = TEXT("正在检查资产…");
        if (BusyText.IsEmpty())
        {
            Execute(Action, Argument);
            return;
        }
        PendingAction = Action;
        Feedback->SetText(FText::FromString(BusyText));
        // Keep the pending state and original selection visible while Slate completes the click.
        RegisterActiveTimer(0.12f, FWidgetActiveTimerDelegate::CreateLambda(
            [this, Action, Argument](double, float)
            {
                Execute(Action, Argument);
                PendingAction.Reset();
                return EActiveTimerReturnType::Stop;
            }));
    }

    void Execute(const FString& Action, const FString& Argument)
    {
        IPythonScriptPlugin* Python = IPythonScriptPlugin::Get();
        if (!Python || !Python->IsPythonAvailable())
        {
            Feedback->SetText(FText::FromString(TEXT("UE Python 尚未就绪。请稍后打开工作台。")));
            return;
        }
        FPythonCommandEx Call;
        // Values can contain arbitrary Unicode package paths. Only base64 enters the Python expression.
        Call.Command = FString::Printf(TEXT("import base64; from asset_forge.unreal.review_workbench import slate_dispatch; print('AF_REVIEW=' + slate_dispatch('%s', base64.b64decode('%s').decode('utf-8')))"), *Action, *FBase64::Encode(Argument));
        Call.ExecutionMode = EPythonCommandExecutionMode::ExecuteFile;
        Call.FileExecutionScope = EPythonFileExecutionScope::Public;
        FObject Next;
        if (Python->ExecPythonCommandEx(Call))
        {
            for (const auto& Entry : Call.LogOutput)
            {
                if (Entry.Output.StartsWith(TEXT("AF_REVIEW=")))
                {
                    const auto Reader = TJsonReaderFactory<>::Create(Entry.Output.Mid(10));
                    FJsonSerializer::Deserialize(Reader, Next);
                    break;
                }
            }
        }
        if (!Next)
        {
            Feedback->SetText(FText::FromString(TEXT("读取批审状态失败。请查看 Output Log 的 Python 记录。")));
            return;
        }
        const bool Same = Str(State, TEXT("selected")) == Str(Next, TEXT("selected"));
        const bool NewBatch = Str(State, TEXT("batch_id")) != Str(Next, TEXT("batch_id"));
        const float Offset = Same && !NewBatch ? Details->GetScrollOffset() : 0;
        if (Action == TEXT("select")) { bDetailPage = true; }
        State = Next;
        if (Action == TEXT("preview")) Folded.Remove("Impact");
        if (Action == TEXT("apply")) Folded.Remove("Changes");
        if (NewBatch || Action == TEXT("batch") || Action == TEXT("scan") || Action == TEXT("folders"))
        {
            bDetailPage = false;
            CloseForm();
        }
        if (NewBatch) SearchBox->SetText(FText::GetEmpty());
        Rebuild();
        if (Action == TEXT("preview") && ImpactArea)
            Details->ScrollDescendantIntoView(ImpactArea, false);
        else if (Action == TEXT("apply") && ChangesArea)
            Details->ScrollDescendantIntoView(ChangesArea, false);
        else
            Details->SetScrollOffset(Offset);
    }


private:
    FObject State;
    FString PendingAction;
    TSharedPtr<SWidget> ImpactArea, ChangesArea;
    bool bNarrow = false;
    bool bDetailPage = false;
    TSet<FName> Folded = { FName(TEXT("Passed")) };
    TSharedPtr<SSearchBox> SearchBox;
    FString Query;
    TSet<FString> SearchFolded;
    int32 MatchCount = 0;
    bool bSelectionFiltered = false;
    TMap<FString,int32> GroupCounts;
    TMap<FString,FObject> AssetRows;
    TSharedPtr<SBox> EditorHost;
    TArray<FObject> AssetItems;
    TSharedPtr<SListView<FObject>> AssetList;
    TSharedPtr<SScrollBox> Details;
    TSharedPtr<STextBlock> Feedback,ListTitle,HeaderStatus;

    TSharedRef<SButton> Button(const FString& Caption, const FString& Action, const FString& Argument,
        FName Brush, const FString& Tooltip, const FString& WidgetTag, bool Commit = false)
    {
        return SNew(SButton).Tag(FName(*WidgetTag))
            .ButtonStyle(FAppStyle::Get(), Commit ? "PrimaryButton" : "Button")
            .ToolTipText(FText::FromString(Tooltip))
            .IsEnabled_Lambda([this](){ return PendingAction.IsEmpty(); })
            .OnClicked_Lambda([this,Action,Argument](){ Run(Action,Argument); return FReply::Handled(); })
            [SNew(SHorizontalBox)
                + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0,0,5,0)[Icon(Brush)]
                + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)
                [SNew(STextBlock).Text_Lambda([this,Caption,Action]()
                    {
                        return FText::FromString(Action == TEXT("apply") && PendingAction == Action
                            ? TEXT("修改并复扫中…") : Caption);
                    })]];
    }

    TSharedRef<SWidget> HistoryMenu()
    {
        Run(TEXT("history"));
        FMenuBuilder Menu(true, nullptr);
        const auto Batches = Items(State, TEXT("batches"));
        for (const auto& Batch : Batches)
        {
            const FString Id = Str(Batch, TEXT("id"));
            Menu.AddMenuEntry(FText::FromString(Str(Batch, TEXT("label"))), FText(), FSlateIcon(),
                FUIAction(FExecuteAction::CreateLambda([this,Id](){Run(TEXT("batch"),Id);})));
        }
        if (Batches.IsEmpty()) Menu.AddWidget(Label(TEXT("暂无返修批次")), FText(), true);
        return Menu.MakeWidget();
    }

    TSharedRef<SWidget> RulesMenu()
    {
        const TSharedPtr<FJsonObject>* Policy = nullptr;
        FMenuBuilder Menu(true, nullptr);
        if (!State || !State->TryGetObjectField(TEXT("stock_policy"), Policy) || !Policy)
        {
            Menu.AddWidget(Label(TEXT("等待读取项目的批审规则")), FText(), true);
            return Menu.MakeWidget();
        }
        AddBatchBudgetFields(Menu);
        Menu.AddWidget(Label(Str(*Policy,TEXT("limits")),"SmallText.Subdued"), FText(), true);
        auto AddChoices = [this, &Menu, Policy](const TCHAR* Id, const TCHAR* Title, const TCHAR* Choices,
            const TCHAR* SelectedKey, const TCHAR* Action)
        {
            Menu.BeginSection(FName(Id),FText::FromString(Title));
            const FString Selected = Str(*Policy,SelectedKey);
            for (const auto& Item : Items(*Policy,Choices))
            {
                const FString Value = Str(Item,TEXT("id"));
                Menu.AddMenuEntry(FText::FromString(Str(Item,TEXT("label"))), FText(), FSlateIcon(),
                    FUIAction(FExecuteAction::CreateLambda([this, Action, Value](){Run(Action,Value);}), FCanExecuteAction(),
                        FIsActionChecked::CreateLambda([Selected, Value](){return Selected == Value;})),
                    NAME_None, EUserInterfaceActionType::RadioButton);
            }
            Menu.EndSection();
        };
        AddChoices(TEXT("Platform"),TEXT("下次存量检查的目标平台"),TEXT("platforms"),TEXT("platform"),TEXT("rules_platform"));
        AddChoices(TEXT("Profile"),TEXT("下次存量检查的材质规则"),TEXT("profiles"),TEXT("profile"),TEXT("rules_profile"));
        Menu.BeginSection(TEXT("Budget"),FText::FromString(TEXT("下次存量检查的预算")));
        AddStockBudgetField(Menu,TEXT("LOD0 三角面"),TEXT("triangles"),TEXT("rules_triangles"));
        AddStockBudgetField(Menu,TEXT("材质槽数量"),TEXT("material_slots"),TEXT("rules_material_slots"));
        Menu.EndSection();
        return Menu.MakeWidget();
    }

    void AddBatchBudgetFields(FMenuBuilder& Menu)
    {
        const TSharedPtr<FJsonObject>* Budget = nullptr;
        int32 TriangleBudget = 0, MaterialSlotBudget = 0;
        if (!State->TryGetObjectField(TEXT("batch_budget"), Budget) || !Budget || !*Budget
            || !(*Budget)->TryGetNumberField(TEXT("triangles"), TriangleBudget)
            || !(*Budget)->TryGetNumberField(TEXT("material_slots"), MaterialSlotBudget))
        {
            return;
        }
        const auto Triangles = MakeShared<int32>(TriangleBudget);
        const auto Slots = MakeShared<int32>(MaterialSlotBudget);
        auto Input = [](const TSharedRef<int32>& Value, FName FieldTag)
        {
            return SNew(SBox).MinDesiredWidth(130)
                [SNew(SNumericEntryBox<int32>).Tag(FieldTag).AllowSpin(false).MinValue(1)
                    .Value_Lambda([Value](){ return TOptional<int32>(*Value); })
                    .OnValueChanged_Lambda([Value](int32 NewValue){ *Value = NewValue; })
                    .OnValueCommitted_Lambda([Value](int32 NewValue, ETextCommit::Type Commit)
                    {
                        if (Commit != ETextCommit::OnCleared) { *Value = NewValue; }
                    })];
        };
        Menu.BeginSection(TEXT("BatchBudget"),FText::FromString(TEXT("本批次预算")));
        Menu.AddWidget(Input(Triangles,TEXT("Review.BatchBudget.Triangles")),FText::FromString(TEXT("LOD0 三角面")),true);
        Menu.AddWidget(Input(Slots,TEXT("Review.BatchBudget.MaterialSlots")),FText::FromString(TEXT("材质槽数量")),true);
        Menu.AddWidget(SNew(SButton).Tag(TEXT("Review.ApplyBatchBudget")).ButtonStyle(FAppStyle::Get(),"PrimaryButton")
            .Text(FText::FromString(TEXT("应用并复验本批次")))
            .IsEnabled_Lambda([this, Triangles, Slots]()
            {
                return PendingAction.IsEmpty() && *Triangles > 0 && *Slots > 0;
            })
            .OnClicked_Lambda([this, Triangles, Slots]()
            {
                const FString Budgets = FString::Printf(TEXT("{\"triangles\":%d,\"material_slots\":%d}"), *Triangles, *Slots);
                FSlateApplication::Get().DismissAllMenus();
                Run(TEXT("rules_batch_budget"), Budgets);
                return FReply::Handled();
            }),FText(),true);
        Menu.EndSection();
    }

    TOptional<int32> StockBudgetValue(const TCHAR* Key) const
    {
        const TSharedPtr<FJsonObject>* Policy = nullptr;
        int32 Value = 0;
        if (State && State->TryGetObjectField(TEXT("stock_policy"), Policy) && Policy && *Policy
            && (*Policy)->TryGetNumberField(Key, Value))
        {
            return Value;
        }
        return {};
    }

    void AddStockBudgetField(FMenuBuilder& Menu, const TCHAR* Title, const TCHAR* Key, const TCHAR* Action)
    {
        Menu.AddWidget(SNew(SBox).MinDesiredWidth(130)
            [SNew(SNumericEntryBox<int32>)
                .MinValue(1)
                .Value_Lambda([this, Key](){ return StockBudgetValue(Key); })
                .OnValueCommitted_Lambda([this, Key, Action](int32 Value, ETextCommit::Type Commit)
                {
                    const TOptional<int32> Current = StockBudgetValue(Key);
                    if (Commit != ETextCommit::OnCleared && Value > 0 && (!Current.IsSet() || Current.GetValue() != Value))
                    {
                        Run(Action, FString::FromInt(Value));
                    }
                })], FText::FromString(Title), true);
    }

    TSharedRef<SWidget> Toolbar()
    {
        return SNew(SWrapBox).UseAllottedSize(true).InnerSlotPadding(FVector2D(5,4))
            + SWrapBox::Slot()
            [Button(TEXT("检查选区"),TEXT("scan"),{},TEXT("Icons.Search"),TEXT("为选中资产建立新批次"),TEXT("Review.Scan"))]
            + SWrapBox::Slot()
            [Button(TEXT("检查文件夹"),TEXT("folders"),{},TEXT("Icons.FolderOpen"),TEXT("检查所选文件夹中的资产"),TEXT("Review.Folders"))]
            + SWrapBox::Slot()
            [SNew(SComboButton).Tag(TEXT("Review.Rules"))
                .IsEnabled_Lambda([this](){return PendingAction.IsEmpty();})
                .OnGetMenuContent(this, &SReviewWorkbench::RulesMenu)
                .ToolTipText(FText::FromString(TEXT("设置下次存量检查的目标平台与材质规则")))
                .ButtonContent()[ActionLabel(TEXT("批审规则"),TEXT("Icons.Settings"))]]
            + SWrapBox::Slot()
            [SNew(SComboButton).Tag(TEXT("Review.History"))
                .IsEnabled_Lambda([this](){return PendingAction.IsEmpty();})
                .OnGetMenuContent(this, &SReviewWorkbench::HistoryMenu)
                .ToolTipText(FText::FromString(TEXT("打开历史批次")))
                .ButtonContent()[ActionLabel(TEXT("批次记录"),TEXT("Icons.Calendar"))]]
            + SWrapBox::Slot()
            [SNew(SBox).IsEnabled_Lambda([this](){bool bCan=false;return State && State->TryGetBoolField(TEXT("can_report"),bCan) && bCan;})
                [Button(TEXT("批次报告"),TEXT("open_report"),{},TEXT("Icons.Documentation"),TEXT("打开当前批次完整 HTML 报告与交接日志"),TEXT("Review.OpenReport"))]];
    }

    TSharedRef<SWidget> Module(FName Id, const FString& Name, FName Brush,
                               const FString& Detail, const TSharedRef<SWidget>& Content)
    {
        return SNew(SExpandableArea).Tag(FName(*(TEXT("Review.Fold.") + Id.ToString())))
            .InitiallyCollapsed(Folded.Contains(Id))
            .OnAreaExpansionChanged_Lambda([this,Id](bool Expanded){
                if (Expanded) Folded.Remove(Id); else Folded.Add(Id);
            })
            .BorderImage(FAppStyle::GetBrush("DetailsView.CategoryTop"))
            .BodyBorderImage(FAppStyle::GetBrush("ToolPanel.GroupBorder"))
            .HeaderPadding(FMargin(5,4)).Padding(FMargin(6,4))
            .HeaderContent()
            [SNew(SHorizontalBox)
                + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0,0,6,0)[Icon(Brush)]
                + SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center)[Label(Name,"DetailsView.CategoryTextStyle")]
                + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)[Label(Detail,"SmallText.Subdued")]]
            .BodyContent()[Content];
    }

    void AddDetail(TSharedRef<SWidget> Widget)
    {
        Details->AddSlot().Padding(0,0,0,6)[Widget];
    }

    void CloseForm()
    {
        EditorHost->SetVisibility(EVisibility::Collapsed);
    }

    void Dispatch(const FString& Action, const FObject& Data)
    {
        FString Json;
        auto Writer = TJsonWriterFactory<>::Create(&Json);
        FJsonSerializer::Serialize(Data.ToSharedRef(), Writer);
        Run(Action, Json);
    }

    void EditAnnotation(bool bTag, const FObject& Existing = nullptr, const FString& Path = FString())
    {
        if (Str(State,TEXT("selected")).IsEmpty()) return;
        const FString Id = Str(Existing,TEXT("id"));
        const FString Caption = bTag
            ? (Id.IsEmpty() ? TEXT("新建标签") : TEXT("编辑标签"))
            : (Id.IsEmpty() ? TEXT("新建分组") : TEXT("重命名分组"));
        auto Editor = SNew(SAnnotationEditor).Caption(Caption).Name(Str(Existing,TEXT("name")))
            .Color(bTag ? (Id.IsEmpty() ? FString(TEXT("#669DD6")) : Str(Existing,TEXT("color"))) : FString())
            .OnCancel(FSimpleDelegate::CreateSP(this,&SReviewWorkbench::CloseForm))
            .OnSave_Lambda([this,bTag,Id,Path,Existing](const FString& Name,const FString& Color)
            {
                auto Data = MakeShared<FJsonObject>();
                Data->SetStringField(TEXT("name"),Name);
                if (!Id.IsEmpty())
                {
                    Data->SetStringField(bTag ? TEXT("tag") : TEXT("group"),Id);
                    Data->SetStringField(TEXT("original_name"),Str(Existing,TEXT("name")));
                    if (bTag) Data->SetStringField(TEXT("original_color"),Str(Existing,TEXT("color")));
                }
                if (bTag) Data->SetStringField(TEXT("color"),Color);
                if (!Path.IsEmpty()) Data->SetStringField(TEXT("path"),Path);
                CloseForm();
                Dispatch(bTag ? (Id.IsEmpty() ? TEXT("create_tag") : TEXT("update_tag"))
                              : (Id.IsEmpty() ? TEXT("create_group") : TEXT("rename_group")),Data);
            });
        EditorHost->SetContent(Editor);
        EditorHost->SetVisibility(EVisibility::Visible);
        Editor->FocusName();
    }

    void ToggleGroup(const FObject& Group)
    {
        const FString Id = Str(Group,TEXT("id"));
        if (!Query.IsEmpty())
        {
            if (SearchFolded.Contains(Id)) SearchFolded.Remove(Id); else SearchFolded.Add(Id);
            RebuildAssetList();
            return;
        }
        auto Data = MakeShared<FJsonObject>();
        Data->SetStringField(TEXT("group"),Id);
        Data->SetBoolField(TEXT("collapsed"),!Group->GetBoolField(TEXT("collapsed")));
        Dispatch(TEXT("toggle_group"),Data);
    }

    void MoveAsset(const FString& Path, const FString& Id)
    {
        auto Data = MakeShared<FJsonObject>();
        Data->SetStringField(TEXT("path"),Path);
        Data->SetStringField(TEXT("group"),Id);
        Dispatch(TEXT("move_asset"),Data);
    }

    void SetTagOnAsset(const FString& Path, const FString& Id, bool Assigned)
    {
        auto Data = MakeShared<FJsonObject>();
        Data->SetStringField(TEXT("path"),Path);
        Data->SetStringField(TEXT("tag"),Id);
        Data->SetBoolField(TEXT("assigned"),Assigned);
        Dispatch(TEXT("set_tag"),Data);
    }

    bool HasAssetTag(const FString& Path,const FString& Id) const
    {
        const FObject* Row = AssetRows.Find(Path);
        const TArray<TSharedPtr<FJsonValue>>* Assigned;
        return Row && (*Row)->TryGetArrayField(TEXT("tags"),Assigned) &&
            Assigned->ContainsByPredicate([&Id](const TSharedPtr<FJsonValue>& Value){return Value->AsString()==Id;});
    }

    TSharedPtr<SWidget> ContextMenu()
    {
        const auto Selected = AssetList->GetSelectedItems();
        FMenuBuilder Menu(true,nullptr);
        if (Selected.IsEmpty()) return nullptr;
        const FObject Row = Selected[0];
        const FString Path = Str(Row,TEXT("path"));
        if (Path.IsEmpty())
        {
            Menu.AddMenuEntry(FText::FromString(TEXT("重命名分组")),FText(),FSlateIcon(),
                FUIAction(FExecuteAction::CreateLambda([this,Row](){ EditAnnotation(false,Row); })));
            return Menu.MakeWidget();
        }
        const auto Groups = Items(State,TEXT("groups"));
        const auto Tags = Items(State,TEXT("tags"));
        Menu.BeginSection(NAME_None,FText::FromString(TEXT("分组")));
        for (const auto& Group : Groups)
        {
            const FString Id = Str(Group,TEXT("id"));
            Menu.AddMenuEntry(FText::FromString(TEXT("移入 ") + Str(Group,TEXT("name"))),FText(),FSlateIcon(),
                FUIAction(FExecuteAction::CreateLambda([this,Path,Id](){ MoveAsset(Path,Id); }),
                    FCanExecuteAction::CreateLambda([Row,Id](){ return Str(Row,TEXT("group")) != Id; })));
        }
        if (!Str(Row,TEXT("group")).IsEmpty())
            Menu.AddMenuEntry(FText::FromString(TEXT("移出分组")),FText(),FSlateIcon(),
                FUIAction(FExecuteAction::CreateLambda([this,Path](){ MoveAsset(Path,FString()); })));
        Menu.AddMenuEntry(FText::FromString(TEXT("新建分组")),FText(),FSlateIcon(),
            FUIAction(FExecuteAction::CreateLambda([this](){ EditAnnotation(false); })));
        Menu.EndSection();
        Menu.BeginSection(NAME_None,FText::FromString(TEXT("资产标签")));
        for (const auto& AssetTag : Tags)
        {
            const FString Id = Str(AssetTag,TEXT("id"));
            Menu.AddMenuEntry(FUIAction(FExecuteAction::CreateLambda([this,Path,Id](){SetTagOnAsset(Path,Id,!HasAssetTag(Path,Id));}),
                FCanExecuteAction(),FIsActionChecked::CreateLambda([this,Path,Id](){return HasAssetTag(Path,Id);})),
                TagLabel(AssetTag),NAME_None,FText(),EUserInterfaceActionType::ToggleButton);
        }
        Menu.AddMenuEntry(FText::FromString(TEXT("新建标签")),FText::FromString(TEXT("创建并添加到此资产")),FSlateIcon(),
            FUIAction(FExecuteAction::CreateLambda([this,Path](){ EditAnnotation(true,nullptr,Path); })));
        if (!Tags.IsEmpty())
            Menu.AddSubMenu(FText::FromString(TEXT("编辑标签")),FText::FromString(TEXT("修改标签名称和颜色")),
                FNewMenuDelegate::CreateLambda([this,Tags](FMenuBuilder& Sub)
                {
                    for (const auto& AssetTag : Tags)
                        Sub.AddMenuEntry(FUIAction(FExecuteAction::CreateLambda([this,AssetTag](){ EditAnnotation(true,AssetTag); })),TagLabel(AssetTag));
                }));
        Menu.EndSection();
        return Menu.MakeWidget();
    }

    TSharedRef<SWidget> TagLabel(const FObject& AssetTag) const
    {
        static const FSlateRoundedBoxBrush Dot(FLinearColor::White,2.f);
        return SNew(SHorizontalBox)
            + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0,0,4,0)
            [SNew(SBox).WidthOverride(8).HeightOverride(8)
                [SNew(SImage).Tag(FName(*(TEXT("Review.Swatch.")+Str(AssetTag,TEXT("id"))))).Image(&Dot)
                    .ColorAndOpacity(FLinearColor::FromSRGBColor(FColor::FromHex(Str(AssetTag,TEXT("color")))))]]
            + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)[Label(Str(AssetTag,TEXT("name")),"SmallText")];
    }

    bool IsGroupFolded(const FObject& Group) const
    {
        return Query.IsEmpty() ? Group->GetBoolField(TEXT("collapsed")) : SearchFolded.Contains(Str(Group,TEXT("id")));
    }

    TSharedRef<ITableRow> GroupRow(const FObject& Group,const TSharedRef<STableViewBase>& Owner)
    {
        const FString Id = Str(Group,TEXT("id"));
        const bool Collapsed = IsGroupFolded(Group);
        return SNew(STableRow<FObject>,Owner).Tag(FName(*(TEXT("Review.Group.")+Id))).Padding(FMargin(3,4))
            .ToolTipText(FText::FromString(TEXT("点击展开或折叠，右键重命名分组")))
            [SNew(SHorizontalBox)
                + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0,0,5,0)
                [Icon(Collapsed ? "TreeArrow_Collapsed" : "TreeArrow_Expanded",11)]
                + SHorizontalBox::Slot().FillWidth(1)[Label(Str(Group,TEXT("name")),"DetailsView.CategoryTextStyle")]
                + SHorizontalBox::Slot().AutoWidth().Padding(5,0)[Label(FString::FromInt(GroupCounts.FindRef(Id)),"SmallText.Subdued")]];
    }

    void RebuildAssetList()
    {
        const auto Assets = Items(State,TEXT("assets"));
        const auto Groups = Items(State,TEXT("groups"));
        TMap<FString,TArray<FObject>> Members;
        TSet<FString> MatchingTags;
        if (!Query.IsEmpty())
        {
            for (const auto& AssetTag : Items(State,TEXT("tags")))
                if (Str(AssetTag,TEXT("name")).Contains(Query)) MatchingTags.Add(Str(AssetTag,TEXT("id")));
        }
        AssetRows.Reset();
        MatchCount = 0;
        const FString Selected = Str(State,TEXT("selected"));
        bSelectionFiltered = !Query.IsEmpty() && !Selected.IsEmpty();
        for (const auto& Row : Assets)
        {
            const FString Path = Str(Row,TEXT("path"));
            AssetRows.Add(Path,Row);
            if (!Query.IsEmpty() && !Str(Row,TEXT("name")).Contains(Query))
            {
                TArray<FString> Tags;
                Row->TryGetStringArrayField(TEXT("tags"),Tags);
                if (!Tags.ContainsByPredicate([&MatchingTags](const FString& TagId){return MatchingTags.Contains(TagId);})) continue;
            }
            Members.FindOrAdd(Str(Row,TEXT("group"))).Add(Row);
            ++MatchCount;
            if (Path == Selected) bSelectionFiltered = false;
        }
        AssetItems.Reset();
        GroupCounts.Reset();
        for (const auto& Group : Groups)
        {
            const FString Id = Str(Group,TEXT("id"));
            const auto* Rows = Members.Find(Id);
            if (!Query.IsEmpty() && !Rows) continue;
            GroupCounts.Add(Id,Rows ? Rows->Num() : 0);
            AssetItems.Add(Group);
            if (Rows && !IsGroupFolded(Group)) AssetItems.Append(*Rows);
        }
        if (const auto* Ungrouped = Members.Find(FString())) AssetItems.Append(*Ungrouped);
        AssetList->ClearSelection();
        AssetList->RebuildList();
        ListTitle->SetText(FText::FromString(Query.IsEmpty() ? Str(State,TEXT("summary"))
            : FString::Printf(TEXT("%d / %d 件资产"),MatchCount,Assets.Num())));
        for (const auto& Row : AssetItems)
            if (Str(Row,TEXT("path")) == Selected && !Selected.IsEmpty()) { AssetList->SetSelection(Row,ESelectInfo::Direct); break; }
    }

    void SelectAsset(FObject Item)
    {
        Run(TEXT("select"), Str(Item, TEXT("path")));
    }

    TSharedRef<ITableRow> AssetRow(FObject Row, const TSharedRef<STableViewBase>& Owner)
    {
        const FString Path = Str(Row,TEXT("path"));
        if (Path.IsEmpty()) return GroupRow(Row,Owner);
        FString Status, Count;
        Str(Row,TEXT("label")).Split(TEXT("·"),&Status,&Count);
        auto Tags = SNew(SWrapBox).UseAllottedSize(true).InnerSlotPadding(FVector2D(8,2));
        TArray<FString> Assigned;
        Row->TryGetStringArrayField(TEXT("tags"),Assigned);
        for (const auto& AssetTag : Items(State,TEXT("tags")))
            if (Assigned.Contains(Str(AssetTag,TEXT("id")))) Tags->AddSlot()[TagLabel(AssetTag)];
        return SNew(STableRow<FObject>, Owner).Tag(FName(*(TEXT("Review.Asset.")+Path)))
            .ToolTipText(FText::FromString(Path + TEXT("\n右键管理分组和标签"))).Padding(FMargin(5,5))
            [SNew(SHorizontalBox)
                + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(Str(Row,TEXT("group")).IsEmpty()?0:10,0,6,0)[Icon("ClassIcon.StaticMesh")]
                + SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center)
                [SNew(SVerticalBox)
                    + SVerticalBox::Slot().AutoHeight()[Label(Str(Row,TEXT("name")))]
                    + SVerticalBox::Slot().AutoHeight().Padding(0,2,0,0)[Label(Count.TrimStartAndEnd(),"SmallText.Subdued")]
                    + SVerticalBox::Slot().AutoHeight().Padding(0,2,0,0)[Tags]]
                + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(6,0,0,0)
                [StatusLabel(Status.TrimStartAndEnd(),Str(Row,TEXT("status")))]];
    }

    TSharedRef<SWidget> AssetHeader(const FString& Selected, const FString& Status)
    {
        FString StateName, Measures;
        Str(State,TEXT("facts")).Split(TEXT("·"),&StateName,&Measures);
        FSlateFontInfo TitleFont = FAppStyle::Get().GetWidgetStyle<FTextBlockStyle>("NormalText.Subdued").Font;
        TitleFont.Size = 14;
        TitleFont.TypefaceFontName = TEXT("Bold");
        auto Title = SNew(STextBlock).Tag(TEXT("Review.Detail.Title")).Text(FText::FromString(Str(State,TEXT("name"))))
            .Font(TitleFont).AutoWrapText(true);
        Title->SetToolTipText(FText::FromString(Selected));
        const FString Path = Str(State,TEXT("path"));
        const FString Source = Str(State,TEXT("source_dir"));
        const FString Updated = Str(State,TEXT("updated_at"));
        const FString Profile = Str(State,TEXT("profile"));
        const FString Platform = Str(State,TEXT("platform"));
        const FString Budget = Str(State,TEXT("budget_summary"));
        const FString BudgetSource = Str(State,TEXT("budget_source"));
        auto PathButton = SNew(SButton).Tag(TEXT("Review.CopyPath")).ButtonStyle(FAppStyle::Get(),"SimpleButton")
            .ContentPadding(FMargin(0,1)).HAlign(HAlign_Left)
            .ToolTipText(FText::FromString(TEXT("复制完整 UE 资产路径\n")+Path)).IsEnabled(!Path.IsEmpty())
            .OnClicked_Lambda([this,Path](){FPlatformApplicationMisc::ClipboardCopy(*Path);
                Feedback->SetText(FText::FromString(TEXT("已复制 UE 资产路径。")));return FReply::Handled();})
            [SNew(SHorizontalBox)
                + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0,0,8,0)[Label(TEXT("UE 资产路径"),"SmallText.Subdued")]
                + SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center)[Label(Path,"SmallText")]
                + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(6,0,0,0)[Icon("GenericCommands.Copy",12)]];
        auto Context = SNew(SWrapBox).UseAllottedSize(true).InnerSlotPadding(FVector2D(16,3));
        auto Field = [](const FString& Key,const FString& Value,bool bWrap = false)
        {
            return SNew(SHorizontalBox)
                + SHorizontalBox::Slot().AutoWidth().Padding(0,0,6,0)[Label(Key,"SmallText.Subdued")]
                + SHorizontalBox::Slot().FillWidth(1)[SNew(STextBlock).Text(FText::FromString(Value))
                    .TextStyle(&FAppStyle::Get(),"SmallText").AutoWrapText(bWrap)
                    .WrappingPolicy(ETextWrappingPolicy::AllowPerCharacterWrapping)];
        };
        FString DisplaySource = Source;
        if (!Source.IsEmpty())
        {
            FString Project = FPaths::ConvertRelativePathToFull(FPaths::ProjectDir());
            FPaths::NormalizeDirectoryName(Project);
            FPaths::NormalizeDirectoryName(DisplaySource);
            if (FPaths::IsUnderDirectory(DisplaySource,Project))
                FPaths::MakePathRelativeTo(DisplaySource,*(Project + TEXT("/")));
            Context->AddSlot()[SNew(SBox).MaxDesiredWidth(390).ToolTipText(FText::FromString(Source))
                [Field(Str(State,TEXT("source_kind")),DisplaySource,true)]];
        }
        if (!Updated.IsEmpty()) Context->AddSlot()[Field(Str(State,TEXT("updated_kind")),Updated)];
        if (!Platform.IsEmpty()) Context->AddSlot()[Field(TEXT("目标平台"),Platform)];
        if (!Profile.IsEmpty()) Context->AddSlot()[Field(TEXT("命中规则"),Profile)];
        if (!Budget.IsEmpty()) Context->AddSlot()[Field(BudgetSource.IsEmpty() ? TEXT("预算") : BudgetSource + TEXT("预算"),Budget)];
        auto Actions = SNew(SWrapBox).UseAllottedSize(true).InnerSlotPadding(FVector2D(6,4))
            + SWrapBox::Slot()[Button(TEXT("复验当前资产"),TEXT("recheck"),{},TEXT("Icons.Refresh"),TEXT("仅复验此资产"),TEXT("Review.Recheck"))]
            + SWrapBox::Slot()[Button(TEXT("返修单"),TEXT("report"),{},TEXT("Icons.Documentation"),TEXT("打开本轮返修单"),TEXT("Review.Report"))]
            + SWrapBox::Slot()
            [SNew(SButton).Tag(TEXT("Review.LocateSelected"))
                .IsEnabled_Lambda([this, Path](){ return PendingAction.IsEmpty() && !Path.IsEmpty(); })
                .ToolTipText(FText::FromString(TEXT("在内容浏览器中选中当前静态网格")))
                .OnClicked_Lambda([this, Path](){ return LocateInContentBrowser(Path); })
                [ActionLabel(TEXT("在内容浏览器定位"),TEXT("Icons.BrowseContent"))]];
        return SNew(SBorder).Padding(12,9).BorderImage(FAppStyle::GetBrush("ToolPanel.GroupBorder"))
            [SNew(SVerticalBox)
                + SVerticalBox::Slot().AutoHeight()[SNew(SHorizontalBox)
                    + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0,0,8,0)[Icon(TEXT("ClassIcon.StaticMesh"),21)]
                    + SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center)[Title]
                    + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)[StatusLabel(StateName.TrimStartAndEnd(),Status)]]
                
                + SVerticalBox::Slot().AutoHeight().Padding(0,5,0,3)[Label(Measures.TrimStartAndEnd(),"NormalText.Subdued")]
                + SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Left)[PathButton]
                + SVerticalBox::Slot().AutoHeight().Padding(0,3,0,8)[Context]
                + SVerticalBox::Slot().AutoHeight()[Actions]];
    }

    FReply LocateInContentBrowser(const FString& Path)
    {
        if (!PendingAction.IsEmpty())
        {
            return FReply::Handled();
        }
        const FString ObjectPath = Path.Contains(TEXT(".")) ? Path : Path + TEXT(".") + FPackageName::GetLongPackageAssetName(Path);
        if (!FPackageName::IsValidObjectPath(ObjectPath))
        {
            Feedback->SetText(FText::FromString(TEXT("无法定位此资产，请复验当前资产。")));
            return FReply::Handled();
        }
        const auto& Registry = FModuleManager::LoadModuleChecked<FAssetRegistryModule>("AssetRegistry").Get();
        const FAssetData Asset = Registry.GetAssetByObjectPath(FSoftObjectPath(ObjectPath));
        if (!Asset.IsValid())
        {
            Feedback->SetText(FText::FromString(TEXT("未找到此资产，请复验当前资产。")));
            return FReply::Handled();
        }
        const FText Located = FText::Format(FText::FromString(TEXT("已在内容浏览器定位：{0}")), FText::FromName(Asset.AssetName));
        Feedback->SetText(Located);
        auto& ContentBrowser = FModuleManager::LoadModuleChecked<FContentBrowserModule>("ContentBrowser").Get();
        ContentBrowser.SyncBrowserToAssets(TArray<FAssetData>{Asset}, false, true);

        FNotificationInfo Notice(Located);
        Notice.ExpireDuration = 3.0f;
        FSlateNotificationManager::Get().AddNotification(Notice);
        return FReply::Handled();
    }

    TSharedRef<SWidget> IssueList(const TArray<FObject>& Issues)
    {
        auto Rows=SNew(SVerticalBox);
        if (!Issues.Num())
        {
            Rows->AddSlot().AutoHeight().Padding(3,4)[Label(Str(State,TEXT("empty_label")),"NormalText.Subdued")];
        }
        FString Previous;
        for (const auto& Issue:Issues)
        {
            const FString Path=Str(Issue,TEXT("path")), Index=Str(Issue,TEXT("index"));
            const FString Severity=Str(Issue,TEXT("severity"));
            const FString Action=Str(Issue,TEXT("action_kind"));
            const FString ActionLabelText=Str(Issue,TEXT("action_label"));
            const FString Slot=Str(Issue,TEXT("slot"));
            if (Path!=Previous)
            {
                auto Name=Label(Leaf(Path),"DetailsView.CategoryTextStyle");
                Name->SetToolTipText(FText::FromString(Path));
                Rows->AddSlot().AutoHeight().Padding(2,4,0,5)[Name];
                Previous=Path;
            }
            const FString SeverityText = Severity == TEXT("blocked") ? TEXT("阻断")
                : Severity == TEXT("warning") ? TEXT("警告") : TEXT("待核实");
            const FString Caption = Str(Issue,TEXT("title")) + (Slot.IsEmpty() ? FString() : TEXT("  ·  槽 ") + Slot);
            auto Card = SNew(SVerticalBox)
                + SVerticalBox::Slot().AutoHeight()
                [SNew(SHorizontalBox)
                    + SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center)[Label(Caption,"DetailsView.CategoryTextStyle")]
                    + SHorizontalBox::Slot().AutoWidth().Padding(4,0,0,0)[StatusLabel(SeverityText,Severity)]]
                + SVerticalBox::Slot().AutoHeight().Padding(0,3,0,0)[Label(Str(Issue,TEXT("summary")))]
                + SVerticalBox::Slot().AutoHeight().Padding(0,2,0,0)[Label(Str(Issue,TEXT("export_impact")),"SmallText.Subdued")]
                + SVerticalBox::Slot().AutoHeight().Padding(0,2,0,4)[Label(Str(Issue,TEXT("fix_guidance")),"NormalText.Subdued")];
            if (Action != TEXT("selection"))
            {
                auto Actions = SNew(SWrapBox).UseAllottedSize(true).InnerSlotPadding(FVector2D(5,3));
                Actions->AddSlot()
                    [SNew(SButton).Tag(FName(*(TEXT("Review.Locate.") + Index)))
                        .IsEnabled_Lambda([this](){ return PendingAction.IsEmpty(); })
                        .ToolTipText(FText::FromString(Path))
                        .OnClicked_Lambda([this, Path](){ return LocateInContentBrowser(Path); })
                        [ActionLabel(TEXT("在内容浏览器定位"),TEXT("Icons.BrowseContent"))]];
                if (Action == TEXT("preview_fix") && Str(State,TEXT("fix")) != TEXT("confirm"))
                    Actions->AddSlot()[Button(ActionLabelText,TEXT("preview"),{},TEXT("Icons.Search"),
                        TEXT("读取当前贴图属性及受影响引用"),TEXT("Review.IssueAction.")+Index)];
                else if (Action.StartsWith(TEXT("open_")))
                    Actions->AddSlot()[Button(ActionLabelText,TEXT("open_issue"),Index,TEXT("Icons.Edit"),Path,TEXT("Review.IssueAction.")+Index)];
                Card->AddSlot().AutoHeight()[Actions];
            }
            Rows->AddSlot().AutoHeight().Padding(0,1)
                [SNew(SBorder).BorderImage(FAppStyle::GetBrush("ToolPanel.GroupBorder")).Padding(8,5)
                    .OnMouseDoubleClick_Lambda([this,Path,Action](const FGeometry&,const FPointerEvent&){
                        return Action != TEXT("selection") ? LocateInContentBrowser(Path) : FReply::Unhandled();
                    })
                    [Card]];
        }
        return Rows;
    }

    TSharedRef<SWidget> ImpactList(const TArray<FObject>& Plans)
    {
        auto Rows=SNew(SVerticalBox);
        for (const auto& Plan:Plans)
        {
            const FString Full=Str(Plan,TEXT("body"));
            TArray<FString> Lines;
            Full.ParseIntoArrayLines(Lines,false);
            FString Title=Str(Plan,TEXT("name"));
            FString Prefix;
            if (Title.Split(TEXT("·"),&Prefix,&Title)) Title=Title.TrimStartAndEnd();
            auto TextureName=Label(Title,"DetailsView.CategoryTextStyle");
            TextureName->SetToolTipText(FText::FromString(Full));
            Rows->AddSlot().AutoHeight().Padding(2,3,0,5)
                [SNew(SHorizontalBox)
                    + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0,0,6,0)[Icon(TEXT("ClassIcon.Texture2D"))]
                    + SHorizontalBox::Slot().FillWidth(1)[TextureName]];
            // Preserve unfamiliar formats in full. Every referenced path remains available on hover.
            if (Lines.Num()<4 || !Lines[1].StartsWith(TEXT("纹理   ")) || !Lines[2].StartsWith(TEXT("引用   ")))
            {
                Rows->AddSlot().AutoHeight()[Label(Full,"NormalText.Subdued")];
                continue;
            }
            TArray<FString> Properties;
            Lines[0].ParseIntoArray(Properties,TEXT("     "),true);
            auto Values=SNew(SVerticalBox);
            for (const FString& Value:Properties)
            {
                FString Property, Change, Old, New;
                if (Value.Split(TEXT("  "),&Property,&Change) && Change.Split(TEXT(" → "),&Old,&New))
                {
                    FSlateFontInfo TargetFont = FAppStyle::Get().GetWidgetStyle<FTextBlockStyle>("NormalText.Subdued").Font;
                    TargetFont.TypefaceFontName = TEXT("Bold");
                    Values->AddSlot().AutoHeight().Padding(2,2)
                        [SNew(SHorizontalBox)
                            + SHorizontalBox::Slot().AutoWidth()[SNew(SBox).WidthOverride(76)[Label(Property,"NormalText.Subdued")]]
                            + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)[Label(Old,"NormalText.Subdued")]
                            + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(8,0)[Icon(TEXT("Icons.ArrowRight"),12)]
                            + SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center)[SNew(STextBlock).Text(FText::FromString(New)).Font(TargetFont)
                                .ColorAndOpacity(FStyleColors::ForegroundHover).AutoWrapText(true)]];
                }
                else { Values->AddSlot().AutoHeight()[Label(Value,"NormalText.Subdued")]; }
            }
            Rows->AddSlot().AutoHeight().Padding(0,0,0,5)
                [SNew(SBorder).BorderImage(FAppStyle::GetBrush("ToolPanel.GroupBorder")).Padding(7,4).ToolTipText(FText::FromString(Lines[1]))[Values]];
            TArray<FString> Paths, Owners;
            bool bReadingOwners=false;
            for (int32 I=2; I<Lines.Num(); ++I)
            {
                FString Ref=Lines[I].TrimStartAndEnd();
                if (Ref.RemoveFromStart(TEXT("引用   "))) { bReadingOwners=false; }
                else if (Ref.RemoveFromStart(TEXT("网格   "))) { bReadingOwners=true; }
                if (Ref.StartsWith(TEXT("/")))
                {
                    Paths.AddUnique(Ref);
                    if (bReadingOwners) Owners.AddUnique(Ref);
                }
                else if (Ref!=TEXT("无") && !Ref.IsEmpty()) { Rows->AddSlot().AutoHeight()[Label(Ref)]; }
            }
            if (Paths.Num())
            {
                Rows->AddSlot().AutoHeight().Padding(1,3,0,3)[Label(FString::Printf(TEXT("受影响引用  ·  %d"),Paths.Num()),"DetailsView.CategoryTextStyle")];
            }
            for (const FString& Path:Paths)
            {
                auto Short=Label(Leaf(Path));
                Short->SetToolTipText(FText::FromString(Path));
                const bool bMesh=Owners.Contains(Path);
                auto RefRow=SNew(SHorizontalBox)
                    + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0,0,7,0)[Icon(bMesh ? TEXT("ClassIcon.StaticMesh") : TEXT("Icons.Link"),14)]
                    + SHorizontalBox::Slot().FillWidth(1)[Short]
                    + SHorizontalBox::Slot().AutoWidth().Padding(4,0,0,0)[Label(bMesh ? TEXT("受影响网格") : TEXT("引用资产"),"SmallText.Subdued")];
                Rows->AddSlot().AutoHeight().Padding(3,3)[SNew(SVerticalBox)
                    + SVerticalBox::Slot().AutoHeight()[RefRow]
                    + SVerticalBox::Slot().AutoHeight().Padding(21,1,0,0)[Label(FPaths::GetPath(Path),"SmallText.Subdued")]];
            }
        }
        return Rows;
    }

    void Rebuild()
    {
        Details->ClearChildren();
        ImpactArea.Reset();
        ChangesArea.Reset();
        const bool Awaiting = Str(State,TEXT("fix")) == TEXT("confirm");
        HeaderStatus->SetText(FText::FromString(Awaiting ? TEXT("等待确认修改") : TEXT("只读浏览")));
        HeaderStatus->SetColorAndOpacity(Awaiting ? FStyleColors::Warning : FSlateColor::UseSubduedForeground());
        Feedback->SetText(FText::FromString(Str(State,TEXT("message"))));
        const FString Selected=Str(State,TEXT("selected"));
        RebuildAssetList();
        const FString SelectedStatus = Str(AssetRows.FindRef(Selected),TEXT("status"));
        if (Selected.IsEmpty())
        {
            AddDetail(Label(TEXT("从内容浏览器选择要检查的资产或文件夹"),"NormalText.Subdued"));
            return;
        }
        AddDetail(SNew(SButton).Tag(TEXT("Review.Back")).ButtonStyle(FAppStyle::Get(), "SimpleButton")
            .HAlign(HAlign_Left).ContentPadding(FMargin(6,4))
            .Visibility_Lambda([this](){return bNarrow ? EVisibility::Visible : EVisibility::Collapsed;})
            .OnClicked_Lambda([this](){bDetailPage=false; return FReply::Handled();})
            [ActionLabel(TEXT("返回资产列表"),TEXT("Icons.ArrowLeft"))]);
        AddDetail(AssetHeader(Selected,SelectedStatus));
        const auto Issues=Items(State,TEXT("issues"));
        AddDetail(Module("Issues",TEXT("检查问题"),TEXT("Icons.Search"),FString::Printf(TEXT("%d 项"),Issues.Num()),IssueList(Issues)));
        const auto Plans=Items(State,TEXT("plans"));
        const FString Fix=Str(State,TEXT("fix"));
        if (Plans.Num() || !Fix.IsEmpty())
        {
            auto Body=SNew(SVerticalBox);
            if (Plans.Num()) Body->AddSlot().AutoHeight()[ImpactList(Plans)];
            if (Fix==TEXT("preview"))
            {
                Body->AddSlot().AutoHeight().HAlign(HAlign_Left).Padding(0,4)[Button(TEXT("预览修复影响"),TEXT("preview"),{},TEXT("Icons.Search"),TEXT("读取最新属性与引用"),TEXT("Review.Preview"))];
            }
            if (Fix==TEXT("confirm"))
            {
                Body->AddSlot().AutoHeight().Padding(0,7,0,4)[SNew(SSeparator)];
                Body->AddSlot().AutoHeight().Padding(0,3,0,1)[SNew(SWrapBox).UseAllottedSize(true).InnerSlotPadding(FVector2D(6,4))
                    + SWrapBox::Slot()
                    [Button(TEXT("确认修改并复扫"),TEXT("apply"),{},TEXT("Icons.Check"),TEXT("保存已预览的修改并复验当前资产"),TEXT("Review.Apply"),true)]
                    + SWrapBox::Slot()[Button(TEXT("取消修改"),TEXT("cancel"),{},TEXT("Icons.X"),TEXT("放弃当前修改预览"),TEXT("Review.Cancel"))]];
            }
            ImpactArea = Module("Impact",TEXT("修复影响"),TEXT("Icons.Link"),
                Plans.Num() ? FString::Printf(TEXT("%d 张贴图"),Plans.Num()) : FString(),Body);
            AddDetail(ImpactArea.ToSharedRef());
        }
        const auto Changes=Items(State,TEXT("changes"));
        if (Changes.Num())
        {
            auto List=SNew(SVerticalBox);
            for (const auto& Change:Changes) List->AddSlot().AutoHeight().Padding(2,3)[Label(Str(Change,TEXT("text")),"NormalText.Subdued")];
            ChangesArea = Module("Changes",TEXT("复验对照"),TEXT("Icons.Calendar"),
                FString::Printf(TEXT("%d 项"),Changes.Num()),List);
            AddDetail(ChangesArea.ToSharedRef());
        }
        const auto Passed=Items(State,TEXT("passed"));
        bool bHasPassEvidence=false;
        State->TryGetBoolField(TEXT("has_pass_evidence"),bHasPassEvidence);
        if (!bHasPassEvidence)
        {
            AddDetail(Label(TEXT("此轮记录早于检查证据功能。复验当前资产以查看通过明细。"),"SmallText.Subdued"));
            return;
        }
        auto PassedRows=SNew(SVerticalBox);
        if (Passed.IsEmpty())
            PassedRows->AddSlot().AutoHeight().Padding(2,3)[Label(TEXT("本轮暂无通过项。"),"SmallText.Subdued")];
        for (const auto& Check : Passed)
        {
            PassedRows->AddSlot().AutoHeight().Padding(2,3)
                [SNew(SVerticalBox)
                    + SVerticalBox::Slot().AutoHeight()[Label(Str(Check,TEXT("title"))+TEXT("  ·  ")+Leaf(Str(Check,TEXT("object_path"))),"DetailsView.CategoryTextStyle")]
                    + SVerticalBox::Slot().AutoHeight()[Label(Str(Check,TEXT("summary")),"NormalText.Subdued")]];
        }
        AddDetail(Module("Passed",FString::Printf(TEXT("已通过检查项（%d 项）"),Passed.Num()),
            TEXT("Icons.SuccessWithColor"),FString(),PassedRows));
    }
};

class SReviewTab : public SDockTab
{
public:
    void Construct(const FArguments& Args)
    {
        SDockTab::Construct(Args);
        if (IconWidget) IconWidget->SetDesiredSizeOverride(TOptional<FVector2D>(FVector2D(19,19)));
    }
};

TWeakPtr<SReviewWorkbench> Current;
}

TSharedRef<SDockTab> CreateTab(const TSharedRef<SWidget>& Content)
{
    return SNew(SReviewTab).TabRole(ETabRole::NomadTab)[Content];
}

TSharedRef<SWidget> CreatePanel()
{
    const auto Panel = SNew(SReviewWorkbench);
    Current = Panel;
    return Panel;
}

void Run(const FString& Action, const FString& Argument)
{
    if (const auto Panel = Current.Pin()) Panel->Run(Action, Argument);
}
}
