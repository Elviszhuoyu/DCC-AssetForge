#pragma once

#include "Modules/ModuleManager.h"
#include "Templates/SharedPointer.h"

class FSlateStyleSet;
class IConsoleObject;

class FAssetForgeEditorModule : public IModuleInterface
{
public:
    virtual void StartupModule() override;
    virtual void ShutdownModule() override;

private:
    void RegisterStyle();
    void UnregisterStyle();
    void RegisterMenus();
    void UnregisterMenus();
    void OpenGateWorkbench();
    TSharedRef<class SDockTab> SpawnGateTab(const class FSpawnTabArgs& Args);

    TSharedPtr<FSlateStyleSet> StyleSet;
    IConsoleObject* GateConsoleCommand = nullptr;
};
