"""Windows Explorerでも日本語ファイル名を保持する体験版ZIPを作成する。"""
from __future__ import annotations

import shutil
import argparse
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "release" / "_staging" / "Otoasobi"
OUTPUT = ROOT / "release" / "Otoasobi_Windows.zip"
README_NAME = "README.txt"
ARCHIVE_ROOT = "Otoasobi"
EXE_NAME = "Otoasobi.exe"
GUIDE_NAME = "Otoasobi_User_Guide.pdf"


def archive_name(path: Path) -> str:
    return (Path(ARCHIVE_ROOT) / path.relative_to(STAGING)).as_posix()


def is_locked_reward_entry(name: str) -> bool:
    normalized = name.replace("\\", "/").casefold()
    return normalized.startswith(f"{ARCHIVE_ROOT.casefold()}/rewards/locked/")


def create_zip() -> None:
    if not (STAGING / EXE_NAME).is_file():
        raise SystemExit(f"Staging package was not found: {STAGING}")
    temporary = OUTPUT.with_suffix(".zip.tmp")
    temporary.unlink(missing_ok=True)
    with zipfile.ZipFile(
        temporary,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
        allowZip64=True,
    ) as archive:
        for path in sorted(STAGING.rglob("*"), key=lambda item: item.as_posix().casefold()):
            if path.is_file() or path.is_dir():
                # Explicit entries preserve empty reward folders on extraction.
                name = archive_name(path) + ("/" if path.is_dir() else "")
                archive.write(path, name)
                if is_locked_reward_entry(name):
                    archive.getinfo(name).external_attr |= 0x02
    shutil.move(temporary, OUTPUT)


def verify_unicode_filenames() -> None:
    with zipfile.ZipFile(OUTPUT) as archive:
        entries = {item.filename: item for item in archive.infolist()}
    required = [
        f"{ARCHIVE_ROOT}/{EXE_NAME}",
        f"{ARCHIVE_ROOT}/{README_NAME}",
        f"{ARCHIVE_ROOT}/{GUIDE_NAME}",
        f"{ARCHIVE_ROOT}/demo_songs/demo_manifest.json",
        f"{ARCHIVE_ROOT}/rewards/reward_config.json",
    ]
    for name in required:
        if name not in entries:
            raise RuntimeError(f"Missing required ZIP entry: {name}")
    reward_images = [
        name
        for name in entries
        if name.startswith(f"{ARCHIVE_ROOT}/rewards/") and Path(name).suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    ]
    if not reward_images:
        raise RuntimeError("No reward image was found in the ZIP.")

    japanese_entries = [item for item in entries.values() if any(ord(char) > 127 for char in item.filename)]
    if not japanese_entries:
        raise RuntimeError("No Japanese filename was found in the ZIP.")
    missing_utf8 = [item.filename for item in japanese_entries if not (item.flag_bits & 0x800)]
    if missing_utf8:
        raise RuntimeError(f"UTF-8 filename flag is missing: {missing_utf8}")

    print(f"ZIP created: {OUTPUT}")
    print(f"files={len(entries)} japanese_entries={len(japanese_entries)}")
    for item in japanese_entries:
        print(f"UTF8 OK: {item.filename}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--trial", action="store_true", help="Build the legacy trial package")
    if parser.parse_args().trial:
        STAGING = ROOT / "release" / "_staging" / "AutoBeat5"
        OUTPUT = ROOT / "release" / "AutoBeat5_Trial_Windows.zip"
        ARCHIVE_ROOT = "AutoBeat5"
        EXE_NAME = "AutoBeat5.exe"
        GUIDE_NAME = "AutoBeat5_User_Guide.pdf"
        README_NAME = "TRIAL_README.txt"
    create_zip()
    verify_unicode_filenames()

