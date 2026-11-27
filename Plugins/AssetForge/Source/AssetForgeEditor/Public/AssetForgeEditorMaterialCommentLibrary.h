#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "AssetForgeEditorMaterialCommentLibrary.generated.h"

class UMaterial;
class UMaterialInterface;

UCLASS()
class ASSETFORGEEDITOR_API UAssetForgeEditorMaterialCommentLibrary : public UBlueprintFunctionLibrary
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintCallable, Category = "DCC AssetForge|Material")
	static int32 RepairAssetForgeCommentBlocks(UMaterial* Material);

	UFUNCTION(BlueprintCallable, Category = "DCC AssetForge|Material")
	static FString DescribeAssetForgeCommentBlocks(UMaterial* Material);

	UFUNCTION(BlueprintCallable, Category = "DCC AssetForge|Material")
	static FString ReadAssetForgeCommentBlocks(UMaterial* Material);

	UFUNCTION(BlueprintCallable, Category = "DCC AssetForge|Material")
	static bool TryReadAssetForgeMaterialCompileErrors(const UMaterialInterface* Material, TArray<FString>& OutErrors);
};
