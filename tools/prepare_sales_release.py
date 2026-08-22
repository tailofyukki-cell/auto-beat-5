"""Prepare the AutoBeat 5 sales-release staging directory.

Run this with the release virtual environment after PyInstaller has created a
clean onedir distribution. It copies only user-facing assets, bundles the
third-party license texts available in that release environment, and writes an
SBOM for the actual staged files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIST = ROOT / "build_release" / "AutoBeat5"
DEFAULT_STAGE = ROOT / "release" / "_staging" / "AutoBeat5"
RUNTIME_DISTRIBUTIONS = (
    "pygame",
    "librosa",
    "soundfile",
    "numpy",
    "scipy",
    "scikit-learn",
    "numba",
    "llvmlite",
    "soxr",
    "PyInstaller",
)
LICENSE_NAME_RE = re.compile(r"(?:^|[._-])(license|copying|notice|copyright|authors)(?:$|[._-])", re.I)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_component_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name)


def copy_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def stage_demo_bundle(destination: Path) -> None:
    """Copy only manifest-authorized demo audio and its matching generated data.

    The source folder is a creator workspace and can contain temporary or
    personal files. The sales staging folder must instead be built from a strict
    allow list: the manifest's audio filenames and their 64-character hashes.
    """
    source = ROOT / "demo_songs"
    manifest_path = source / "demo_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        songs = manifest["songs"]
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Invalid demo manifest: {manifest_path}") from exc
    if not isinstance(songs, list) or not songs:
        raise RuntimeError("Demo manifest must contain at least one song")

    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(manifest_path, destination / manifest_path.name)
    readme = source / "README.txt"
    if readme.is_file():
        shutil.copy2(readme, destination / readme.name)

    allowed_hashes: set[str] = set()
    for song in songs:
        if not isinstance(song, dict):
            raise RuntimeError("Demo manifest contains a non-object song entry")
        filename = song.get("file")
        digest = song.get("music_hash")
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise RuntimeError(f"Demo manifest contains an invalid audio filename: {filename!r}")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise RuntimeError(f"Demo manifest contains an invalid music hash for {filename!r}")
        audio = source / filename
        if not audio.is_file():
            raise RuntimeError(f"Manifest-authorized demo audio is missing: {audio}")
        shutil.copy2(audio, destination / filename)
        allowed_hashes.add(digest)

    for digest in sorted(allowed_hashes):
        cache = source / "cache" / f"{digest}.json"
        charts = source / "charts" / digest
        if not cache.is_file() or not charts.is_dir():
            raise RuntimeError(f"Demo cache or charts are missing for manifest hash: {digest}")
        target_cache = destination / "cache"
        target_cache.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cache, target_cache / cache.name)
        copy_tree(charts, destination / "charts" / digest)


def stage_release_marker(stage_dir: Path) -> None:
    # This marker isolates a shipped release from the developer's AppData profile.
    (stage_dir / "RELEASE_CHANNEL.txt").write_text("AutoBeat5_Release_RC1\n", encoding="ascii")


def license_candidates(distribution: metadata.Distribution) -> Iterable[Path]:
    seen: set[Path] = set()
    for entry in distribution.files or []:
        text = entry.as_posix()
        lower = text.lower()
        filename = Path(text).name
        if not (
            LICENSE_NAME_RE.search(filename)
            or "/licenses/" in lower
            or lower.endswith("/copying.txt")
        ):
            continue
        candidate = Path(distribution.locate_file(entry))
        if candidate.is_file() and candidate not in seen:
            seen.add(candidate)
            yield candidate


def copy_distribution_licenses(license_root: Path) -> list[dict[str, object]]:
    component_root = license_root / "third_party"
    component_root.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []

    for requested_name in RUNTIME_DISTRIBUTIONS:
        try:
            distribution = metadata.distribution(requested_name)
        except metadata.PackageNotFoundError as exc:
            raise RuntimeError(f"Release dependency is missing: {requested_name}") from exc
        component_name = distribution.metadata["Name"]
        component_dir = component_root / safe_component_name(component_name)
        component_dir.mkdir(parents=True, exist_ok=True)
        copied: list[str] = []
        for candidate in license_candidates(distribution):
            relative_name = candidate.name
            target = component_dir / relative_name
            suffix = 2
            while target.exists() and target.read_bytes() != candidate.read_bytes():
                target = component_dir / f"{candidate.stem}_{suffix}{candidate.suffix}"
                suffix += 1
            if not target.exists():
                shutil.copy2(candidate, target)
            copied.append(target.relative_to(license_root).as_posix())

        # Some wheels keep their complete license only in package metadata.
        # Preserve that text instead of leaving a sales-release component without
        # a readable license document.
        metadata_license = distribution.metadata.get("License") or ""
        if not copied and len(metadata_license.strip()) > 80:
            target = component_dir / "LICENSE-METADATA.txt"
            target.write_text(metadata_license.strip() + "\n", encoding="utf-8")
            copied.append(target.relative_to(license_root).as_posix())

        # pygame documents the LGPL and licenses of its bundled SDL ecosystem
        # under its package docs rather than in wheel dist-info metadata.
        if component_name.casefold() == "pygame":
            package_root = Path(distribution.locate_file("pygame"))
            source_docs = package_root / "docs"
            pygame_license_dir = component_dir / "pygame_docs"
            for source in (source_docs / "LGPL.txt", source_docs / "licenses"):
                if source.is_file():
                    pygame_license_dir.mkdir(parents=True, exist_ok=True)
                    target = pygame_license_dir / source.name
                    shutil.copy2(source, target)
                    copied.append(target.relative_to(license_root).as_posix())
                elif source.is_dir():
                    copy_tree(source, pygame_license_dir / source.name)
                    copied.extend(
                        item.relative_to(license_root).as_posix()
                        for item in (pygame_license_dir / source.name).rglob("*")
                        if item.is_file()
                    )
            if not any(path.endswith("LGPL.txt") or path.endswith("LGPL-2.1.txt") for path in copied):
                fixed_license = ROOT / "licenses" / "Pygame-LGPL-2.1.txt"
                if not fixed_license.is_file():
                    raise RuntimeError(f"Pinned Pygame LGPL text is missing: {fixed_license}")
                target = component_dir / "LGPL-2.1.txt"
                shutil.copy2(fixed_license, target)
                copied.append(target.relative_to(license_root).as_posix())
        records.append(
            {
                "name": component_name,
                "version": distribution.version,
                "license_expression": distribution.metadata.get("License-Expression"),
                "license_field": distribution.metadata.get("License"),
                "project_url": distribution.metadata.get("Home-page") or distribution.metadata.get("Project-URL"),
                "license_files": sorted(set(copied)),
            }
        )

    # libsndfile is the native SoundFile dependency. Its COPYING is packed with
    # the wheel data rather than a standard Python dist-info license location.
    soundfile_data = Path(sys.prefix) / "Lib" / "site-packages" / "_soundfile_data" / "COPYING"
    if not soundfile_data.is_file():
        raise RuntimeError(f"libsndfile COPYING was not found: {soundfile_data}")
    libsndfile_dir = component_root / "libsndfile"
    libsndfile_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(soundfile_data, libsndfile_dir / "COPYING")
    records.append(
        {
            "name": "libsndfile",
            "version": "bundled by SoundFile wheel",
            "license_expression": "LGPL (see COPYING)",
            "license_field": None,
            "project_url": "https://libsndfile.github.io/libsndfile/",
            "license_files": ["third_party/libsndfile/COPYING"],
        }
    )

    # Python and Tcl/Tk are runtime components copied by PyInstaller on Windows.
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.is_file():
        python_dir = component_root / "Python"
        python_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(python_license, python_dir / "LICENSE.txt")
        records.append(
            {
                "name": "Python",
                "version": sys.version.split()[0],
                "license_expression": "PSF-2.0",
                "license_field": None,
                "project_url": "https://www.python.org/psf/license/",
                "license_files": ["third_party/Python/LICENSE.txt"],
            }
        )

    return records


def write_license_index(license_root: Path, records: list[dict[str, object]]) -> None:
    lines = [
        "# AutoBeat 5 Third-Party Licenses",
        "",
        "This folder contains license texts and notices for components bundled in this release.",
        "The game code and the included author-created demo songs and reward images are not licensed by this index.",
        "",
        "| Component | Version | License metadata | License files |",
        "|---|---:|---|---|",
    ]
    for record in records:
        raw_license = record.get("license_expression") or record.get("license_field") or "See included files"
        license_name = str(raw_license).splitlines()[0].strip()
        if len(license_name) > 100:
            license_name = license_name[:97] + "..."
        files = "<br>".join(record["license_files"]) if record["license_files"] else "No local text found — review before sale"
        lines.append(f"| {record['name']} | {record['version']} | {license_name} | {files} |")
    lines.extend(
        [
            "",
            "The Noto Sans CJK font license is provided in `NotoSansCJK-OFL-1.1.txt`.",
            "For component source and project URLs, see `SBOM.json`.",
        ]
    )
    (license_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def stage_assets(dist_dir: Path, stage_dir: Path) -> None:
    if not (dist_dir / "AutoBeat5.exe").is_file():
        raise RuntimeError(f"PyInstaller distribution is missing AutoBeat5.exe: {dist_dir}")
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    stage_dir.parent.mkdir(parents=True, exist_ok=True)
    copy_tree(dist_dir, stage_dir)

    stage_demo_bundle(stage_dir / "demo_songs")
    for folder in ("rewards", "licenses"):
        source = ROOT / folder
        if not source.is_dir():
            raise RuntimeError(f"Required release asset folder is missing: {source}")
        copy_tree(source, stage_dir / folder)
    stage_release_marker(stage_dir)

    readme = ROOT / "TRIAL_README.txt"
    if not readme.is_file():
        raise RuntimeError(f"Release README is missing: {readme}")
    shutil.copy2(readme, stage_dir / readme.name)

    checklist = ROOT / "docs" / "sales_release_rc1_test_checklist.md"
    if not checklist.is_file():
        raise RuntimeError(f"Release test checklist is missing: {checklist}")
    shutil.copy2(checklist, stage_dir / "RC1_TEST_CHECKLIST.md")


def write_sbom(stage_dir: Path, records: list[dict[str, object]]) -> None:
    native_files = []
    for path in sorted(stage_dir.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if path.is_file() and path.suffix.lower() in {".dll", ".pyd", ".exe"}:
            native_files.append(
                {
                    "path": path.relative_to(stage_dir).as_posix(),
                    "sha256": sha256(path),
                    "size": path.stat().st_size,
                }
            )
    sbom = {
        "format": "AutoBeat5-sales-SBOM-v1",
        "generated_utc": datetime.now(UTC).isoformat(),
        "python": sys.version,
        "components": records,
        "native_files": native_files,
    }
    (stage_dir / "licenses" / "SBOM.json").write_text(json.dumps(sbom, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist-dir", type=Path, default=DEFAULT_DIST)
    parser.add_argument("--stage-dir", type=Path, default=DEFAULT_STAGE)
    arguments = parser.parse_args()

    dist_dir = arguments.dist_dir.resolve()
    stage_dir = arguments.stage_dir.resolve()
    stage_assets(dist_dir, stage_dir)
    records = copy_distribution_licenses(stage_dir / "licenses")
    write_license_index(stage_dir / "licenses", records)
    write_sbom(stage_dir, records)
    print(stage_dir)


if __name__ == "__main__":
    main()
