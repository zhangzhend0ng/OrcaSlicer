@echo off
REM Incremental build of libslic3r_gui (MCP C++ work)
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 (
  echo VCVARS_FAILED
  exit /b 1
)
cd /d %~dp0
echo === BUILDING libslic3r_gui ===
cmake --build build --config Release --target libslic3r_gui -- -m
if errorlevel 1 (
  echo BUILD_FAILED
  exit /b 1
)
echo === BUILD_OK ===
