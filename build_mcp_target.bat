@echo off
REM Usage: build_mcp_target.bat <target-name>
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 (
  echo VCVARS_FAILED
  exit /b 1
)
cd /d %~dp0
cmake --build build --config Release --target %1 -- -m
if errorlevel 1 (
  echo BUILD_FAILED
  exit /b 1
)
echo TARGET_%1_OK
