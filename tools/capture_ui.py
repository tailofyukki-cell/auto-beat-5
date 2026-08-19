from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("AUTOBEAT_DATA_DIR", str(ROOT / "artifacts" / "ui_userdata"))

sys.path.insert(0, str(ROOT / "src"))

import pygame
from app import AutoBeatApp


app = AutoBeatApp()
image_path = app.paths.rewards / "reward_001.png"
image_path.parent.mkdir(parents=True, exist_ok=True)
image = pygame.Surface((640, 360), pygame.SRCALPHA)
image.fill((49, 101, 167, 255))
pygame.draw.circle(image, (255, 204, 89, 255), (320, 180), 100)
pygame.image.save(image, str(image_path))
(app.paths.rewards / "reward_config.json").write_text(
    '{"reward_001.png": {"required_score": 100000}}', encoding="utf-8"
)
app.profile["unlocked_rewards"] = ["reward_001.png"]

for screen in ("title", "settings", "gallery"):
    app.screen = screen
    app.draw()
    pygame.image.save(app.surface, str(ROOT / "artifacts" / f"{screen}.png"))
reward = app.gallery_rewards()[0]
app.open_reward(reward)
app.draw()
pygame.image.save(app.surface, str(ROOT / "artifacts" / "gallery_preview.png"))
pygame.quit()
