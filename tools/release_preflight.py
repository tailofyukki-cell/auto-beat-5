"""Release gate for the AutoBeat 5 Windows sales package."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ZIP = ROOT / "release" / "AutoBeat5_Trial_Windows.zip"
REQUIRED_ENTRIES = (
    "AutoBeat5/AutoBeat5.exe",
    "AutoBeat5/TRIAL_README.txt",
    "AutoBeat5/RC1_TEST_CHECKLIST.md",
    "AutoBeat5/RELEASE_CHANNEL.txt",
    "AutoBeat5/demo_songs/demo_manifest.json",
    "AutoBeat5/rewards/reward_config.json",
    "AutoBeat5/licenses/INDEX.md",
    "AutoBeat5/licenses/SBOM.json",
    "AutoBeat5/licenses/NotoSansCJK-OFL-1.1.txt",
    "AutoBeat5/licenses/third_party/libsndfile/COPYING",
    "AutoBeat5/licenses/third_party/pygame/LGPL-2.1.txt",
)
FORBIDDEN_COMPONENTS = (
    "openai",
    "torch",
    "torchvision",
    "transformers",
    "tiktoken",
    "huggingface_hub",
    "onnxruntime",
    "cv2",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def assert_demo_bundle_is_allowlisted(app_dir: Path) -> None:
    """Reject personal music or local-player state from a sales release."""
    for forbidden_name in ("profile.json", "settings.json", "library.json", "recent_songs.json", "cache", "charts"):
        if (app_dir / forbidden_name).exists():
            raise RuntimeError(f"Personal player data is present in release root: {forbidden_name}")

    marker = app_dir / "RELEASE_CHANNEL.txt"
    if marker.read_text(encoding="utf-8").strip() != "AutoBeat5_Release_RC1":
        raise RuntimeError("Release data namespace marker is missing or invalid")

    demo_root = app_dir / "demo_songs"
    try:
        manifest = json.loads((demo_root / "demo_manifest.json").read_text(encoding="utf-8"))
        songs = manifest["songs"]
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("Release demo manifest is missing or invalid") from exc
    if not isinstance(songs, list) or not songs:
        raise RuntimeError("Release demo manifest has no songs")

    allowed_audio: set[str] = set()
    allowed_hashes: set[str] = set()
    for song in songs:
        if not isinstance(song, dict):
            raise RuntimeError("Release demo manifest contains an invalid song entry")
        filename = song.get("file")
        digest = song.get("music_hash")
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise RuntimeError("Release demo manifest contains an unsafe audio filename")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise RuntimeError("Release demo manifest contains an invalid music hash")
        if not (demo_root / filename).is_file():
            raise RuntimeError(f"Manifest-authorized demo audio is missing: {filename}")
        allowed_audio.add(filename)
        allowed_hashes.add(digest)

    allowed_files = {"demo_manifest.json", "README.txt", *allowed_audio}
    for path in demo_root.iterdir():
        if path.is_file() and path.name not in allowed_files:
            raise RuntimeError(f"Unapproved file in demo bundle: {path.name}")
        if path.is_dir() and path.name not in {"cache", "charts"}:
            raise RuntimeError(f"Unapproved directory in demo bundle: {path.name}")

    cache_root = demo_root / "cache"
    chart_root = demo_root / "charts"
    actual_cache = {path.stem for path in cache_root.glob("*.json")} if cache_root.is_dir() else set()
    actual_charts = {path.name for path in chart_root.iterdir() if path.is_dir()} if chart_root.is_dir() else set()
    if actual_cache != allowed_hashes:
        raise RuntimeError("Release demo cache hashes do not exactly match the manifest")
    if actual_charts != allowed_hashes:
        raise RuntimeError("Release demo chart hashes do not exactly match the manifest")


def assert_zip_contents(archive_path: Path) -> int:
    with zipfile.ZipFile(archive_path) as archive:
        entries = {item.filename: item for item in archive.infolist()}
    missing = [name for name in REQUIRED_ENTRIES if name not in entries]
    if missing:
        raise RuntimeError(f"Missing required release entries: {missing}")

    japanese_entries = [item for item in entries.values() if any(ord(char) > 127 for char in item.filename)]
    if not japanese_entries:
        raise RuntimeError("No Japanese filename was found in the release ZIP.")
    bad_flags = [item.filename for item in japanese_entries if not (item.flag_bits & 0x800)]
    if bad_flags:
        raise RuntimeError(f"UTF-8 filename flag is missing: {bad_flags}")

    # SciPy and scikit-learn contain lightweight array-API compatibility modules
    # named ``torch``. Treat only a top-level package or dist-info directory as
    # a leaked PyTorch dependency; nested compatibility sources are not torch.
    lowered_paths = [name.casefold() for name in entries]
    leaked = []
    for component in FORBIDDEN_COMPONENTS:
        package_prefix = f"autobeat5/_internal/{component.casefold()}/"
        dist_prefix = f"autobeat5/_internal/{component.casefold()}-"
        if any(name.startswith(package_prefix) or name.startswith(dist_prefix) for name in lowered_paths):
            leaked.append(component)
    if leaked:
        raise RuntimeError(f"Forbidden development components leaked into release: {leaked}")
    return len(japanese_entries)


def expand_with_windows(archive_path: Path, output_dir: Path) -> Path:
    expanded_root = output_dir / "expanded"
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        f"Expand-Archive -LiteralPath '{archive_path}' -DestinationPath '{expanded_root}' -Force",
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    app_dir = expanded_root / "AutoBeat5"
    if not (app_dir / "AutoBeat5.exe").is_file():
        raise RuntimeError("Windows extraction did not create AutoBeat5.exe.")
    japanese_files = [path for path in app_dir.rglob("*") if path.is_file() and any(ord(char) > 127 for char in path.name)]
    if not japanese_files:
        raise RuntimeError("Windows extraction did not preserve any Japanese filename.")
    return app_dir


def smoke_test_exe(app_dir: Path, work_dir: Path) -> None:
    environment = os.environ.copy()
    environment["SDL_VIDEODRIVER"] = "dummy"
    environment["SDL_AUDIODRIVER"] = "dummy"
    # Do not bypass AppPaths with AUTOBEAT_DATA_DIR here. A sales build must
    # prove that it uses its own release channel rather than a developer's
    # existing AutoBeat5 profile.
    environment.pop("AUTOBEAT_DATA_DIR", None)
    appdata_root = work_dir / "appdata"
    environment["APPDATA"] = str(appdata_root)
    process = subprocess.Popen(
        [str(app_dir / "AutoBeat5.exe")],
        cwd=app_dir,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(4)
    exit_code = process.poll()
    if exit_code is not None:
        raise RuntimeError(f"AutoBeat5.exe exited during smoke test: {exit_code}")
    release_namespace = appdata_root / "AutoBeat5_Release_RC1"
    if not release_namespace.is_dir():
        raise RuntimeError("Sales release did not create its isolated AppData namespace")
    if (appdata_root / "AutoBeat5").exists():
        raise RuntimeError("Sales release accessed the development AppData namespace")
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", type=Path, default=DEFAULT_ZIP)
    parser.add_argument("--skip-smoke", action="store_true")
    arguments = parser.parse_args()
    archive_path = arguments.zip.resolve()
    if not archive_path.is_file():
        raise SystemExit(f"Release ZIP was not found: {archive_path}")

    print("STEP 1/3: validating ZIP entries and UTF-8 filename flags", flush=True)
    japanese_count = assert_zip_contents(archive_path)
    with tempfile.TemporaryDirectory(prefix="autobeat5_release_preflight_") as temporary:
        work_dir = Path(temporary)
        print("STEP 2/3: expanding with Windows Expand-Archive", flush=True)
        app_dir = expand_with_windows(archive_path, work_dir)
        assert_demo_bundle_is_allowlisted(app_dir)
        if not arguments.skip_smoke:
            print("STEP 3/3: smoke-testing AutoBeat5.exe", flush=True)
            smoke_test_exe(app_dir, work_dir)

    print(f"RELEASE PREFLIGHT PASSED: {archive_path}")
    print(f"sha256={sha256(archive_path)}")
    print(f"japanese_entries={japanese_count}")


if __name__ == "__main__":
    main()
