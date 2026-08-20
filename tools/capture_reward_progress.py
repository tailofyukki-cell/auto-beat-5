"""ご褒美画像のスコア進捗と新規解放通知を隔離環境で描画する。"""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts" / "reward_progress_capture"
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["AUTOBEAT_DATA_DIR"] = str(ARTIFACTS / "data")
os.environ["AUTOBEAT_REWARDS_DIR"] = str(ARTIFACTS / "rewards")

import pygame  # noqa: E402

import sys  # noqa: E402
sys.path.insert(0, str(ROOT / "src"))
from app import AutoBeatApp  # noqa: E402


def create_reward(path: Path, color: tuple[int, int, int]) -> None:
    image = pygame.Surface((480, 320), pygame.SRCALPHA)
    image.fill((*color, 255))
    for index in range(5):
        pygame.draw.rect(image, (255, 255, 255, 80), pygame.Rect(42 + index * 84, 60 + (index % 2) * 42, 54, 170))
    pygame.image.save(image, str(path))


def main() -> None:
    app = AutoBeatApp()
    app.paths.rewards.mkdir(parents=True, exist_ok=True)
    create_reward(app.paths.rewards / "reward_100.png", (32, 130, 158))
    create_reward(app.paths.rewards / "reward_300.png", (89, 55, 158))
    (app.paths.rewards / "reward_config.json").write_text(
        json.dumps(
            {
                "reward_100.png": {"required_score": 100000},
                "reward_300.png": {"required_score": 300000},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    app.profile["lifetime_score"] = 75000
    app.screen = "gallery"
    app.draw()
    pygame.image.save(app.surface, str(ARTIFACTS / "gallery_progress.png"))

    app.profile["lifetime_score"] = 100000
    app.newly_unlocked = ["reward_100.png"]
    app.screen = "unlock"
    app.draw()
    pygame.image.save(app.surface, str(ARTIFACTS / "unlock_notice.png"))
    pygame.quit()


if __name__ == "__main__":
    main()
