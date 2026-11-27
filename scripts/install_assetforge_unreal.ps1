param(
    [Parameter(Mandatory = $true)]
    [string] $Project,

    [Parameter(Mandatory = $true)]
    [string] $EngineRoot,

    [switch] $CheckOnly,

    [switch] $Source
)

$ErrorActionPreference = 'Stop'
$ueRoot = (Get-Item -LiteralPath $EngineRoot).FullName
if ((Split-Path -Leaf $ueRoot) -ieq 'Engine') {
    $ueRoot = Split-Path -Parent $ueRoot
}

$python = Join-Path $ueRoot 'Engine\Binaries\ThirdParty\Python3\Win64\python.exe'
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw 'Unreal Engine Python was not found. Select the Unreal Engine installation folder for this project.'
}

$projectPath = (Get-Item -LiteralPath $Project).FullName
$arguments = @('-B', (Join-Path $PSScriptRoot 'Scripts\InstallUnreal.py'), $projectPath, $ueRoot)
if ($Source) {
    $arguments += '--source'
}
if ($CheckOnly) {
    $arguments += '--check-only'
}
& $python @arguments
exit $LASTEXITCODE
