#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "AssetForgeEditorMaterialCommentLibrary.generated.h"

class UMaterial;

UCLASS()
class ASSETFORGEEDITOR_API UAssetForgeEditorMaterialCommentLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintCallable, Category = "DCC AssetForge|Material")
	static int32 RepairAssetForgeCommentBlocks(UMaterial* Material);

	UFUNCTION(BlueprintCallable, Category = "DCC AssetForge|Material")
	static FString DescribeAssetForgeCommentBlocks(UMaterial* Material);
};
