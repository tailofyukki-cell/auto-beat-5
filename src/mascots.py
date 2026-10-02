"""ゲーム中のマスコット資産を、安全かつ拡張可能に読み込む。"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path


SUPPORTED_MASCOT_IMAGES = {".png", ".webp"}
_MASCOT_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


@dataclass(frozen=True, slots=True)
class Mascot:
    """一体分の配布同梱マスコット定義。"""

    mascot_id: str
    name: str
    image_path: Path
    scale: float = 1.0
    anchor: str = "right"


def load_mascot_catalog(directory: Path) -> tuple[Mascot, ...]:
    """manifest.jsonを優先し、未記載の画像も候補として読み込む。

    壊れた定義や存在しない画像は無視する。ゲーム本体はマスコットなしでも起動可能。
    PNG / WebPを同じフォルダへ追加するだけでも設定画面の候補に出る。
    """
    manifest_path = directory / "manifest.json"
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        entries = raw.get("mascots", [])
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        entries = []
    if not isinstance(entries, list):
        entries = []

    catalog: list[Mascot] = []
    seen_ids: set[str] = set()
    for raw_entry in entries:
        if not isinstance(raw_entry, dict):
            continue
        mascot_id = str(raw_entry.get("id", "")).casefold()
        filename = str(raw_entry.get("file", ""))
        if not _MASCOT_ID.fullmatch(mascot_id) or mascot_id in seen_ids:
            continue
        if Path(filename).name != filename:
            continue
        image_path = directory / filename
        if image_path.suffix.casefold() not in SUPPORTED_MASCOT_IMAGES or not image_path.is_file():
            continue
        try:
            scale = max(0.50, min(1.50, float(raw_entry.get("scale", 1.0))))
        except (TypeError, ValueError):
            scale = 1.0
        anchor = str(raw_entry.get("anchor", "right")).casefold()
        if anchor not in {"left", "right"}:
            anchor = "right"
        name = str(raw_entry.get("name", mascot_id.upper())).strip() or mascot_id.upper()
        catalog.append(Mascot(mascot_id, name, image_path, scale, anchor))
        seen_ids.add(mascot_id)
    try:
        image_paths = sorted(directory.iterdir(), key=lambda path: path.name.casefold())
    except OSError:
        return tuple(catalog)

    for image_path in image_paths:
        if image_path.suffix.casefold() not in SUPPORTED_MASCOT_IMAGES or not image_path.is_file():
            continue
        mascot_id = image_path.stem.casefold()
        mascot_id = re.sub(r"[^a-z0-9_-]+", "-", mascot_id).strip("-_")
        if not _MASCOT_ID.fullmatch(mascot_id):
            digest = hashlib.sha1(image_path.name.encode("utf-8")).hexdigest()[:8]
            mascot_id = f"mascot-{digest}"
        if mascot_id in seen_ids:
            continue
        name = image_path.stem.replace("_", " ").replace("-", " ").strip().upper() or mascot_id.upper()
        catalog.append(Mascot(mascot_id, name, image_path))
        seen_ids.add(mascot_id)
    return tuple(catalog)


def find_mascot(catalog: tuple[Mascot, ...], mascot_id: object) -> Mascot | None:
    """設定のIDに対応するマスコットを返す。"""
    requested = str(mascot_id).casefold()
    return next((mascot for mascot in catalog if mascot.mascot_id == requested), None)
