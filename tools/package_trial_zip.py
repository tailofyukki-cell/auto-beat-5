"""Windows Explorerでも日本語ファイル名を保持する体験版ZIPを作成する。"""
from __future__ import annotations

import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "release" / "_staging" / "AutoBeat5"
OUTPUT = ROOT / "release" / "AutoBeat5_Trial_Windows.zip"


def archive_name(path: Path) -> str:
    return (Path("AutoBeat5") / path.relative_to(STAGING)).as_posix()


def create_zip() -> None:
    if not (STAGING / "AutoBeat5.exe").is_file():
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
            if path.is_file():
                archive.write(path, archive_name(path))
    shutil.move(temporary, OUTPUT)


def verify_unicode_filenames() -> None:
    with zipfile.ZipFile(OUTPUT) as archive:
        entries = {item.filename: item for item in archive.infolist()}
    required = [
        "AutoBeat5/AutoBeat5.exe",
        "AutoBeat5/TRIAL_README.txt",
        "AutoBeat5/demo_songs/demo_manifest.json",
        "AutoBeat5/rewards/musical_trophy.png",
    ]
    for name in required:
        if name not in entries:
            raise RuntimeError(f"Missing required ZIP entry: {name}")

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
    create_zip()
    verify_unicode_filenames()
