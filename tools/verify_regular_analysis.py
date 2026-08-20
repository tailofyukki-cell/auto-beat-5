"""任意の通常音源がアプリの選択・解析フローを完走できるか検証する。"""
from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ["AUTOBEAT_DATA_DIR"] = str(ROOT / "artifacts" / "regular_analysis_test_data")
sys.path.insert(0, str(ROOT / "src"))

import pygame
from app import AutoBeatApp
from models import Difficulty


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python tools/verify_regular_analysis.py <audio-file>")
    source = Path(sys.argv[1]).expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f"Audio file was not found: {source}")

    data_dir = Path(os.environ["AUTOBEAT_DATA_DIR"])
    shutil.rmtree(data_dir, ignore_errors=True)
    app = AutoBeatApp()
    try:
        app.select_song_path(source)
        deadline = time.monotonic() + 180.0
        while app.worker is not None and time.monotonic() < deadline:
            app.poll_worker()
            time.sleep(0.02)
        app.poll_worker()
        if app.worker is not None:
            raise RuntimeError("Analysis worker timed out")
        if app.error:
            raise RuntimeError(f"Analysis failed: {app.error}")
        if app.analysis is None or app.screen != "difficulty":
            raise RuntimeError(f"Analysis did not reach difficulty screen: {app.screen}")
        app.select_chart(Difficulty.BEGINNER)
        if app.chart is None or app.screen != "chart_summary":
            raise RuntimeError(f"Chart generation did not reach summary: {app.screen}")
        print(
            f"PASS: {source.name} | {app.analysis.bpm:.3f} BPM | "
            f"{app.analysis.duration:.2f}s | BEGINNER {len(app.chart.notes)} notes"
        )
    finally:
        pygame.quit()
        shutil.rmtree(data_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
