# -*- mode: python ; coding: utf-8 -*-
"""AutoBeat 5 Windows distribution spec (onedir)."""
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

project_root = Path(SPECPATH)
datas = []
binaries = []
hiddenimports = []

def is_runtime_module(module_name):
    """Exclude test and documentation modules from the commercial runtime."""
    segments = module_name.split(".")
    return "tests" not in segments and "test" not in segments and "docs" not in segments


for package in ("pygame", "librosa", "soundfile", "scipy", "sklearn", "numba", "llvmlite"):
    # Keep package data and native libraries needed by dynamic loaders, but do
    # not collect test fixtures, docs, or every development-only submodule.
    datas += collect_data_files(
        package,
        excludes=["tests/**", "test/**", "**/tests/**", "**/test/**", "docs/**", "**/docs/**"],
    )
    binaries += collect_dynamic_libs(package)
    hiddenimports += collect_submodules(package, filter=is_runtime_module)

# SciPy 1.18 loads this compatibility namespace dynamically from its
# FFT path. Static PyInstaller analysis can miss it, so include its concrete
# modules explicitly; the release audio probe verifies this in the frozen exe.
hiddenimports += collect_submodules("scipy._external.array_api_compat")

# Runtime font data is needed by the executable. User-facing assets and
# license notices are copied to the distribution root by prepare_sales_release.py.
for folder in ("fonts", "assets"):
    source = project_root / folder
    if source.exists():
        datas.append((str(source), folder))

analysis = Analysis(
    [str(project_root / "main.py")],
    pathex=[str(project_root), str(project_root / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=[
        "tkinter.test", "pytest", "matplotlib", "IPython",
        # Release guard: these are not part of AutoBeat 5 and must never leak
        # in from a developer's global environment.
        "openai", "torch", "torchvision", "transformers", "tiktoken", "cv2",
        "huggingface_hub", "onnxruntime", "PIL",
        # collect_all() can enumerate very large test suites that are never
        # imported by the game. Exclude them from the commercial runtime.
        "pygame.tests", "librosa.tests", "numpy.tests", "scipy.tests",
        "sklearn.tests", "numba.tests", "llvmlite.tests",
    ],
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="AutoBeat5",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=None,
)
coll = COLLECT(
    exe,
    analysis.binaries,
    analysis.zipfiles,
    analysis.datas,
    strip=False,
    upx=False,
    name="AutoBeat5",
)
