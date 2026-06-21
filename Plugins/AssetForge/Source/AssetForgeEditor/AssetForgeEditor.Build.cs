using UnrealBuildTool;

public class AssetForgeEditor : ModuleRules
{
    public AssetForgeEditor(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

        PrivateDependencyModuleNames.AddRange(
            new string[]
            {
                "Core",
                "CoreUObject",
                "DesktopPlatform",
                "Engine",
                "InputCore",
                "Json",
                "JsonUtilities",
                "Projects",
                "PythonScriptPlugin",
                "Slate",
                "SlateCore",
                "ToolMenus",
                "UnrealEd"
            }
        );
    }
}
