"""Render title previews without accessing the player's save data."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pygame
from app import AutoBeatApp


def main():
    output = ROOT / "artifacts" / "title_preview"
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"AUTOBEAT_DATA_DIR": temporary}):
        app = AutoBeatApp()
        for size in ((1600, 900), (1280, 720), (960, 540)):
            app.display_surface = pygame.display.set_mode(size)
            app.surface = app._create_render_surface(size)
            with patch("pygame.time.get_ticks", return_value=3000):
                app.draw()
                app._title_scene.started = 0
                app.draw()
            path = output / f"otoasobi-title-{size[0]}x{size[1]}.png"
            pygame.image.save(app.display_surface, str(path))
            print(path)
        pygame.quit()


if __name__ == "__main__":
    main()
