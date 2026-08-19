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
echo Build complete: dist\AutoBeat5\AutoBeat5.exe
pause
