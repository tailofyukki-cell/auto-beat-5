@echo off
setlocal EnableExtensions
set "ROOT=%~dp0"
set "PY=%ROOT%.venv_release\Scripts\python.exe"

if not exist "%PY%" (
  echo ERROR: Release environment is missing.
  echo Create it with: python -m venv .venv_release
  exit /b 1
)

set "SDL_VIDEODRIVER=dummy"
set "SDL_AUDIODRIVER=dummy"
set "AUTOBEAT_DATA_DIR=%ROOT%artifacts\release_build_data"

"%PY%" -m pip check
if errorlevel 1 exit /b 1

"%PY%" -m unittest discover -s "%ROOT%tests" -v
if errorlevel 1 exit /b 1

if exist "%ROOT%build_release" rmdir /s /q "%ROOT%build_release"
if exist "%ROOT%build_work_release" rmdir /s /q "%ROOT%build_work_release"
if exist "%ROOT%release\_staging" rmdir /s /q "%ROOT%release\_staging"

"%PY%" -m PyInstaller --noconfirm --clean --distpath "%ROOT%build_release" --workpath "%ROOT%build_work_release" "%ROOT%AutoBeat5.spec"
if errorlevel 1 exit /b 1

"%PY%" "%ROOT%tools\prepare_sales_release.py" --dist-dir "%ROOT%build_release\AutoBeat5"
if errorlevel 1 exit /b 1

"%PY%" "%ROOT%tools\package_trial_zip.py"
if errorlevel 1 exit /b 1

"%PY%" "%ROOT%tools\release_preflight.py"
if errorlevel 1 exit /b 1

echo SALES RELEASE PASSED: %ROOT%release\AutoBeat5_Trial_Windows.zip
exit /b 0
