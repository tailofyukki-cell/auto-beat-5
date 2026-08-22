"""AutoBeat 5 の実行エントリーポイント。"""
from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

SOURCE = Path(__file__).resolve().parent / "src"
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))


def run_release_audio_probe() -> int | None:
    """Run the packaged audio-analysis path without opening the game UI.

    This is intentionally activated only by the release preflight environment.
    It verifies the same analyzer and chart-generator code that the file picker
    invokes, including the fallback decoder used when a packaged codec fails.
    """
    source_value = os.environ.get("AUTOBEAT_RELEASE_AUDIO_PROBE_PATH")
    result_value = os.environ.get("AUTOBEAT_RELEASE_AUDIO_PROBE_RESULT")
    if not source_value or not result_value:
        return None

    result_path = Path(result_value)
    payload: dict[str, object] = {"source_path": source_value, "success": False}
    try:
        from analyzer import MusicAnalyzer
        from chart_generator import ChartGenerator
        from models import Difficulty

        analysis = MusicAnalyzer().analyze(source_value)
        chart = ChartGenerator().generate(analysis, Difficulty.BEGINNER)
        payload.update(
            {
                "success": True,
                "music_hash": analysis.music_hash,
                "duration": analysis.duration,
                "bpm": analysis.bpm,
                "note_count": len(chart.notes),
            }
        )
    except Exception as error:  # The result is consumed by the release gate.
        payload["error"] = str(error)
        payload["traceback"] = traceback.format_exc()
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if payload["success"] else 1


if __name__ == "__main__":
    probe_exit = run_release_audio_probe()
    if probe_exit is not None:
        raise SystemExit(probe_exit)

    from app import main

    main()
