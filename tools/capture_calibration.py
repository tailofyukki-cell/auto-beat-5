from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pygame
from app import AutoBeatApp
from calibration import CalibrationSession


def main() -> None:
    app = AutoBeatApp()
    session = CalibrationSession(started_at=time.perf_counter() - 4.2, warmup_beats=0, sample_target=10)
    for beat, offset_ms in enumerate((18, 21, 19, 17, 22, 20, 18, 21, 19, 20)):
        session.record_press(session.beat_time(beat) + offset_ms / 1000.0)
    app.calibration = session
    app.screen = "calibration"
    app.draw()
    output = ROOT / "artifacts" / "calibration.png"
    output.parent.mkdir(exist_ok=True)
    pygame.image.save(app.surface, output)
    pygame.quit()


if __name__ == "__main__":
    main()
