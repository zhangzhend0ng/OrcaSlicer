@echo off
REM Build ALL test executables for a full ctest run (long).
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul
if errorlevel 1 (
  echo VCVARS_FAILED
  exit /b 1
)
cd /d %~dp0
echo === BUILDING all tests ===
cmake --build build --config Release --target tests -- -m
if errorlevel 1 (
  echo BUILD_FAILED
  exit /b 1
)
echo === ALL_TESTS_BUILD_OK ===
