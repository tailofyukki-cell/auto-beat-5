# -*- mode: python ; coding: utf-8 -*-
"""AutoBeat 5 Windows distribution spec (onedir)."""
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

project_root = Path(SPECPATH)
datas = []
binaries = []
hiddenimports = []

for package in ("pygame", "librosa", "soundfile", "scipy", "sklearn", "numba", "llvmlite"):
    package_datas, package_binaries, package_hiddenimports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hiddenimports

for folder in ("fonts", "licenses", "docs", "rewards", "demo_songs"):
    source = project_root / folder
    if source.exists():
        datas.append((str(source), folder))

analysis = Analysis(
    [str(project_root / "main.py")],
    pathex=[str(project_root), str(project_root / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter.test", "pytest", "matplotlib", "IPython"],
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
