using UnrealBuildTool;

public class AssetForgeEditor : ModuleRules
{
    public AssetForgeEditor(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

        PrivateDependencyModuleNames.AddRange(
            new string[]
            {
                "ApplicationCore",
                "AppFramework",
                "AssetRegistry",
                "ContentBrowser",
                "Core",
                "CoreUObject",
                "DesktopPlatform",
                "Engine",
                "InputCore",
                "Json",
                "JsonUtilities",
                "Projects",
                "PythonScriptPlugin",
                "RHI",
                "Slate",
                "SlateCore",
                "ToolMenus",
                "UnrealEd"
            }
        );
    }
}
