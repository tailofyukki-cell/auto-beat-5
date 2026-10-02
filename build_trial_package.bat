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
if not exist "release\_staging\AutoBeat5\rewards\locked" mkdir "release\_staging\AutoBeat5\rewards\locked"
if not exist "release\_staging\AutoBeat5\rewards\unlocked" mkdir "release\_staging\AutoBeat5\rewards\unlocked"
attrib +h "release\_staging\AutoBeat5\rewards\locked" >nul 2>nul
xcopy "assets" "release\_staging\AutoBeat5\assets\" /E /I /Y >nul
if %errorlevel% neq 0 (
  echo ERROR: Failed to copy assets folder.
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
python tools\build_user_guide_pdf.py
if %errorlevel% neq 0 (
  echo ERROR: Failed to build user guide PDF.
  pause
  exit /b 1
)
copy /Y "docs\AutoBeat5_User_Guide.pdf" "release\_staging\AutoBeat5\AutoBeat5_User_Guide.pdf" >nul
if %errorlevel% neq 0 (
  echo ERROR: Failed to copy user guide PDF.
  pause
  exit /b 1
)
python tools\package_trial_zip.py --trial
if %errorlevel% neq 0 (
  echo ERROR: Failed to create UTF-8 ZIP package.
  pause
  exit /b 1
)
echo Trial ZIP created: release\AutoBeat5_Trial_Windows.zip
pause

