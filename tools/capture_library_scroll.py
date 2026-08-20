"""多数の解析済み楽曲を含むライブラリー画面を隔離データでキャプチャする。"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ["AUTOBEAT_DATA_DIR"] = str(ROOT / "artifacts" / "library_scroll_capture_data")
sys.path.insert(0, str(ROOT / "src"))

import pygame
from app import AutoBeatApp


def main() -> None:
    output = ROOT / "artifacts" / "library_scroll.png"
    data_dir = Path(os.environ["AUTOBEAT_DATA_DIR"])
    songs_dir = ROOT / "artifacts" / "library_scroll_songs"
    shutil.rmtree(data_dir, ignore_errors=True)
    shutil.rmtree(songs_dir, ignore_errors=True)
    songs_dir.mkdir(parents=True, exist_ok=True)
    app = AutoBeatApp()
    try:
        entries: list[dict[str, object]] = []
        for index in range(14):
            filename = "夜明けのプレイリスト.wav" if index == 10 else f"Library Track {index + 1:02d}.wav"
            path = songs_dir / filename
            path.write_bytes(b"")
            entries.append(
                {
                    "source_path": str(path),
                    "music_hash": f"{index + 1:064x}",
                    "bpm": 118.0 + index * 1.5,
                    "duration": 95.0 + index * 8.25,
                }
            )
        app.profile["recent_songs"] = entries
        app.open_library()
        app.scroll_library(7)
        app.draw()
        output.parent.mkdir(parents=True, exist_ok=True)
        pygame.image.save(app.surface, str(output))
        print(f"captured={output}")
        print(f"scroll={app.library_scroll_index} selected={app.library_selected_index}")
    finally:
        pygame.quit()
        shutil.rmtree(data_dir, ignore_errors=True)
        shutil.rmtree(songs_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
