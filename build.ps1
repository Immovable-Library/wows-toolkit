param(
    [ValidateSet("check", "build", "run", "test")]
    [string]$Action = "check",

    [switch]$Release,

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CargoArgs
)

$ErrorActionPreference = "Stop"

Set-Location -LiteralPath $PSScriptRoot

$cargo = Join-Path $env:USERPROFILE ".cargo\bin\cargo.exe"
if (-not (Test-Path -LiteralPath $cargo)) {
    throw "cargo was not found at $cargo"
}

$vcvars64 = "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvars64.bat"
if (-not (Test-Path -LiteralPath $vcvars64)) {
    throw "vcvars64.bat was not found at $vcvars64"
}

$rustupDistServer = $env:RUSTUP_DIST_SERVER
if ([string]::IsNullOrWhiteSpace($rustupDistServer)) {
    $rustupDistServer = "https://rsproxy.cn"
}

$cargoParts = @($cargo, $Action, "-p", "wows_toolkit")
if ($Release) {
    $cargoParts += "--release"
}
$cargoParts += $CargoArgs

$cargoArgsLine = ($cargoParts | Select-Object -Skip 1) -join " "
$cmd = "call `"$vcvars64`" >nul && set RUSTUP_DIST_SERVER=$rustupDistServer && `"$cargo`" $cargoArgsLine"

& cmd.exe /c $cmd
exit $LASTEXITCODE
