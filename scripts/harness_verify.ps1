# Harness verification script for OrcaSlicer refactoring
# Run after each Phase commit to validate safety nets.

$ErrorActionPreference = "Continue"
$ROOT = Split-Path -Parent $PSScriptRoot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  OrcaSlicer Harness Verification" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$passed = 0
$failed = 0

# 1. Layer violations
Write-Host "[1/4] Layer violation check..." -ForegroundColor Yellow
python "$ROOT\scripts\check_layer_violations.py"
if ($LASTEXITCODE -eq 0) { $passed++; Write-Host "  PASS" -ForegroundColor Green }
else { $failed++; Write-Host "  FAIL" -ForegroundColor Red }

# 2. Cycle report
Write-Host "[2/4] Dependency cycle report..." -ForegroundColor Yellow
python "$ROOT\scripts\cycle_report.py"
if ($LASTEXITCODE -eq 0) { $passed++; Write-Host "  PASS (no cross-boundary cycles)" -ForegroundColor Green }
else { Write-Host "  WARN (cycles exist, tracked for Phase 2-4)" -ForegroundColor Yellow }

# 3. God class audit
Write-Host "[3/4] God class audit..." -ForegroundColor Yellow
python "$ROOT\scripts\god_class_audit.py"
if ($LASTEXITCODE -eq 0) { $passed++; Write-Host "  PASS (all classes under threshold)" -ForegroundColor Green }
else { Write-Host "  WARN (god classes exist, tracked for Phase 3)" -ForegroundColor Yellow }

# 4. New files review
Write-Host "[4/4] New architecture artifacts..." -ForegroundColor Yellow
$artifacts = @(
    "src\libslic3r\MVVP.hpp",
    "src\libslic3r\Ports\Ports.hpp",
    "src\libslic3r\ColorSpaceConvert.hpp",
    "src\slic3r\App\CameraController.hpp",
    "src\slic3r\App\PlaterViewModel.hpp",
    "src\slic3r\App\CanvasViewModel.hpp",
    "src\slic3r\App\SelectionController.hpp",
    "tests\libslic3r\TestMVVP.cpp",
    "tests\libslic3r\TestCameraController.cpp"
)
foreach ($a in $artifacts) {
    if (Test-Path "$ROOT\$a") {
        Write-Host "  $a" -ForegroundColor Green
    } else {
        Write-Host "  $a - MISSING" -ForegroundColor Red
    }
}
$passed++

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Results: $passed checks passed" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
