"""ご褒美画像フォルダをゲーム本体から分離して扱う。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from persistence import AppPaths, reward_thresholds

SUPPORTED_IMAGES = {".png", ".jpg", ".jpeg", ".webp"}


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


def ensure_reward_template(paths: AppPaths) -> None:
    """制作者が再ビルドなしで編集できる設定テンプレートを初回だけ作成する。"""
    paths.ensure()
    config = paths.rewards / "reward_config.json"
    if not config.exists():
        config.write_text(
            "{\n"
            "  \"reward_001.png\": {\n"
            "    \"required_score\": 100000\n"
            "  },\n"
            "  \"reward_002.png\": {\n"
            "    \"required_score\": 300000\n"
            "  }\n"
            "}\n",
            encoding="utf-8",
        )


def scan_rewards(paths: AppPaths, unlocked_names: set[str], lifetime_score: int | None = None) -> list[RewardImage]:
    paths.ensure()
    thresholds = reward_thresholds(paths)
    score = None if lifetime_score is None else max(0, int(lifetime_score))
    images = [
        file
        for file in paths.rewards.iterdir()
        if file.is_file() and file.suffix.lower() in SUPPORTED_IMAGES
    ]
    return [
        RewardImage(
            name=image.name,
            path=image,
            required_score=thresholds.get(image.name),
            unlocked=(
                image.name in unlocked_names
                or thresholds.get(image.name) == 0
                or (score is not None and thresholds.get(image.name) is not None and score >= int(thresholds[image.name]))
            ),
        )
        for image in sorted(images, key=lambda item: (thresholds.get(item.name, 10**18), item.name.lower()))
    ]


def reward_progress(paths: AppPaths, profile: dict[str, Any]) -> RewardProgress:
    """累積スコアに基づく解放数と次の解放までの進捗を返す。"""
    lifetime_score = max(0, int(profile.get("lifetime_score", 0)))
    rewards = scan_rewards(
        paths,
        set(profile.get("unlocked_rewards", [])),
        lifetime_score=lifetime_score,
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
    previous_required_score = max(
        (int(reward.required_score or 0) for reward in configured if int(reward.required_score or 0) <= lifetime_score),
        default=0,
    )
    span = max(1, next_required_score - previous_required_score)
    ratio = max(0.0, min(1.0, (lifetime_score - previous_required_score) / span))
    return RewardProgress(
        lifetime_score=lifetime_score,
        reward_count=len(configured),
        unlocked_count=unlocked_count,
        next_reward=next_reward,
        previous_required_score=previous_required_score,
        next_required_score=next_required_score,
        remaining_score=max(0, next_required_score - lifetime_score),
        progress_ratio=ratio,
    )
