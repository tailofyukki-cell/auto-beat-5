"""ご褒美画像フォルダをゲーム本体から分離して扱う。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from persistence import AppPaths, reward_thresholds

SUPPORTED_IMAGES = {".png", ".jpg", ".jpeg", ".webp"}


@dataclass(frozen=True, slots=True)
class RewardImage:
    name: str
    path: Path
    required_score: int | None
    unlocked: bool


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


def scan_rewards(paths: AppPaths, unlocked_names: set[str]) -> list[RewardImage]:
    paths.ensure()
    thresholds = reward_thresholds(paths)
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
            unlocked=image.name in unlocked_names,
        )
        for image in sorted(images, key=lambda item: item.name.lower())
    ]
