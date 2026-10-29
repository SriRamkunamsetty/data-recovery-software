# =====================================================================
# RecoverX - PowerShell Clean-Machine Smoke Test Wrapper
# Windows 10/11 x64 Verification
# =====================================================================
param(
    [string]$ExePath = ""
)

$ErrorActionPreference = "Stop"

Write-Host "=== RecoverX PowerShell Clean-Machine Smoke Test Wrapper ===" -ForegroundColor Cyan
$PythonExe = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"

if (-not [string]::IsNullOrEmpty($ExePath)) {
    Write-Host "Running smoke test targeting packaged binary: $ExePath" -ForegroundColor Yellow
    if (Test-Path $PythonExe) {
        & $PythonExe (Join-Path $PSScriptRoot "smoke_test_clean_machine.py") --exe $ExePath
    } else {
        python (Join-Path $PSScriptRoot "smoke_test_clean_machine.py") --exe $ExePath
    }
} else {
    Write-Host "Running smoke test with default environment..." -ForegroundColor Yellow
    if (Test-Path $PythonExe) {
        & $PythonExe (Join-Path $PSScriptRoot "smoke_test_clean_machine.py")
    } else {
        python (Join-Path $PSScriptRoot "smoke_test_clean_machine.py")
    }
}

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nAll smoke test assertions verified successfully on this machine!" -ForegroundColor Green
    exit 0
} else {
    Write-Host "`nSmoke test failed with exit code $LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
}
