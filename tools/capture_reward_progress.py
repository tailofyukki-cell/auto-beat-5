"""ご褒美画像のスコア進捗と新規解放通知を隔離環境で描画する。"""
from __future__ import annotations

import json
import os
import shutil
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
    shutil.rmtree(ARTIFACTS, ignore_errors=True)
    app = AutoBeatApp()
    app.paths.rewards.mkdir(parents=True, exist_ok=True)
    config: dict[str, dict[str, int]] = {}
    for index in range(8):
        name = f"reward_{index + 1:03d}.png"
        config[name] = {"required_score": (index + 1) * 100000}
        if index < 7:
            create_reward(app.paths.rewards / name, (32 + index * 20, 130 - index * 7, 158 + index * 8))
    (app.paths.rewards / "reward_config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    app.profile["lifetime_score"] = 75000
    app.screen = "gallery"
    app.draw()
    pygame.image.save(app.surface, str(ARTIFACTS / "gallery_progress.png"))

    app.profile["lifetime_score"] = 100000
    app.newly_unlocked = ["reward_001.png"]
    app.screen = "unlock"
    app.draw()
    pygame.image.save(app.surface, str(ARTIFACTS / "unlock_notice.png"))

    app.profile["lifetime_score"] = 250000
    app.open_reward_manager()
    app.scroll_reward_manager(2)
    app.draw()
    pygame.image.save(app.surface, str(ARTIFACTS / "reward_manager.png"))
    pygame.quit()


if __name__ == "__main__":
    main()
