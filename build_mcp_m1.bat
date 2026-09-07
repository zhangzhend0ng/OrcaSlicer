@echo off
REM Build mcp tests + full app after CMake reconfigure
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 (
  echo VCVARS_FAILED
  exit /b 1
)
cd /d %~dp0
set DEPS=%CD%\deps\build\OrcaSlicer_dep

echo === RECONFIGURE ===
cmake -S . -B build -G "Visual Studio 17 2022" -A x64 -DBBL_RELEASE_TO_PUBLIC=1 -DORCA_TOOLS=ON -DBUILD_TESTS=1 -DCMAKE_PREFIX_PATH="%DEPS%/usr/local" -DOPENSSL_ROOT_DIR="%DEPS%/usr/local" -DCMAKE_INSTALL_PREFIX="./Snapmaker_Orca" -DCMAKE_BUILD_TYPE=Release -DWIN10SDK_PATH="%WindowsSdkDir%Include\%WindowsSDKVersion%\"
if errorlevel 1 (
  echo RECONFIGURE_FAILED
  exit /b 1
)
echo === CONFIGURE_OK ===

echo === BUILDING mcp_tests ===
cmake --build build --config Release --target mcp_tests -- -m
if errorlevel 1 (
  echo BUILD_FAILED
  exit /b 1
)
echo === TESTS_BUILD_OK ===

echo === BUILDING Snapmaker_Orca_app_gui ===
cmake --build build --config Release --target Snapmaker_Orca_app_gui -- -m
if errorlevel 1 (
  echo BUILD_FAILED
  exit /b 1
)
echo === BUILD_OK ===
