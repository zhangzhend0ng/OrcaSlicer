@echo off
REM MCP worktree baseline build (Release, VS2022)
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 (
  echo VCVARS_FAILED
  exit /b 1
)
set WP=%CD%
set DEPS=%WP%\deps\build\OrcaSlicer_dep

if not exist "%WP%\build" mkdir %WP%\build
cd /d %WP%\build

echo === CONFIGURING ===
cmake .. -G "Visual Studio 17 2022" -A x64 -DBBL_RELEASE_TO_PUBLIC=1 -DORCA_TOOLS=ON -DCMAKE_PREFIX_PATH="%DEPS%/usr/local" -DOPENSSL_ROOT_DIR="%DEPS%/usr/local" -DCMAKE_INSTALL_PREFIX="./Snapmaker_Orca" -DCMAKE_BUILD_TYPE=Release -DWIN10SDK_PATH="%WindowsSdkDir%Include\%WindowsSDKVersion%\"
if errorlevel 1 (
  echo CONFIGURE_FAILED
  exit /b 1
)
echo === CONFIGURE_OK ===

echo === BUILDING Snapmaker_Orca ===
cmake --build . --config Release --target Snapmaker_Orca -- -m
if errorlevel 1 (
  echo BUILD_FAILED
  exit /b 1
)
echo === BUILD_OK ===
