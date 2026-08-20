@echo off
setlocal
cd /d "%~dp0"
echo Building AutoBeat 5 trial package...
if exist "release\_staging" rmdir /s /q "release\_staging"
if exist "build_trial_package" rmdir /s /q "build_trial_package"
python -m PyInstaller --noconfirm --clean --distpath "release\_staging" --workpath "build_trial_package" AutoBeat5.spec
if %errorlevel% neq 0 (
  echo ERROR: PyInstaller build failed.
  pause
  exit /b 1
)
xcopy "rewards" "release\_staging\AutoBeat5\rewards\" /E /I /Y >nul
if %errorlevel% neq 0 (
  echo ERROR: Failed to copy rewards folder.
  pause
  exit /b 1
)
xcopy "demo_songs" "release\_staging\AutoBeat5\demo_songs\" /E /I /Y >nul
if %errorlevel% neq 0 (
  echo ERROR: Failed to copy demo_songs folder.
  pause
  exit /b 1
)
copy /Y "TRIAL_README.txt" "release\_staging\AutoBeat5\TRIAL_README.txt" >nul
if %errorlevel% neq 0 (
  echo ERROR: Failed to copy trial README.
  pause
  exit /b 1
)
python tools\package_trial_zip.py
if %errorlevel% neq 0 (
  echo ERROR: Failed to create UTF-8 ZIP package.
  pause
  exit /b 1
)
echo Trial ZIP created: release\AutoBeat5_Trial_Windows.zip
pause
