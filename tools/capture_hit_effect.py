from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ["AUTOBEAT_DATA_DIR"] = str(ROOT / "artifacts" / "capture_data")

import pygame
from app import AutoBeatApp
from gameplay import GameSession, JudgmentWindows
from models import Chart, Difficulty, Judgment, Note


app = AutoBeatApp()
chart = Chart(
    version=1,
    music_hash="hit_effect_capture" * 4,
    difficulty=Difficulty.NORMAL,
    seed=1,
    song_duration=12.0,
    notes=[
        Note(2.0, 0),
        Note(2.4, 1),
        Note(2.8, 2),
        Note(3.2, 3),
        Note(3.6, 4),
        Note(4.1, 2),
    ],
)
app.chart = chart
app.session = GameSession(chart, JudgmentWindows())
app.screen = "game"
app.audio._last_time = 2.8
app.audio._started_at = None
app._play_feedback(Judgment.PERFECT, lane=2)
app.draw()
output = ROOT / "artifacts" / "hit_effect.png"
output.parent.mkdir(parents=True, exist_ok=True)
pygame.image.save(app.surface, output)
pygame.quit()
print(output)
