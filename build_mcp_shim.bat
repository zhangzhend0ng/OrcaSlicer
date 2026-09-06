@echo off
REM Build the snapmaker-orca.exe GUI shim (and anything missing)
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 (
  echo VCVARS_FAILED
  exit /b 1
)
cd /d %~dp0
echo === BUILDING Snapmaker_Orca_app_gui ===
cmake --build build --config Release --target Snapmaker_Orca_app_gui -- -m
if errorlevel 1 (
  echo BUILD_FAILED
  exit /b 1
)
echo === BUILD_OK ===
