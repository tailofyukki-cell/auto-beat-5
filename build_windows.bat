@echo off
setlocal
cd /d "%~dp0"
echo Installing AutoBeat 5 build dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
  echo ERROR: Dependency installation failed.
  pause
  exit /b 1
)
echo Building Windows distribution...
python -m PyInstaller --noconfirm --clean AutoBeat5.spec
if %errorlevel% neq 0 (
  echo ERROR: PyInstaller build failed.
  pause
  exit /b 1
)
echo Copying editable content folders...
if exist "dist\AutoBeat5\rewards" rmdir /s /q "dist\AutoBeat5\rewards"
if exist "dist\AutoBeat5\demo_songs" rmdir /s /q "dist\AutoBeat5\demo_songs"
xcopy "rewards" "dist\AutoBeat5\rewards\" /E /I /Y >nul
if %errorlevel% neq 0 (
  echo ERROR: Failed to copy rewards folder.
  pause
  exit /b 1
)
xcopy "demo_songs" "dist\AutoBeat5\demo_songs\" /E /I /Y >nul
if %errorlevel% neq 0 (
  echo ERROR: Failed to copy demo_songs folder.
  pause
  exit /b 1
)
copy /Y "TRIAL_README.txt" "dist\AutoBeat5\TRIAL_README.txt" >nul
if %errorlevel% neq 0 (
  echo ERROR: Failed to copy trial README.
  pause
  exit /b 1
)
echo Build complete: dist\AutoBeat5\AutoBeat5.exe
pause
