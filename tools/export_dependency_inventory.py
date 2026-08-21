"""AutoBeat 5の販売前ライセンス監査用に依存関係のメタデータをJSON出力する。"""
from __future__ import annotations

import json
import re
from collections import deque
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "dependency_inventory.json"
ROOT_DISTRIBUTIONS = {
    "pygame",
    "librosa",
    "soundfile",
    "numpy",
    "scipy",
    "scikit-learn",
    "numba",
    "llvmlite",
    "pyinstaller",
}


def normalize_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def requirement_name(requirement: str) -> str | None:
    match = re.match(r"^\s*([A-Za-z0-9_.-]+)", requirement)
    return normalize_name(match.group(1)) if match else None


def metadata_value(data: metadata.Metadata, key: str) -> str | None:
    value = data.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def main() -> None:
    queue = deque(sorted(ROOT_DISTRIBUTIONS))
    visited: set[str] = set()
    items: list[dict[str, object]] = []

    while queue:
        name = queue.popleft()
        if name in visited:
            continue
        visited.add(name)
        try:
            distribution = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            items.append({"name": name, "installed": False})
            continue

        data = distribution.metadata
        requires = distribution.requires or []
        dependencies = sorted({dependency for value in requires if (dependency := requirement_name(value))})
        for dependency in dependencies:
            if dependency not in visited:
                queue.append(dependency)

        classifiers = data.get_all("Classifier") or []
        license_classifiers = [item for item in classifiers if item.startswith("License ::")]
        items.append(
            {
                "name": distribution.metadata["Name"],
                "version": distribution.version,
                "installed": True,
                "license_expression": metadata_value(data, "License-Expression"),
                "license_field": metadata_value(data, "License"),
                "license_classifiers": license_classifiers,
                "homepage": metadata_value(data, "Home-page") or metadata_value(data, "Project-URL"),
                "dependencies": dependencies,
            }
        )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps({"root_distributions": sorted(ROOT_DISTRIBUTIONS), "items": items}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
