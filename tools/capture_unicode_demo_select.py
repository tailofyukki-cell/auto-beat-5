"""展開済み体験版のdemo_songsを使って選曲画面をキャプチャする。"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ["AUTOBEAT_DATA_DIR"] = str(ROOT / "artifacts" / "unicode_demo_capture_data")
sys.path.insert(0, str(ROOT / "src"))

import pygame
from app import AutoBeatApp


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python tools/capture_unicode_demo_select.py <demo-songs-dir> <output-png>")
    demo_dir = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2]).resolve()
    if not demo_dir.is_dir():
        raise SystemExit(f"Demo songs directory not found: {demo_dir}")
    os.environ["AUTOBEAT_DEMO_SONGS_DIR"] = str(demo_dir)
    data_dir = Path(os.environ["AUTOBEAT_DATA_DIR"])
    shutil.rmtree(data_dir, ignore_errors=True)
    app = AutoBeatApp()
    try:
        app.screen = "select"
        app.draw()
        output.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(app.surface, str(output))
        names = [path.name for path in app.demo_song_files()]
        if "ここから始まる～夜明けの光～.wav" not in names:
            raise RuntimeError(f"Japanese demo filename was not detected: {names}")
        print(f"captured={output}")
        print(f"demo_names={names}")
    finally:
        pygame.quit()
        shutil.rmtree(data_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
