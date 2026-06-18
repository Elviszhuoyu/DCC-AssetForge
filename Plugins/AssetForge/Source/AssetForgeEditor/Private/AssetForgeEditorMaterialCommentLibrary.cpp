#include "AssetForgeEditorMaterialCommentLibrary.h"

#if WITH_EDITOR
#include "Kismet2/BlueprintEditorUtils.h"
#include "MaterialGraph/MaterialGraph.h"
#include "MaterialGraph/MaterialGraphNode_Comment.h"
#include "MaterialGraph/MaterialGraphSchema.h"
#include "Materials/Material.h"
#include "Materials/MaterialExpressionComment.h"
#include "UObject/UObjectIterator.h"
#endif

namespace
{
#if WITH_EDITOR
constexpr int32 AFCommentFontSize = 20;

struct FAFCommentSpec
{
	const TCHAR* Key;
	const TCHAR* Text;
	FIntPoint Position;
	FIntPoint Size;
	FLinearColor Color;
};

const FAFCommentSpec AFCommentSpecs[] = {
	{
		TEXT("AF 01"),
		TEXT("AF 01 UV 坐标\n统一贴图采样入口：TexCoord0 + UVTiling。\nUV 问题优先回到模型或展开修复。"),
		FIntPoint(-1260, -980),
		FIntPoint(920, 280),
		FLinearColor(0.16f, 0.32f, 0.72f, 0.30f)
	},
	{
		TEXT("AF 02"),
		TEXT("AF 02 BaseColor 基础色\nBaseColor RGB 控制颜色，Alpha 可作为 Masked 镂空来源。\n颜色贴图保持 sRGB。"),
		FIntPoint(-1080, -560),
		FIntPoint(1760, 340),
		FLinearColor(0.18f, 0.55f, 0.36f, 0.30f)
	},
	{
		TEXT("AF 03"),
		TEXT("AF 03 Normal 法线\nNormal 贴图必须使用 Normal sampler。\nNormalStrength 只调强度，不改变贴图语义。"),
		FIntPoint(-1080, -60),
		FIntPoint(1480, 300),
		FLinearColor(0.14f, 0.45f, 0.68f, 0.30f)
	},
	{
		TEXT("AF 04"),
		TEXT("AF 04 ARM / ORM 打包 PBR\nR=AO，G=Roughness，B=Metallic。\n必须关闭 sRGB，并使用 Masks 采样。"),
		FIntPoint(-1080, 340),
		FIntPoint(1520, 540),
		FLinearColor(0.78f, 0.52f, 0.16f, 0.30f)
	},
	{
		TEXT("AF 05"),
		TEXT("AF 05 Imperfection 瑕疵\n污渍、磨损、划痕强度默认 0。\n实例按资产需要开启，不默认污染干净材质。"),
		FIntPoint(-1080, 900),
		FIntPoint(1520, 340),
		FLinearColor(0.50f, 0.34f, 0.72f, 0.30f)
	},
	{
		TEXT("AF 06"),
		TEXT("AF 06 Emissive 自发光\nUseEmissive 开启后生效。\n普通道具默认关闭，避免实例意外发光。"),
		FIntPoint(-1080, 1320),
		FIntPoint(1600, 360),
		FLinearColor(0.82f, 0.36f, 0.14f, 0.30f)
	},
	{
		TEXT("AF 07"),
		TEXT("AF 07 Opacity / Mask 透明与镂空\n默认使用 BaseColor.A 作为 Masked 来源。\n只有存在独立遮罩贴图时才开启 UseSeparateOpacityMask。"),
		FIntPoint(-1080, 1760),
		FIntPoint(1700, 620),
		FLinearColor(0.74f, 0.22f, 0.26f, 0.30f)
	},
};

template<typename FuncType>
void ForEachAFComment(UMaterial* Material, FuncType&& Func)
{
	TSet<UMaterialExpressionComment*> Visited;
	for (UMaterialExpressionComment* Comment : Material->GetEditorComments())
	{
		if (Comment && Comment->Text.StartsWith(TEXT("AF ")))
		{
			Visited.Add(Comment);
			Func(Comment);
		}
	}

	for (TObjectIterator<UMaterialExpressionComment> It; It; ++It)
	{
		UMaterialExpressionComment* Comment = *It;
		if (!Comment || Visited.Contains(Comment) || Comment->GetOuter() != Material || !Comment->Text.StartsWith(TEXT("AF ")))
		{
			continue;
		}
		Visited.Add(Comment);
		Func(Comment);
	}
}

const FAFCommentSpec* FindAFCommentSpec(const FString& Text)
{
	for (const FAFCommentSpec& Spec : AFCommentSpecs)
	{
		if (Text.StartsWith(Spec.Key))
		{
			return &Spec;
		}
	}
	return nullptr;
}

FString AFCommentKey(const FString& Text)
{
	const FAFCommentSpec* Spec = FindAFCommentSpec(Text);
	return Spec ? FString(Spec->Key) : FString();
}

void NormalizeAFCommentOwnership(UMaterial* Material, UMaterialExpressionComment* Comment)
{
	if (!Material || !Comment)
	{
		return;
	}

	if (Comment->GetOuter() != Material)
	{
		Comment->Rename(nullptr, Material, REN_DontCreateRedirectors);
	}
	Comment->Material = Material;
	Comment->Function = nullptr;
	Comment->SubgraphExpression = nullptr;

	bool bInCommentCollection = false;
	for (UMaterialExpressionComment* ExistingComment : Material->GetEditorComments())
	{
		if (ExistingComment == Comment)
		{
			bInCommentCollection = true;
			break;
		}
	}
	if (!bInCommentCollection)
	{
		Material->GetExpressionCollection().AddComment(Comment);
	}
}

void RemoveDuplicateAFComment(UMaterial* Material, UMaterialExpressionComment* Comment)
{
	if (!Material || !Comment)
	{
		return;
	}

	Comment->Modify();
	if (UMaterialGraphNode_Comment* GraphComment = Cast<UMaterialGraphNode_Comment>(Comment->GraphNode))
	{
		if (UMaterialGraph* MaterialGraph = Cast<UMaterialGraph>(GraphComment->GetGraph()))
		{
			MaterialGraph->Modify();
		}
		GraphComment->Modify();
		GraphComment->MaterialExpressionComment = nullptr;
		GraphComment->DestroyNode();
	}

	Comment->GraphNode = nullptr;
	Material->GetExpressionCollection().RemoveComment(Comment);
}

UMaterialGraph* FindAFMaterialGraph(UMaterial* Material, UMaterialExpressionComment* Comment)
{
	if (!Material)
	{
		return nullptr;
	}

	if (Comment)
	{
		if (UMaterialGraphNode_Comment* ExistingGraphComment = Cast<UMaterialGraphNode_Comment>(Comment->GraphNode))
		{
			return Cast<UMaterialGraph>(ExistingGraphComment->GetGraph());
		}
	}

	if (Material->MaterialGraph)
	{
		return Material->MaterialGraph;
	}

	for (TObjectIterator<UMaterialGraph> It; It; ++It)
	{
		UMaterialGraph* Graph = *It;
		if (Graph && Graph->Material == Material && !Graph->SubgraphExpression)
		{
			Material->MaterialGraph = Graph;
			return Graph;
		}
	}

	Material->Modify();
	Material->MaterialGraph = CastChecked<UMaterialGraph>(FBlueprintEditorUtils::CreateNewGraph(
		Material,
		NAME_None,
		UMaterialGraph::StaticClass(),
		UMaterialGraphSchema::StaticClass()));
	Material->MaterialGraph->Material = Material;
	Material->MaterialGraph->MaterialFunction = nullptr;
	Material->MaterialGraph->RebuildGraph();
	return Material->MaterialGraph;
}

UMaterialGraphNode_Comment* EnsureAFGraphComment(UMaterial* Material, UMaterialExpressionComment* Comment);

void SyncAFGraphCommentFromExpression(UMaterial* Material, UMaterialExpressionComment* Comment)
{
	if (!Material || !Comment)
	{
		return;
	}

	const FAFCommentSpec* Spec = FindAFCommentSpec(Comment->Text);
	const FIntPoint Position(
		Comment->MaterialExpressionEditorX,
		Comment->MaterialExpressionEditorY);
	const FIntPoint Size(
		Comment->SizeX > 0 ? Comment->SizeX : (Spec ? Spec->Size.X : 600),
		Comment->SizeY > 0 ? Comment->SizeY : (Spec ? Spec->Size.Y : 220));

	if (UMaterialGraphNode_Comment* GraphComment = EnsureAFGraphComment(Material, Comment))
	{
		GraphComment->Modify();
		GraphComment->MaterialExpressionComment = Comment;
		GraphComment->NodeComment = Comment->Text;
		GraphComment->NodePosX = Position.X;
		GraphComment->NodePosY = Position.Y;
		GraphComment->NodeWidth = Size.X;
		GraphComment->NodeHeight = Size.Y;
		GraphComment->FontSize = Comment->FontSize > 0 ? Comment->FontSize : AFCommentFontSize;
		GraphComment->CommentColor = Comment->CommentColor;
		GraphComment->bCommentBubbleVisible = false;
		GraphComment->bCommentBubbleVisible_InDetailsPanel = false;
		GraphComment->bCommentBubblePinned = false;
		GraphComment->bColorCommentBubble = false;
	}
}

void RebuildAFMaterialGraph(UMaterial* Material)
{
	ForEachAFComment(Material, [Material](UMaterialExpressionComment* Comment)
	{
		NormalizeAFCommentOwnership(Material, Comment);
	});

	if (UMaterialGraph* MaterialGraph = FindAFMaterialGraph(Material, nullptr))
	{
		MaterialGraph->Modify();
		MaterialGraph->RebuildGraph();
		ForEachAFComment(Material, [Material](UMaterialExpressionComment* Comment)
		{
			SyncAFGraphCommentFromExpression(Material, Comment);
		});
		MaterialGraph->NotifyGraphChanged();
	}
}

UMaterialGraphNode_Comment* EnsureAFGraphComment(UMaterial* Material, UMaterialExpressionComment* Comment)
{
	if (!Material || !Comment)
	{
		return nullptr;
	}

	NormalizeAFCommentOwnership(Material, Comment);

	if (UMaterialGraphNode_Comment* ExistingGraphComment = Cast<UMaterialGraphNode_Comment>(Comment->GraphNode))
	{
		return ExistingGraphComment;
	}

	UMaterialGraph* MaterialGraph = FindAFMaterialGraph(Material, Comment);
	if (!MaterialGraph)
	{
		return nullptr;
	}

	MaterialGraph->Modify();
	UMaterialGraphNode_Comment* GraphComment = MaterialGraph->AddComment(Comment, false);
	if (GraphComment)
	{
		GraphComment->Modify();
		GraphComment->MaterialExpressionComment = Comment;
		Comment->GraphNode = GraphComment;
	}
	return GraphComment;
}

void ApplyAFCommentSpec(UMaterial* Material, UMaterialExpressionComment* Comment, const FAFCommentSpec& Spec)
{
	NormalizeAFCommentOwnership(Material, Comment);

	Comment->Modify();
	Comment->Text = Spec.Text;
	Comment->Desc = Spec.Text;
	Comment->CommentColor = Spec.Color;
	Comment->MaterialExpressionEditorX = Spec.Position.X;
	Comment->MaterialExpressionEditorY = Spec.Position.Y;
	Comment->SizeX = Spec.Size.X;
	Comment->SizeY = Spec.Size.Y;
	Comment->FontSize = AFCommentFontSize;
	Comment->bCommentBubbleVisible_InDetailsPanel = false;
	Comment->bColorCommentBubble = false;
	Comment->bGroupMode = true;

	if (UMaterialGraphNode_Comment* GraphComment = EnsureAFGraphComment(Material, Comment))
	{
		GraphComment->Modify();
		GraphComment->MaterialExpressionComment = Comment;
		GraphComment->NodeComment = Spec.Text;
		GraphComment->NodePosX = Spec.Position.X;
		GraphComment->NodePosY = Spec.Position.Y;
		GraphComment->NodeWidth = Spec.Size.X;
		GraphComment->NodeHeight = Spec.Size.Y;
		GraphComment->FontSize = AFCommentFontSize;
		GraphComment->CommentColor = Spec.Color;
		GraphComment->bCommentBubbleVisible = false;
		GraphComment->bCommentBubbleVisible_InDetailsPanel = false;
		GraphComment->bCommentBubblePinned = false;
		GraphComment->bColorCommentBubble = false;
		if (UMaterialGraph* MaterialGraph = Cast<UMaterialGraph>(GraphComment->GetGraph()))
		{
			MaterialGraph->NotifyGraphChanged();
		}
	}
}
#endif
}

int32 UAssetForgeEditorMaterialCommentLibrary::RepairAssetForgeCommentBlocks(UMaterial* Material)
{
#if WITH_EDITOR
	if (!Material)
	{
		return 0;
	}

	TArray<UMaterialExpressionComment*> Comments;
	ForEachAFComment(Material, [&](UMaterialExpressionComment* Comment)
	{
		Comments.AddUnique(Comment);
	});

	TMap<FString, UMaterialExpressionComment*> KeptComments;
	int32 RemovedCount = 0;
	for (UMaterialExpressionComment* Comment : Comments)
	{
		const FString Key = AFCommentKey(Comment ? Comment->Text : FString());
		if (Key.IsEmpty())
		{
			continue;
		}

		UMaterialExpressionComment** Existing = KeptComments.Find(Key);
		if (!Existing)
		{
			KeptComments.Add(Key, Comment);
			continue;
		}

		const bool bCurrentHasGraph = Comment && Comment->GraphNode != nullptr;
		const bool bExistingHasGraph = *Existing && (*Existing)->GraphNode != nullptr;
		if (bCurrentHasGraph && !bExistingHasGraph)
		{
			RemoveDuplicateAFComment(Material, *Existing);
			KeptComments[Key] = Comment;
		}
		else
		{
			RemoveDuplicateAFComment(Material, Comment);
		}
		++RemovedCount;
	}

	int32 RepairedCount = 0;
	for (const FAFCommentSpec& Spec : AFCommentSpecs)
	{
		if (UMaterialExpressionComment** CommentPtr = KeptComments.Find(Spec.Key))
		{
			ApplyAFCommentSpec(Material, *CommentPtr, Spec);
			++RepairedCount;
		}
	}

	if (RepairedCount > 0 || RemovedCount > 0)
	{
		Material->MarkPackageDirty();
		Material->PostEditChange();
		RebuildAFMaterialGraph(Material);
	}
	return RepairedCount;
#else
	return 0;
#endif
}

FString UAssetForgeEditorMaterialCommentLibrary::DescribeAssetForgeCommentBlocks(UMaterial* Material)
{
#if WITH_EDITOR
	if (!Material)
	{
		return TEXT("missing material");
	}

	RebuildAFMaterialGraph(Material);

	TArray<FString> Lines;
	TMap<FString, int32> CommentKeyCounts;
	int32 ExpressionCommentCount = 0;
	ForEachAFComment(Material, [&](UMaterialExpressionComment* Comment)
	{
		++ExpressionCommentCount;
		const FString Key = AFCommentKey(Comment->Text);
		if (!Key.IsEmpty())
		{
			CommentKeyCounts.FindOrAdd(Key)++;
		}

		const int32 NewlineIndex = Comment->Text.Find(TEXT("\n"), ESearchCase::CaseSensitive, ESearchDir::FromStart);
		const FString FirstLine = NewlineIndex == INDEX_NONE ? Comment->Text : Comment->Text.Left(NewlineIndex);
		Lines.Add(FString::Printf(TEXT("%s|X=%d|Y=%d|SizeX=%d|SizeY=%d|FontSize=%d|Bubble=%s"),
			*FirstLine,
			Comment->MaterialExpressionEditorX,
			Comment->MaterialExpressionEditorY,
			Comment->SizeX,
			Comment->SizeY,
			Comment->FontSize,
			Comment->bCommentBubbleVisible_InDetailsPanel ? TEXT("true") : TEXT("false")));
	});

	int32 LinkedGraphCommentCount = 0;
	int32 OrphanGraphCommentCount = 0;
	if (UMaterialGraph* MaterialGraph = FindAFMaterialGraph(Material, nullptr))
	{
		for (UEdGraphNode* Node : MaterialGraph->Nodes)
		{
			const UMaterialGraphNode_Comment* GraphComment = Cast<UMaterialGraphNode_Comment>(Node);
			if (!GraphComment)
			{
				continue;
			}

			const UMaterialExpressionComment* Comment = GraphComment->MaterialExpressionComment;
			if (!Comment)
			{
				if (GraphComment->NodeComment.StartsWith(TEXT("AF ")))
				{
					++OrphanGraphCommentCount;
				}
				continue;
			}
			if (Comment->GetOuter() != Material || !Comment->Text.StartsWith(TEXT("AF ")))
			{
				continue;
			}

			++LinkedGraphCommentCount;
			const int32 NewlineIndex = Comment->Text.Find(TEXT("\n"), ESearchCase::CaseSensitive, ESearchDir::FromStart);
			const FString FirstLine = NewlineIndex == INDEX_NONE ? Comment->Text : Comment->Text.Left(NewlineIndex);
			Lines.Add(FString::Printf(TEXT("GRAPH %s|X=%d|Y=%d|NodeWidth=%d|NodeHeight=%d|StoredFontSize=%d|VisualFontSize=%d"),
				*FirstLine,
				GraphComment->NodePosX,
				GraphComment->NodePosY,
				GraphComment->NodeWidth,
				GraphComment->NodeHeight,
				GraphComment->FontSize,
				GraphComment->GetFontSize()));
		}
	}

	int32 DuplicateCommentCount = 0;
	for (const TPair<FString, int32>& Pair : CommentKeyCounts)
	{
		DuplicateCommentCount += FMath::Max(0, Pair.Value - 1);
	}

	Lines.Insert(FString::Printf(TEXT("SUMMARY expected_af_comments=%d|expression_comments=%d|linked_graph_comments=%d|orphan_graph_comments=%d|duplicate_comments=%d"),
		UE_ARRAY_COUNT(AFCommentSpecs),
		ExpressionCommentCount,
		LinkedGraphCommentCount,
		OrphanGraphCommentCount,
		DuplicateCommentCount), 0);
	return FString::Join(Lines, TEXT("\n"));
#else
	return TEXT("editor only");
#endif
}
