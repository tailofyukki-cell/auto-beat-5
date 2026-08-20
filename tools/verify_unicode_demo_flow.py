"""Windows展開後の日本語名デモ曲が選択・譜面読込できることを検証する。"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ["AUTOBEAT_DATA_DIR"] = str(ROOT / "artifacts" / "unicode_demo_flow_data")
sys.path.insert(0, str(ROOT / "src"))

import pygame
from app import AutoBeatApp
from models import Difficulty

FILENAME = "ここから始まる～夜明けの光～.wav"


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python tools/verify_unicode_demo_flow.py <demo-songs-dir>")
    demo_dir = Path(sys.argv[1]).resolve()
    if not (demo_dir / FILENAME).is_file():
        raise SystemExit(f"Japanese demo file was not found: {demo_dir / FILENAME}")
    os.environ["AUTOBEAT_DEMO_SONGS_DIR"] = str(demo_dir)
    data_dir = Path(os.environ["AUTOBEAT_DATA_DIR"])
    shutil.rmtree(data_dir, ignore_errors=True)
    app = AutoBeatApp()
    try:
        song = demo_dir / FILENAME
        app.load_demo_song(song)
        if app.screen != "difficulty" or app.analysis is None:
            raise RuntimeError(f"Demo cache did not load: screen={app.screen}, error={app.error}")
        app.select_chart(Difficulty.BEGINNER)
        if app.screen != "chart_summary" or app.chart is None:
            raise RuntimeError(f"Demo chart did not load: screen={app.screen}, error={app.error}")
        print(f"PASS: {song.name} | {app.analysis.bpm:.3f} BPM | {len(app.chart.notes)} BEGINNER notes")
    finally:
        pygame.quit()
        shutil.rmtree(data_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
