@echo off
setlocal EnableExtensions
set "ROOT=%~dp0"
set "PY=%ROOT%.venv_release\Scripts\python.exe"
set "STEP=Opening project folder"
pushd "%ROOT%"
if errorlevel 1 goto failed

set "STEP=Locating release environment"
if not exist "%PY%" (
  echo ERROR: Release environment is missing.
  echo Create it with: python -m venv .venv_release
  goto failed
)

set "SDL_VIDEODRIVER=dummy"
set "SDL_AUDIODRIVER=dummy"
set "AUTOBEAT_DATA_DIR=%ROOT%artifacts\release_build_data"

set "STEP=Installing build-only dependencies"
"%PY%" -m pip install --disable-pip-version-check -r "%ROOT%requirements-build.txt"
if errorlevel 1 goto failed

set "STEP=Checking dependencies"
"%PY%" -m pip check
if errorlevel 1 goto failed

set "STEP=Running tests"
"%PY%" -m unittest discover -s "%ROOT%tests" -v
if errorlevel 1 goto failed

set "STEP=Rebuilding user guide PDF"
"%PY%" "%ROOT%tools\build_user_guide_pdf.py"
if errorlevel 1 goto failed
if /i "%~1"=="--check-only" goto checked

set "STEP=Cleaning previous build directories"
if exist "%ROOT%build_release" rmdir /s /q "%ROOT%build_release"
if exist "%ROOT%build_release" goto failed
if exist "%ROOT%build_work_release" rmdir /s /q "%ROOT%build_work_release"
if exist "%ROOT%build_work_release" goto failed
if exist "%ROOT%release\_staging" rmdir /s /q "%ROOT%release\_staging"
if exist "%ROOT%release\_staging" goto failed

set "STEP=Building executable"
"%PY%" -m PyInstaller --noconfirm --clean --distpath "%ROOT%build_release" --workpath "%ROOT%build_work_release" "%ROOT%AutoBeat5.spec"
if errorlevel 1 goto failed

set "STEP=Preparing release files"
"%PY%" "%ROOT%tools\prepare_sales_release.py" --dist-dir "%ROOT%build_release\AutoBeat5"
if errorlevel 1 goto failed

set "STEP=Packaging ZIP"
"%PY%" "%ROOT%tools\package_trial_zip.py"
if errorlevel 1 goto failed

set "STEP=Validating release ZIP"
"%PY%" "%ROOT%tools\release_preflight.py"
if errorlevel 1 goto failed

echo SALES RELEASE PASSED: %ROOT%release\Otoasobi_Windows.zip
popd
if /i not "%~1"=="--no-pause" pause
exit /b 0

:checked
echo BUILD CHECK PASSED. EXE and ZIP were not rebuilt.
popd
exit /b 0

:failed
echo.
echo BUILD FAILED: %STEP%
echo Do not distribute an older ZIP as the result of this run.
popd
if /i "%~1"=="--no-pause" exit /b 1
if /i "%~1"=="--check-only" exit /b 1
pause
exit /b 1
