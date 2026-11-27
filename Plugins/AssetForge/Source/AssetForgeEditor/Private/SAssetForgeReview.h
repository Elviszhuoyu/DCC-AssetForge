#pragma once

#include "CoreMinimal.h"

class SDockTab;
class SWidget;

namespace AssetForgeReview
{
TSharedRef<SDockTab> CreateTab(const TSharedRef<SWidget>& Content);
TSharedRef<SWidget> CreatePanel();
void Run(const FString& Action, const FString& Argument);
void OpenImported(const FString& Receipt);
void Open(const TArray<FString>& Args = {});
}
