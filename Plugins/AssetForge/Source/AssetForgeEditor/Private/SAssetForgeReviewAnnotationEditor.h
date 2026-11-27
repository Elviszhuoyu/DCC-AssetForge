#pragma once

#include "Framework/Application/SlateApplication.h"
#include "Styling/AppStyle.h"
#include "Widgets/Colors/SColorBlock.h"
#include "Widgets/Colors/SColorPicker.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Input/SEditableTextBox.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SCompoundWidget.h"
#include "Widgets/Text/STextBlock.h"

namespace AssetForgeReview
{
class SAnnotationEditor : public SCompoundWidget
{
public:
    DECLARE_DELEGATE_TwoParams(FOnSave, const FString&, const FString&);
    SLATE_BEGIN_ARGS(SAnnotationEditor) {}
        SLATE_ARGUMENT(FString, Caption)
        SLATE_ARGUMENT(FString, Name)
        SLATE_ARGUMENT(FString, Color)
        SLATE_EVENT(FOnSave, OnSave)
        SLATE_EVENT(FSimpleDelegate, OnCancel)
    SLATE_END_ARGS()

    void Construct(const FArguments& Args)
    {
        OnSave = Args._OnSave;
        OnCancel = Args._OnCancel;
        auto Form = SNew(SVerticalBox);
        Form->AddSlot().AutoHeight().Padding(0,0,0,5)
            [SNew(STextBlock).Text(FText::FromString(Args._Caption)).TextStyle(&FAppStyle::Get(), "DetailsView.CategoryTextStyle")];
        Form->AddSlot().AutoHeight()
            [SAssignNew(NameField, SEditableTextBox).Tag(TEXT("Review.Form.Name")).Text(FText::FromString(Args._Name))
                .HintText(FText::FromString(TEXT("名称"))).SelectAllTextWhenFocused(true)
                .OnTextCommitted(this, &SAnnotationEditor::CommitText)];
        if (!Args._Color.IsEmpty())
        {
            Form->AddSlot().AutoHeight().Padding(0,5,0,0)
                [SNew(SHorizontalBox)
                    + SHorizontalBox::Slot().AutoWidth().Padding(0,0,5,0)
                    [SNew(SButton).Tag(TEXT("Review.Form.Picker")).ToolTipText(FText::FromString(TEXT("选择标签颜色")))
                        .OnClicked(this,&SAnnotationEditor::ChooseColor)
                        [SNew(SColorBlock).Color_Lambda([this](){ return FLinearColor::FromSRGBColor(FColor::FromHex(ColorText())); })
                            .Size(FVector2D(22,14)).ShowBackgroundForAlpha(false)]]
                    + SHorizontalBox::Slot().FillWidth(1)
                    [SAssignNew(ColorField, SEditableTextBox).Tag(TEXT("Review.Form.Color")).Text(FText::FromString(Args._Color))
                        .ToolTipText(FText::FromString(TEXT("sRGB 颜色，格式为 #RRGGBB"))).SelectAllTextWhenFocused(true)
                        .OnTextCommitted(this, &SAnnotationEditor::CommitText)]];
        }
        Form->AddSlot().AutoHeight().HAlign(HAlign_Right).Padding(0,6,0,0)
            [SNew(SHorizontalBox)
                + SHorizontalBox::Slot().AutoWidth().Padding(0,0,5,0)
                [SNew(SButton).Tag(TEXT("Review.Form.Cancel")).Text(FText::FromString(TEXT("取消")))
                    .OnClicked_Lambda([this](){ OnCancel.ExecuteIfBound(); return FReply::Handled(); })]
                + SHorizontalBox::Slot().AutoWidth()
                [SNew(SButton).Tag(TEXT("Review.Form.Save")).ButtonStyle(FAppStyle::Get(), "PrimaryButton")
                    .Text(FText::FromString(TEXT("保存"))).IsEnabled(this,&SAnnotationEditor::CanSave)
                    .OnClicked(this,&SAnnotationEditor::Save)]];
        ChildSlot[SNew(SBorder).BorderImage(FAppStyle::GetBrush("DetailsView.CategoryTop")).Padding(8)[Form]];
    }

    void FocusName() { FSlateApplication::Get().SetKeyboardFocus(NameField, EFocusCause::SetDirectly); }

    virtual FReply OnPreviewKeyDown(const FGeometry& Geometry,const FKeyEvent& Event) override
    {
        if (Event.GetKey() == EKeys::Escape) { OnCancel.ExecuteIfBound(); return FReply::Handled(); }
        return SCompoundWidget::OnPreviewKeyDown(Geometry,Event);
    }

private:
    FString ColorText() const { return ColorField ? ColorField->GetText().ToString().TrimStartAndEnd() : FString(); }
    bool CanSave() const
    {
        if (NameField->GetText().ToString().TrimStartAndEnd().IsEmpty()) return false;
        if (!ColorField) return true;
        const FString Value = ColorText();
        if (Value.Len() != 7 || Value[0] != '#') return false;
        for (int32 I = 1; I < Value.Len(); ++I) if (!FChar::IsHexDigit(Value[I])) return false;
        return true;
    }
    FReply Save()
    {
        if (CanSave()) OnSave.ExecuteIfBound(NameField->GetText().ToString().TrimStartAndEnd(), ColorText());
        return FReply::Handled();
    }
    void CommitText(const FText&, ETextCommit::Type Commit)
    {
        if (Commit == ETextCommit::OnEnter) Save();
    }
    FReply ChooseColor()
    {
        FColorPickerArgs Args;
        Args.ParentWidget = SharedThis(this);
        Args.InitialColor = FLinearColor::FromSRGBColor(FColor::FromHex(ColorText()));
        Args.bOnlyRefreshOnOk = true;
        Args.OnColorCommitted = FOnLinearColorValueChanged::CreateSP(this,&SAnnotationEditor::PickedColor);
        OpenColorPicker(Args);
        return FReply::Handled();
    }
    void PickedColor(FLinearColor C)
    {
        ColorField->SetText(FText::FromString(TEXT("#") + C.ToFColorSRGB().ToHex().Left(6)));
    }
    FOnSave OnSave;
    FSimpleDelegate OnCancel;
    TSharedPtr<SEditableTextBox> NameField, ColorField;
};
}
