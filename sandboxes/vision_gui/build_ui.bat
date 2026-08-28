@echo off
rem build_ui.bat — package the vision_gui UI shell into a self-contained
rem onedir app with PyInstaller. Run from sandboxes/vision_gui.
rem
rem Result:  dist\vision_gui_runner\vision_gui_runner.exe
rem Layout (packaged): the driver scripts + harness + templates ship as DATA
rem next to the exe ("run" subcommand re-invokes the exe to run them); the
rem app-under-test is expected at  dist\vision_gui_runner\orca\
rem snapmaker-orca.exe  (or set ORCA_VISION_APP_EXE).
rem
rem mss/MaaFw are excluded: mss is unused by the sandbox code and MaaFw is
rem only needed by the settled m1b experiment (not part of the runner).

setlocal
cd /d %~dp0

.venv\Scripts\pip install pyinstaller || goto :err

.venv\Scripts\pyinstaller --noconfirm --clean --onedir --console ^
  --name vision_gui_runner ^
  --collect-all customtkinter ^
  --add-data "m0_boot_check.py;." ^
  --add-data "m1_minimal_loop.py;." ^
  --add-data "m1b_maa.py;." ^
  --add-data "m2_slice_chain.py;." ^
  --add-data "inspect_window.py;." ^
  --add-data "harness;harness" ^
  --add-data "resource;resource" ^
  --exclude-module mss ^
  --exclude-module maa ^
  --exclude-module MaaFw ^
  ui_runner.py || goto :err

echo.
echo Packaged: dist\vision_gui_runner\vision_gui_runner.exe
echo Put the app-under-test at dist\vision_gui_runner\orca\snapmaker-orca.exe
echo   (or set ORCA_VISION_APP_EXE) before running.
exit /b 0

:err
echo BUILD FAILED
exit /b 1
