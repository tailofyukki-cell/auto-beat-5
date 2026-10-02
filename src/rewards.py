"""ご褒美画像フォルダをゲーム本体から分離して扱う。"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from persistence import AppPaths, materialize_unlocked_rewards, normalize_profile, reward_image_paths, reward_thresholds, set_locked_rewards_hidden

SUPPORTED_IMAGES = {".png", ".jpg", ".jpeg", ".webp"}


def _needs_materialize(paths: AppPaths, paths_by_name: dict[str, Path], name: str) -> bool:
    source = paths_by_name.get(name)
    if source is None:
        return False
    target = paths.rewards / "unlocked" / Path(name).name
    try:
        return source.resolve() != target.resolve() or not target.is_file()
    except OSError:
        return True


@dataclass(frozen=True, slots=True)
class RewardImage:
    name: str
    path: Path
    required_score: int | None
    unlocked: bool


@dataclass(frozen=True, slots=True)
class RewardProgress:
    """ご褒美解放の現在地と、次の目標を画面へ渡す値。"""

    lifetime_score: int
    reward_count: int
    unlocked_count: int
    next_reward: RewardImage | None
    previous_required_score: int
    next_required_score: int | None
    remaining_score: int
    progress_ratio: float


@dataclass(frozen=True, slots=True)
class RewardCatalogItem:
    """報酬管理画面で表示する、設定と実画像を突合した1件分の状態。"""

    name: str
    path: Path
    required_score: int | None
    exists: bool
    unlocked: bool
    remaining_score: int | None


def ensure_reward_template(paths: AppPaths) -> None:
    """制作者が再ビルドなしで編集できる設定テンプレートを初回だけ作成する。"""
    paths.ensure()
    (paths.rewards / "locked").mkdir(parents=True, exist_ok=True)
    (paths.rewards / "unlocked").mkdir(parents=True, exist_ok=True)
    set_locked_rewards_hidden(paths)
    config = paths.rewards / "reward_config.json"
    if not config.exists():
        config.write_text(
            "{\n"
            "  \"reward_001.png\": {\n"
            "    \"price\": 100000\n"
            "  },\n"
            "  \"reward_002.png\": {\n"
            "    \"price\": 300000\n"
            "  }\n"
            "}\n",
            encoding="utf-8",
        )


def scan_rewards(paths: AppPaths, unlocked_names: set[str], lifetime_score: int | None = None) -> list[RewardImage]:
    paths.ensure()
    thresholds = reward_thresholds(paths)
    paths_by_name = reward_image_paths(paths)
    unlockable = {
        name
        for name, required in thresholds.items()
        if name in paths_by_name
        and (name in unlocked_names or required == 0)
        and _needs_materialize(paths, paths_by_name, name)
    }
    if unlockable:
        materialize_unlocked_rewards(paths, unlockable)
        paths_by_name = reward_image_paths(paths)
    images = list(paths_by_name.values())
    return [
        RewardImage(
            name=image.name,
            path=image,
            required_score=thresholds.get(image.name),
            unlocked=(
                image.name in unlocked_names
                or thresholds.get(image.name) == 0
            ),
        )
        for image in sorted(images, key=lambda item: (thresholds.get(item.name, 10**18), item.name.lower()))
    ]


def reward_catalog(paths: AppPaths, profile: dict[str, Any]) -> list[RewardCatalogItem]:
    """設定済み・未設定・不足画像を含む報酬一覧を、管理画面向けに返す。"""
    paths.ensure()
    normalize_profile(profile)
    wallet_score = max(0, int(profile.get("wallet_score", 0)))
    unlocked_names = set(profile.get("unlocked_rewards", []))
    config_path = paths.rewards / "reward_config.json"
    raw: dict[str, Any] = {}
    try:
        loaded = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
        raw = loaded if isinstance(loaded, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        raw = {}

    configured: dict[str, int] = {}
    for name, value in raw.items():
        try:
            required = int(value.get("price", value.get("required_score", -1))) if isinstance(value, dict) else -1
        except (TypeError, ValueError):
            continue
        if required >= 0:
            configured[str(name)] = required

    paths_by_name = reward_image_paths(paths)
    unlockable = {
        name
        for name, required in configured.items()
        if name in paths_by_name
        and (name in unlocked_names or required == 0)
        and _needs_materialize(paths, paths_by_name, name)
    }
    if unlockable:
        materialize_unlocked_rewards(paths, unlockable)
        paths_by_name = reward_image_paths(paths)
    images = dict(paths_by_name)
    names = set(configured) | set(images)
    catalog: list[RewardCatalogItem] = []
    for name in names:
        path = images.get(name, paths.rewards / name)
        exists = name in images
        required = configured.get(name)
        unlocked = bool(exists and required is not None and (name in unlocked_names or required == 0))
        remaining = None if required is None else max(0, required - wallet_score)
        catalog.append(
            RewardCatalogItem(
                name=name,
                path=path,
                required_score=required,
                exists=exists,
                unlocked=unlocked,
                remaining_score=remaining,
            )
        )
    return sorted(
        catalog,
        key=lambda item: (
            item.required_score is None,
            item.required_score if item.required_score is not None else 10**18,
            item.name.lower(),
        ),
    )


def reward_progress(paths: AppPaths, profile: dict[str, Any]) -> RewardProgress:
    """購入済み画像数と、所持BEAT POINTSに対する次の価格を返す。"""
    normalize_profile(profile)
    lifetime_score = max(0, int(profile.get("lifetime_score", 0)))
    wallet_score = max(0, int(profile.get("wallet_score", 0)))
    rewards = scan_rewards(
        paths,
        set(profile.get("unlocked_rewards", [])),
        lifetime_score=None,
    )
    configured = [reward for reward in rewards if reward.required_score is not None]
    unlocked_count = sum(1 for reward in configured if reward.unlocked)
    upcoming = [reward for reward in configured if not reward.unlocked]
    next_reward = min(upcoming, key=lambda reward: (int(reward.required_score or 0), reward.name), default=None)

    if next_reward is None or next_reward.required_score is None:
        return RewardProgress(
            lifetime_score=lifetime_score,
            reward_count=len(configured),
            unlocked_count=unlocked_count,
            next_reward=None,
            previous_required_score=lifetime_score,
            next_required_score=None,
            remaining_score=0,
            progress_ratio=1.0 if configured else 0.0,
        )

    next_required_score = int(next_reward.required_score)
    previous_required_score = 0
    ratio = max(0.0, min(1.0, wallet_score / max(1, next_required_score)))
    return RewardProgress(
        lifetime_score=lifetime_score,
        reward_count=len(configured),
        unlocked_count=unlocked_count,
        next_reward=next_reward,
        previous_required_score=previous_required_score,
        next_required_score=next_required_score,
        remaining_score=max(0, next_required_score - wallet_score),
        progress_ratio=ratio,
    )
