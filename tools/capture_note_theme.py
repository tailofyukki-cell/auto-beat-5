from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "artifacts" / "note_theme_capture_data"
shutil.rmtree(DATA_DIR, ignore_errors=True)
os.environ["AUTOBEAT_DATA_DIR"] = str(DATA_DIR)
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
sys.path.insert(0, str(ROOT / "src"))

import pygame
from app import AutoBeatApp, HitEffect
from gameplay import GameSession, Judgment, JudgmentWindows
from models import Chart, Difficulty, Note, NoteType


def main() -> None:
    app = AutoBeatApp()
    app.screen = "settings"
    app.settings_selection = 7
    app.settings["note_theme"] = "pastel"
    app.draw()
    pygame.image.save(app.surface, ROOT / "artifacts" / "note_theme_settings.png")

    chart = Chart(
        1,
        "theme_capture" * 5,
        Difficulty.NORMAL,
        1,
        6.0,
        notes=[
            Note(1.4, 0),
            Note(1.9, 1, NoteType.HOLD, 3.1),
            Note(2.4, 2),
            Note(2.8, 4),
        ],
    )
    app.chart = chart
    app.session = GameSession(chart, JudgmentWindows())
    app.screen = "game"
    app.settings["note_theme"] = "neon"
    app.audio = SimpleNamespace(time=2.2, paused=False, finished=False)
    app.hit_effects = [HitEffect(lane=3, judgment=Judgment.PERFECT, started_at=time.perf_counter())]
    app.draw()
    pygame.image.save(app.surface, ROOT / "artifacts" / "note_theme_neon.png")
    pygame.quit()


if __name__ == "__main__":
    main()
