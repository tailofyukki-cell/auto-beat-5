"""AutoBeat 5 のローカル永続化。破損ファイルは退避して既定値へ戻す。"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from models import AnalysisResult, Chart, DEFAULT_KEYS

APP_NAME = "AutoBeat5"
RELEASE_CHANNEL_MARKER = "RELEASE_CHANNEL.txt"


def data_namespace() -> str:
    """Return an isolated AppData namespace for a packaged release channel.

    Development builds continue to use ``AutoBeat5``. A packaged release carries
    a short marker next to the executable, preventing it from reading a
    developer's personal profile, library history, scores, or cached charts.
    """
    if not getattr(sys, "frozen", False):
        return APP_NAME
    marker = Path(sys.executable).resolve().parent / RELEASE_CHANNEL_MARKER
    try:
        channel = marker.read_text(encoding="utf-8").strip()
    except OSError:
        return APP_NAME
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


DEFAULT_SETTINGS: dict[str, Any] = {
    "keys": list(DEFAULT_KEYS),
    "music_volume": 0.8,
    "sfx_volume": 0.7,
    "note_speed": 625.0,
    "playfield_mode": "standard",
    "note_theme": "standard",
    "timing_offset_ms": 0,
    "fullscreen": False,
    "resolution": [1280, 720],
    "judgment_windows_ms": {"perfect": 45, "great": 90, "good": 140},
}

DEFAULT_PROFILE: dict[str, Any] = {
    "lifetime_score": 0,
    "unlocked_rewards": [],
    "high_scores": {},
    "rankings": {},
    "last_play_ranking": {},
    "play_history": [],
    "recent_songs": [],
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


def load_settings(paths: AppPaths) -> dict[str, Any]:
    paths.ensure()
    settings = _load_json(paths.settings, DEFAULT_SETTINGS)
    keys = settings.get("keys")
    if not isinstance(keys, list) or len(keys) != 5 or len(set(keys)) != 5:
        settings["keys"] = list(DEFAULT_KEYS)
    return settings


def save_settings(paths: AppPaths, settings: dict[str, Any]) -> None:
    if len(settings.get("keys", [])) != 5 or len(set(settings["keys"])) != 5:
        raise ValueError("lane keys must be five unique keys")
    _atomic_write_json(paths.settings, settings)


def load_profile(paths: AppPaths) -> dict[str, Any]:
    paths.ensure()
    return _load_json(paths.profile, DEFAULT_PROFILE)


def save_profile(paths: AppPaths, profile: dict[str, Any]) -> None:
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


def chart_path(paths: AppPaths, digest: str, difficulty: str) -> Path:
    return paths.charts / digest / f"{difficulty}.json"


def load_chart(paths: AppPaths, digest: str, difficulty: str) -> Chart | None:
    path = chart_path(paths, digest, difficulty)
    try:
        if path.exists():
            return Chart.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        path.unlink(missing_ok=True)
    return None


def save_chart(paths: AppPaths, chart: Chart) -> None:
    _atomic_write_json(chart_path(paths, chart.music_hash, chart.difficulty.value), chart.to_dict())


RECENT_SONG_LIMIT = 100


def record_recent_song(paths: AppPaths, profile: dict[str, Any], analysis: AnalysisResult) -> None:
    """解析済み楽曲を最大100件のローカルライブラリーとして保持する。音源本体は保存しない。"""
    entry = {
        "music_hash": analysis.music_hash,
        "source_path": analysis.source_path,
        "duration": round(float(analysis.duration), 3),
        "bpm": round(float(analysis.bpm), 3),
        "last_used": now_iso(),
    }
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
    for chart_key, entries in raw_rankings.items():
        if not isinstance(chart_key, str) or not chart_key.startswith(prefix) or not isinstance(entries, list):
            continue
        difficulty = chart_key[len(prefix) :]
        valid = [dict(entry) for entry in entries if isinstance(entry, dict) and "score" in entry]
        if valid:
            summary[difficulty] = valid[0]
    return summary


def record_play(paths: AppPaths, profile: dict[str, Any], *, chart_key: str, result: dict[str, Any]) -> list[str]:
    """プレイ成績・自己ベスト・曲別ローカル順位表を保存し、新しく解放された画像名を返す。"""
    score = int(result["score"])
    profile["lifetime_score"] = int(profile.get("lifetime_score", 0)) + score
    old_score = int(profile.get("high_scores", {}).get(chart_key, 0))
    profile.setdefault("high_scores", {})[chart_key] = max(old_score, score)
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
    }
    profile.setdefault("play_history", []).append({"played_at": played_at, **result, "chart_key": chart_key})
    unlocked = set(profile.get("unlocked_rewards", []))
    newly_unlocked: list[str] = []
    for name, required in reward_thresholds(paths).items():
        if profile["lifetime_score"] >= required and name not in unlocked:
            unlocked.add(name)
            newly_unlocked.append(name)
    profile["unlocked_rewards"] = sorted(unlocked)
    save_profile(paths, profile)
    return newly_unlocked


def reward_thresholds(paths: AppPaths) -> dict[str, int]:
    config = paths.rewards / "reward_config.json"
    if not config.exists():
        return {}
    try:
        raw = json.loads(config.read_text(encoding="utf-8"))
        return {
            str(name): int(value["required_score"])
            for name, value in raw.items()
            if (
                isinstance(value, dict)
                and int(value.get("required_score", -1)) >= 0
                and (paths.rewards / str(name)).is_file()
            )
        }
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return {}
