from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("AUTOBEAT_DATA_DIR", str(ROOT / "artifacts" / "chart_summary_capture_data"))
sys.path.insert(0, str(ROOT / "src"))

import pygame
from app import AutoBeatApp
from models import AnalysisResult, Difficulty


def main() -> None:
    app = AutoBeatApp()
    app.analysis = AnalysisResult(
        music_hash="v" * 64,
        source_path="demo_track.wav",
        duration=132.4,
        sample_rate=22050,
        bpm=128.0,
        beats=[index * 0.46875 for index in range(280)],
        onsets=[1.3 + index * 0.29 for index in range(130)],
        onset_strengths=[0.85 - (index % 4) * 0.06 for index in range(130)],
        band_energy=[[0.62, 0.18, 0.25, 0.55, 0.44] for _ in range(130)],
        percussive_strengths=[0.48 for _ in range(130)],
        sustained_segments=[(12.0, 14.0, 1), (42.0, 44.0, 3), (88.0, 90.2, 0)],
        local_bpms=[(0.0, 128.0), (66.0, 130.0)],
        downbeats=[index * 1.875 for index in range(71)],
    )
    app.song_path = Path(app.analysis.source_path)
    app.select_chart(Difficulty.NORMAL)
    app.draw()
    output = ROOT / "artifacts" / "chart_summary.png"
    output.parent.mkdir(exist_ok=True)
    pygame.image.save(app.surface, output)
    pygame.quit()


if __name__ == "__main__":
    main()
