"""AutoBeat 5 のローカル永続化。破損ファイルは退避して既定値へ戻す。"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from models import AnalysisResult, Chart, DEFAULT_KEYS, LANE_KEY_PRESETS, chart_lane_count, normalize_lane_count

APP_NAME = "AutoBeat5"
RELEASE_APP_NAME = "AutoBeat5_Release_RC1"
RELEASE_CHANNEL_MARKER = "RELEASE_CHANNEL.txt"
REWARD_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
INITIAL_MASCOT_ID = "rhythm"
INITIAL_UNLOCKED_FEATURES = ("lane.5",)
INITIAL_UNLOCKED_COSMETICS = (
    f"mascot.{INITIAL_MASCOT_ID}",
    "sfx.classic",
    "background.visualizer",
    "note_theme.standard",
    "note_skin.standard",
)
MASCOT_SCORE_STEP = 100000
LOW_RANKS = {"C", "D", "E", "F"}
A_OR_BETTER_RANKS = {"S+", "S", "A"}
S_OR_BETTER_RANKS = {"S+", "S"}
_HIDDEN_LOCKED_REWARD_PATHS: set[Path] = set()


def data_namespace() -> str:
    """Return an isolated AppData namespace for a packaged release channel.

    Development builds use ``AutoBeat5``. Frozen builds default to the existing
    release namespace; legacy marker files remain supported for older installs.
    """
    if not getattr(sys, "frozen", False):
        return APP_NAME
    marker = Path(sys.executable).resolve().parent / RELEASE_CHANNEL_MARKER
    try:
        channel = marker.read_text(encoding="utf-8").strip()
    except OSError:
        # Keep existing shipped saves without requiring a loose marker file.
        return RELEASE_APP_NAME
    safe_channel = "".join(character for character in channel if character.isascii() and (character.isalnum() or character in "_-"))
    return safe_channel or APP_NAME


@dataclass(frozen=True, slots=True)
class AppPaths:
    root: Path
    settings: Path
    profile: Path
    cache: Path
    charts: Path
    rewards: Path
    demo_songs: Path | None = None

    @classmethod
    def discover(cls) -> "AppPaths":
        if os.environ.get("AUTOBEAT_DATA_DIR"):
            root = Path(os.environ["AUTOBEAT_DATA_DIR"]).expanduser()
        elif os.name == "nt" and os.environ.get("APPDATA"):
            root = Path(os.environ["APPDATA"]) / data_namespace()
        else:
            root = Path.home() / f".{data_namespace().lower()}"
        # 配布版ではexe隣接の素材フォルダを優先する。開発時のご褒美画像は従来どおりアプリデータ配下に置く。
        if getattr(sys, "frozen", False):
            bundled_root = Path(sys.executable).resolve().parent
            default_rewards = bundled_root / "rewards"
            default_demo_songs = bundled_root / "demo_songs"
        else:
            default_rewards = root / "rewards"
            default_demo_songs = Path(__file__).resolve().parents[1] / "demo_songs"
        rewards = Path(os.environ.get("AUTOBEAT_REWARDS_DIR", default_rewards)).expanduser()
        demo_songs = Path(os.environ.get("AUTOBEAT_DEMO_SONGS_DIR", default_demo_songs)).expanduser()
        return cls(
            root=root,
            settings=root / "settings.json",
            profile=root / "profile.json",
            cache=root / "cache",
            charts=root / "charts",
            rewards=rewards,
            demo_songs=demo_songs,
        )

    def ensure(self) -> None:
        directories = (self.root, self.cache, self.charts, self.rewards)
        if self.demo_songs is not None:
            directories = (*directories, self.demo_songs)
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
        ensure_reward_storage(self)


DEFAULT_SETTINGS: dict[str, Any] = {
    "graphics_quality": "standard",
    "keys": list(DEFAULT_KEYS),
    "lane_count": 5,
    "lane_keys": {str(count): list(keys) for count, keys in LANE_KEY_PRESETS.items()},
    "music_volume": 0.8,
    "sfx_volume": 0.7,
    "sfx_theme": "classic",
    "note_speed": 625.0,
    "playfield_mode": "standard",
    "background_mode": "visualizer",
    "background_image": "",
    "background_opacity": 0.28,
    "note_theme": "standard",
    "note_skin": "standard",
    "mascot_mode": "standard",
    "mascot_id": INITIAL_MASCOT_ID,
    "timing_offset_ms": 0,
    "fullscreen": False,
    "resolution": [1280, 720],
    "judgment_windows_ms": {"perfect": 45, "great": 90, "good": 140},
}

DEFAULT_PROFILE: dict[str, Any] = {
    "lifetime_score": 0,
    "wallet_score": 0,
    "wallet_initialized": False,
    "shop_migrated": False,
    "purchase_history": [],
    "unlocked_rewards": [],
    "unlocked_features": list(INITIAL_UNLOCKED_FEATURES),
    "unlocked_cosmetics": list(INITIAL_UNLOCKED_COSMETICS),
    "unlock_stats": {
        "five_lane_low_rank_count": 0,
        "five_lane_high_miss_count": 0,
        "five_lane_a_or_better_count": 0,
        "five_lane_s_or_better_count": 0,
    },
    "high_scores": {},
    "rankings": {},
    "last_play_ranking": {},
    "last_play_badges": [],
    "badges": [],
    "play_history": [],
    "recent_songs": [],
    "library_folders": ["ホーム"],
    "active_library_folder": "ホーム",
    "tutorial_completed": False,
}


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def music_hash(path: str | Path) -> str:
    """大きな音源でもメモリを圧迫しないようストリームでSHA-256を求める。"""
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def reward_locked_dir(paths: AppPaths) -> Path:
    return paths.rewards / "locked"


def reward_unlocked_dir(paths: AppPaths) -> Path:
    return paths.rewards / "unlocked"


def set_locked_rewards_hidden(paths: AppPaths) -> None:
    locked = reward_locked_dir(paths)
    if os.name != "nt" or not locked.exists():
        return
    try:
        resolved = locked.resolve()
    except OSError:
        resolved = locked
    if resolved in _HIDDEN_LOCKED_REWARD_PATHS:
        return
    startupinfo = None
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if hasattr(subprocess, "STARTUPINFO"):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
        startupinfo.wShowWindow = 0
    try:
        subprocess.run(
            ["attrib", "+h", str(locked)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )
        _HIDDEN_LOCKED_REWARD_PATHS.add(resolved)
    except OSError:
        pass


def ensure_reward_storage(paths: AppPaths) -> None:
    paths.rewards.mkdir(parents=True, exist_ok=True)
    reward_locked_dir(paths).mkdir(parents=True, exist_ok=True)
    reward_unlocked_dir(paths).mkdir(parents=True, exist_ok=True)
    set_locked_rewards_hidden(paths)


def reward_image_paths(paths: AppPaths) -> dict[str, Path]:
    ensure_reward_storage(paths)
    images: dict[str, Path] = {}
    for folder in (paths.rewards, reward_locked_dir(paths), reward_unlocked_dir(paths)):
        try:
            files = [file for file in folder.iterdir() if file.is_file() and file.suffix.lower() in REWARD_IMAGE_EXTENSIONS]
        except OSError:
            continue
        for file in sorted(files, key=lambda item: item.name.casefold()):
            images[file.name] = file
    return images


def reward_image_path(paths: AppPaths, name: str) -> Path | None:
    return reward_image_paths(paths).get(Path(name).name)


def materialize_unlocked_rewards(paths: AppPaths, names: set[str] | list[str] | tuple[str, ...]) -> list[Path]:
    ensure_reward_storage(paths)
    images = reward_image_paths(paths)
    copied: list[Path] = []
    target_dir = reward_unlocked_dir(paths)
    for raw_name in names:
        name = Path(str(raw_name)).name
        source = images.get(name)
        if source is None or not source.is_file():
            continue
        target = target_dir / name
        if source.resolve() == target.resolve():
            copied.append(target)
            continue
        try:
            shutil.copy2(source, target)
        except OSError:
            continue
        copied.append(target)
    return copied


def _load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return copy.deepcopy(default)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("top level must be object")
        merged = copy.deepcopy(default)
        merged.update(data)
        return merged
    except (OSError, ValueError, json.JSONDecodeError):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = path.with_suffix(path.suffix + f".corrupt_{stamp}")
        try:
            shutil.move(path, backup)
        except OSError:
            pass
        return copy.deepcopy(default)


def _normalize_lane_settings(settings: dict[str, Any]) -> None:
    lane_count = settings.get("lane_count", 5)
    if lane_count not in LANE_KEY_PRESETS:
        lane_count = 5
    settings["lane_count"] = int(lane_count)

    lane_keys = settings.get("lane_keys")
    if not isinstance(lane_keys, dict):
        lane_keys = {}
    normalized: dict[str, list[str]] = {}
    for count, defaults in LANE_KEY_PRESETS.items():
        raw = lane_keys.get(str(count), lane_keys.get(count))
        if count == 5 and (not isinstance(raw, list)):
            raw = settings.get("keys")
        if not isinstance(raw, list) or len(raw) != count or len(set(raw)) != count:
            raw = list(defaults)
        normalized[str(count)] = [str(key).lower() for key in raw]
    settings["lane_keys"] = normalized
    settings["keys"] = list(normalized["5"])



def _normalize_string_list(value: Any, defaults: tuple[str, ...] = ()) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    raw_items = value if isinstance(value, list) else list(defaults)
    for item in raw_items:
        text = str(item).strip()
        if text and text not in seen:
            seen.add(text)
            normalized.append(text)
    for item in defaults:
        if item not in seen:
            normalized.append(item)
            seen.add(item)
    return normalized


def normalize_profile(profile: dict[str, Any]) -> dict[str, Any]:
    profile["unlocked_rewards"] = _normalize_string_list(profile.get("unlocked_rewards", []))
    profile["unlocked_features"] = _normalize_string_list(profile.get("unlocked_features", []), INITIAL_UNLOCKED_FEATURES)
    profile["unlocked_cosmetics"] = _normalize_string_list(profile.get("unlocked_cosmetics", []), INITIAL_UNLOCKED_COSMETICS)
    stats = profile.get("unlock_stats")
    if not isinstance(stats, dict):
        stats = {}
    defaults = DEFAULT_PROFILE["unlock_stats"]
    profile["unlock_stats"] = {key: max(0, int(stats.get(key, default))) for key, default in defaults.items()}
    for key in ("high_scores", "rankings", "last_play_ranking"):
        if not isinstance(profile.get(key), dict):
            profile[key] = {}
    for key in ("last_play_badges", "badges", "play_history", "recent_songs", "purchase_history"):
        if not isinstance(profile.get(key), list):
            profile[key] = []
    if not isinstance(profile.get("library_folders"), list):
        profile["library_folders"] = ["ホーム"]
    normalized_folders = ["ホーム"]
    for item in profile.get("library_folders", []):
        text = str(item or "").strip()
        if text and text not in normalized_folders:
            normalized_folders.append(text)
    for entry in profile.get("recent_songs", []):
        if isinstance(entry, dict):
            folder = str(entry.get("folder") or "ホーム").strip() or "ホーム"
            entry["folder"] = folder
            if folder not in normalized_folders:
                normalized_folders.append(folder)
    profile["library_folders"] = normalized_folders
    if str(profile.get("active_library_folder") or "ホーム") not in normalized_folders:
        profile["active_library_folder"] = "ホーム"
    profile["lifetime_score"] = max(0, int(profile.get("lifetime_score", 0)))
    if not bool(profile.get("wallet_initialized", False)):
        profile["wallet_score"] = profile["lifetime_score"]
        profile["wallet_initialized"] = True
    else:
        profile["wallet_score"] = max(0, int(profile.get("wallet_score", 0)))
    profile["tutorial_completed"] = bool(profile.get("tutorial_completed", False))
    profile["shop_migrated"] = bool(profile.get("shop_migrated", False))
    return profile


def lane_feature_id(lane_count: int) -> str:
    return f"lane.{normalize_lane_count(lane_count)}"


def mascot_cosmetic_id(mascot_id: str) -> str:
    return f"mascot.{str(mascot_id).casefold()}"


def cosmetic_id(category: str, item_id: str) -> str:
    safe_category = str(category).strip().casefold()
    safe_item = str(item_id).strip().casefold()
    return f"{safe_category}.{safe_item}"


def mascot_required_score(mascot_id: str, order_index: int) -> int:
    if str(mascot_id).casefold() == INITIAL_MASCOT_ID:
        return 0
    return max(1, order_index) * MASCOT_SCORE_STEP


def is_feature_unlocked(profile: dict[str, Any], feature_id: str) -> bool:
    normalize_profile(profile)
    return feature_id in set(profile.get("unlocked_features", []))


def is_cosmetic_unlocked(profile: dict[str, Any], item_id: str) -> bool:
    normalize_profile(profile)
    return str(item_id) in set(profile.get("unlocked_cosmetics", []))


def is_mascot_unlocked(profile: dict[str, Any], mascot_id: str, required_score: int | None = None) -> bool:
    normalize_profile(profile)
    return is_cosmetic_unlocked(profile, mascot_cosmetic_id(mascot_id))


def purchase_unlock(paths: AppPaths, profile: dict[str, Any], item_id: str, price: int) -> bool:
    """Spend BEAT POINTS and permanently unlock one cosmetic or reward."""
    normalize_profile(profile)
    normalized_id = str(item_id).strip()
    cost = max(0, int(price))
    if normalized_id.startswith("reward."):
        reward_name = Path(normalized_id.split(".", 1)[1]).name
        unlocked = set(profile.get("unlocked_rewards", []))
        if reward_name in unlocked:
            return False
        target = profile["unlocked_rewards"]
        stored_id = f"reward.{reward_name}"
    else:
        unlocked = set(profile.get("unlocked_cosmetics", []))
        if normalized_id in unlocked:
            return False
        target = profile["unlocked_cosmetics"]
        stored_id = normalized_id
    balance = int(profile.get("wallet_score", 0))
    if balance < cost:
        return False
    profile["wallet_score"] = balance - cost
    target.append(reward_name if normalized_id.startswith("reward.") else normalized_id)
    profile["purchase_history"].append({"item_id": stored_id, "price": cost, "purchased_at": now_iso()})
    if normalized_id.startswith("reward."):
        materialize_unlocked_rewards(paths, [reward_name])
    save_profile(paths, profile)
    return True


def unlock_tutorial_cosmetics(profile: dict[str, Any], item_ids: list[str] | tuple[str, ...] | set[str]) -> list[str]:
    normalize_profile(profile)
    unlocked = set(profile.get("unlocked_cosmetics", []))
    newly: list[str] = []
    for item_id in item_ids:
        text = str(item_id).strip()
        if text and text not in unlocked:
            unlocked.add(text)
            newly.append(text)
    profile["unlocked_cosmetics"] = sorted(unlocked)
    return newly


def _lane_count_from_chart_key(chart_key: str) -> int:
    match = re.search(r":(3|5|7)lane$", str(chart_key))
    return int(match.group(1)) if match else 5


def _miss_rate(result: dict[str, Any]) -> float:
    judgments = result.get("judgments", {})
    if not isinstance(judgments, dict):
        return 0.0
    total = sum(max(0, int(judgments.get(name, 0))) for name in ("PERFECT", "GREAT", "GOOD", "MISS"))
    if total <= 0:
        return 0.0
    return max(0, int(judgments.get("MISS", 0))) / total


def update_performance_unlocks(profile: dict[str, Any], *, chart_key: str, result: dict[str, Any]) -> list[str]:
    normalize_profile(profile)
    if _lane_count_from_chart_key(chart_key) != 5:
        return []
    rank = str(result.get("rank", "D")).upper()
    stats = profile["unlock_stats"]
    if rank in LOW_RANKS:
        stats["five_lane_low_rank_count"] += 1
    if _miss_rate(result) >= 0.25:
        stats["five_lane_high_miss_count"] += 1
    if rank in A_OR_BETTER_RANKS:
        stats["five_lane_a_or_better_count"] += 1
    if rank in S_OR_BETTER_RANKS:
        stats["five_lane_s_or_better_count"] += 1

    unlocked = set(profile.get("unlocked_features", []))
    newly: list[str] = []
    if (stats["five_lane_low_rank_count"] >= 3 or stats["five_lane_high_miss_count"] >= 3) and "lane.3" not in unlocked:
        unlocked.add("lane.3")
        newly.append("lane.3")
    if (stats["five_lane_s_or_better_count"] >= 1 or stats["five_lane_a_or_better_count"] >= 3) and "lane.7" not in unlocked:
        unlocked.add("lane.7")
        newly.append("lane.7")
    profile["unlocked_features"] = sorted(unlocked)
    return newly


def unlock_score_cosmetics(profile: dict[str, Any], items: list[tuple[str, int]]) -> list[str]:
    normalize_profile(profile)
    lifetime_score = int(profile.get("lifetime_score", 0))
    unlocked = set(profile.get("unlocked_cosmetics", []))
    newly: list[str] = []
    for cosmetic_id, required_score in items:
        if lifetime_score >= int(required_score) and cosmetic_id not in unlocked:
            unlocked.add(cosmetic_id)
            newly.append(cosmetic_id)
    profile["unlocked_cosmetics"] = sorted(unlocked)
    return newly

def load_settings(paths: AppPaths) -> dict[str, Any]:
    paths.ensure()
    settings = _load_json(paths.settings, DEFAULT_SETTINGS)
    _normalize_lane_settings(settings)
    return settings


def save_settings(paths: AppPaths, settings: dict[str, Any]) -> None:
    _normalize_lane_settings(settings)
    for count, keys in settings["lane_keys"].items():
        expected = int(count)
        if len(keys) != expected or len(set(keys)) != expected:
            raise ValueError(f"{expected} lane keys must be unique")
    _atomic_write_json(paths.settings, settings)


def load_profile(paths: AppPaths) -> dict[str, Any]:
    paths.ensure()
    return normalize_profile(_load_json(paths.profile, DEFAULT_PROFILE))


def save_profile(paths: AppPaths, profile: dict[str, Any]) -> None:
    normalize_profile(profile)
    profile["play_history"] = profile.get("play_history", [])[-100:]
    _atomic_write_json(paths.profile, profile)


def cache_path(paths: AppPaths, digest: str) -> Path:
    return paths.cache / f"{digest}.json"


def load_analysis(paths: AppPaths, digest: str) -> AnalysisResult | None:
    path = cache_path(paths, digest)
    try:
        if path.exists():
            return AnalysisResult.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        path.unlink(missing_ok=True)
    return None


def save_analysis(paths: AppPaths, analysis: AnalysisResult) -> None:
    _atomic_write_json(cache_path(paths, analysis.music_hash), analysis.to_dict())


def chart_path(paths: AppPaths, digest: str, difficulty: str, lane_count: int = 5) -> Path:
    lane_count = normalize_lane_count(lane_count)
    return paths.charts / digest / f"{lane_count}lane" / f"{difficulty}.json"


def legacy_chart_path(paths: AppPaths, digest: str, difficulty: str) -> Path:
    return paths.charts / digest / f"{difficulty}.json"


def load_chart(paths: AppPaths, digest: str, difficulty: str, lane_count: int = 5) -> Chart | None:
    lane_count = normalize_lane_count(lane_count)
    paths_to_try = [chart_path(paths, digest, difficulty, lane_count)]
    if lane_count == 5:
        paths_to_try.append(legacy_chart_path(paths, digest, difficulty))
    for path in paths_to_try:
        try:
            if path.exists():
                chart = Chart.from_dict(json.loads(path.read_text(encoding="utf-8")))
                chart.metadata.setdefault("lane_count", lane_count)
                chart.metadata.setdefault("lane_mode", f"{lane_count}lane")
                return chart
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            path.unlink(missing_ok=True)
    return None


def save_chart(paths: AppPaths, chart: Chart) -> None:
    lane_count = chart_lane_count(chart)
    chart.metadata["lane_count"] = lane_count
    chart.metadata["lane_mode"] = f"{lane_count}lane"
    _atomic_write_json(chart_path(paths, chart.music_hash, chart.difficulty.value, lane_count), chart.to_dict())


RECENT_SONG_LIMIT = 100
DEFAULT_LIBRARY_FOLDER = "ホーム"


def normalize_library_folder_name(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return DEFAULT_LIBRARY_FOLDER
    return re.sub(r'[\\/:*?"<>|]+', "_", text)[:28] or DEFAULT_LIBRARY_FOLDER


def library_folders(profile: dict[str, Any]) -> list[str]:
    normalize_profile(profile)
    names = [DEFAULT_LIBRARY_FOLDER]
    raw = profile.get("library_folders", [])
    if isinstance(raw, list):
        for item in raw:
            name = normalize_library_folder_name(item)
            if name not in names:
                names.append(name)
    for entry in profile.get("recent_songs", []):
        if isinstance(entry, dict):
            name = normalize_library_folder_name(entry.get("folder"))
            if name not in names:
                names.append(name)
    profile["library_folders"] = names
    if normalize_library_folder_name(profile.get("active_library_folder")) not in names:
        profile["active_library_folder"] = DEFAULT_LIBRARY_FOLDER
    return names


def active_library_folder(profile: dict[str, Any]) -> str:
    folders = library_folders(profile)
    name = normalize_library_folder_name(profile.get("active_library_folder"))
    return name if name in folders else DEFAULT_LIBRARY_FOLDER


def set_active_library_folder(paths: AppPaths, profile: dict[str, Any], folder: str) -> str:
    name = normalize_library_folder_name(folder)
    folders = library_folders(profile)
    if name not in folders:
        folders.append(name)
    profile["library_folders"] = folders
    profile["active_library_folder"] = name
    save_profile(paths, profile)
    return name


def assign_recent_song_folder(paths: AppPaths, profile: dict[str, Any], music_hash: str, source_path: str, folder: str) -> bool:
    name = normalize_library_folder_name(folder)
    folders = library_folders(profile)
    if name not in folders:
        folders.append(name)
    changed = False
    for entry in profile.get("recent_songs", []):
        if not isinstance(entry, dict):
            continue
        if str(entry.get("music_hash", "")) == str(music_hash) or str(entry.get("source_path", "")) == str(source_path):
            entry["folder"] = name
            changed = True
    if changed:
        profile["library_folders"] = folders
        save_profile(paths, profile)
    return changed


def record_recent_song(paths: AppPaths, profile: dict[str, Any], analysis: AnalysisResult, folder: str | None = None) -> None:
    """解析済み楽曲を最大100件のローカルライブラリーとして保持する。音源本体は保存しない。"""
    entry = {
        "music_hash": analysis.music_hash,
        "source_path": analysis.source_path,
        "duration": round(float(analysis.duration), 3),
        "bpm": round(float(analysis.bpm), 3),
        "last_used": now_iso(),
    }
    previous_folder = None
    for item in profile.get("recent_songs", []):
        if isinstance(item, dict) and (item.get("music_hash") == analysis.music_hash or item.get("source_path") == analysis.source_path):
            previous_folder = item.get("folder")
            break
    entry["folder"] = normalize_library_folder_name(folder if folder is not None else previous_folder)
    folders = library_folders(profile)
    if entry["folder"] not in folders:
        folders.append(entry["folder"])
    profile["library_folders"] = folders
    existing = [
        item
        for item in profile.get("recent_songs", [])
        if item.get("music_hash") != analysis.music_hash and item.get("source_path") != analysis.source_path
    ]
    profile["recent_songs"] = [entry, *existing][:RECENT_SONG_LIMIT]
    save_profile(paths, profile)


def ranking_entries(profile: dict[str, Any], chart_key: str, *, limit: int = 10) -> list[dict[str, Any]]:
    """指定曲・難易度のローカル順位表を、安全な表示用データとして返す。"""
    raw_rankings = profile.get("rankings", {})
    if not isinstance(raw_rankings, dict):
        return []
    entries = raw_rankings.get(chart_key, [])
    if (not entries) and isinstance(chart_key, str) and chart_key.endswith(":5lane"):
        entries = raw_rankings.get(chart_key[: -len(":5lane")], [])
    if not isinstance(entries, list):
        return []
    valid = [dict(entry) for entry in entries if isinstance(entry, dict) and "score" in entry]
    return valid[: max(0, int(limit))]


def song_ranking_summary(profile: dict[str, Any], music_hash: str) -> dict[str, dict[str, Any]]:
    """楽曲ハッシュに属する難易度別の自己ベストを返す。別楽曲の記録は混在させない。"""
    raw_rankings = profile.get("rankings", {})
    if not isinstance(raw_rankings, dict):
        return {}
    prefix = f"{music_hash}:"
    summary: dict[str, dict[str, Any]] = {}
    for key, entries in raw_rankings.items():
        if not isinstance(key, str) or not key.startswith(prefix) or not isinstance(entries, list):
            continue
        parts = key[len(prefix) :].split(":")
        if not parts:
            continue
        difficulty = parts[0]
        lane_mode = parts[1] if len(parts) > 1 else "5lane"
        summary_key = f"{difficulty}:{lane_mode}"
        valid = [dict(entry) for entry in entries if isinstance(entry, dict) and "score" in entry]
        if valid:
            summary[summary_key] = valid[0]
            if lane_mode == "5lane":
                summary.setdefault(difficulty, valid[0])
    return summary


def result_badges(result: dict[str, Any], *, previous_best_score: int = 0) -> list[str]:
    """リザルト画面とプロフィールへ残す、短い称号を成績から決める。"""
    judgments = result.get("judgments", {})
    if not isinstance(judgments, dict):
        judgments = {}
    perfect = int(judgments.get("PERFECT", 0))
    great = int(judgments.get("GREAT", 0))
    good = int(judgments.get("GOOD", 0))
    miss = int(judgments.get("MISS", 0))
    total = perfect + great + good + miss
    max_combo = int(result.get("max_combo", 0))
    score = int(result.get("score", 0))
    rank = str(result.get("rank", "D"))

    badges: list[str] = []
    if total > 0 and perfect == total:
        badges.append("神業の演奏")
    if total > 0 and miss == 0:
        badges.append("完璧な集中")
        badges.append("ノーミスクリア")
    if rank in {"S+", "S"}:
        badges.append("ステージ支配者")
    if previous_best_score <= 0:
        badges.append("First Clear")
    elif score > previous_best_score:
        badges.append("Rising Star")
    if max_combo >= 500:
        badges.append("Combo Master")
    elif max_combo >= 100:
        badges.append("Combo Maker")

    unique: list[str] = []
    for badge in badges:
        if badge not in unique:
            unique.append(badge)
    return unique

def record_play(paths: AppPaths, profile: dict[str, Any], *, chart_key: str, result: dict[str, Any]) -> list[str]:
    """プレイ成績・順位・BEAT POINTを保存し、新しく解放されたレーンを返す。"""
    normalize_profile(profile)
    score = max(0, int(result["score"]))
    profile["lifetime_score"] = int(profile.get("lifetime_score", 0)) + score
    profile["wallet_score"] = int(profile.get("wallet_score", 0)) + score
    old_score = int(profile.get("high_scores", {}).get(chart_key, 0))
    profile.setdefault("high_scores", {})[chart_key] = max(old_score, score)
    badges = result_badges(result, previous_best_score=old_score)
    saved_badges = profile.setdefault("badges", [])
    if not isinstance(saved_badges, list):
        saved_badges = []
        profile["badges"] = saved_badges
    for badge in badges:
        if badge not in saved_badges:
            saved_badges.append(badge)
    profile["last_play_badges"] = badges
    played_at = now_iso()
    entry = {
        "played_at": played_at,
        "score": score,
        "accuracy": float(result.get("accuracy", 0.0)),
        "max_combo": int(result.get("max_combo", 0)),
        "rank": str(result.get("rank", "D")),
    }
    rankings = profile.setdefault("rankings", {})
    if not isinstance(rankings, dict):
        rankings = {}
        profile["rankings"] = rankings
    existing = rankings.get(chart_key, [])
    if not isinstance(existing, list):
        existing = []
    ordered = [*existing, entry]
    ordered.sort(
        key=lambda candidate: (
            -int(candidate.get("score", 0)),
            -float(candidate.get("accuracy", 0.0)),
            -int(candidate.get("max_combo", 0)),
            str(candidate.get("played_at", "")),
        )
    )
    rankings[chart_key] = ordered[:10]
    try:
        position = rankings[chart_key].index(entry) + 1
    except ValueError:
        position = 0
    profile["last_play_ranking"] = {
        "chart_key": chart_key,
        "position": position,
        "new_high_score": score > old_score,
        "made_top_ten": position > 0,
        "previous_best_score": old_score,
        "score_delta": score - old_score,
    }
    profile.setdefault("play_history", []).append({"played_at": played_at, **result, "chart_key": chart_key})
    newly_unlocked: list[str] = update_performance_unlocks(profile, chart_key=chart_key, result=result)
    save_profile(paths, profile)
    return newly_unlocked


def reward_thresholds(paths: AppPaths) -> dict[str, int]:
    config = paths.rewards / "reward_config.json"
    if not config.exists():
        return {}
    try:
        raw = json.loads(config.read_text(encoding="utf-8"))
        return {
            str(name): int(value.get("price", value.get("required_score", -1)))
            for name, value in raw.items()
            if (
                isinstance(value, dict)
                and int(value.get("price", value.get("required_score", -1))) >= 0
                and reward_image_path(paths, str(name)) is not None
            )
        }
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return {}
