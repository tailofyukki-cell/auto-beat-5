"""demo_songs内の音源を解析し、体験版同梱用のキャッシュと譜面を生成する。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analyzer import MusicAnalyzer
from chart_generator import ChartGenerator
from chart_validator import ChartValidator
from models import Difficulty

AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".flac"}
BUNDLE_VERSION = 1


def write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    demo_root = ROOT / "demo_songs"
    songs = sorted(path for path in demo_root.iterdir() if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS)
    if not songs:
        raise SystemExit("No supported audio files were found in demo_songs.")

    analyzer = MusicAnalyzer(lambda ratio, stage: print(f"[{ratio * 100:5.1f}%] {stage}", flush=True))
    generator = ChartGenerator()
    validator = ChartValidator()
    manifest_songs: list[dict[str, object]] = []

    for source in songs:
        print(f"\nPreparing demo song: {source.name}", flush=True)
        analysis = analyzer.analyze(source)
        write_json(demo_root / "cache" / f"{analysis.music_hash}.json", analysis.to_dict())
        chart_info: list[dict[str, object]] = []
        for difficulty in Difficulty:
            chart = generator.generate(analysis, difficulty, variant=0)
            report = validator.validate(chart)
            chart.metadata["validation_removed"] = report.removed_notes
            chart.metadata["validation_issues"] = report.issues[:20]
            write_json(demo_root / "charts" / analysis.music_hash / f"{difficulty.value}.json", chart.to_dict())
            chart_info.append({"difficulty": difficulty.value, "notes": len(chart.notes)})
            print(f"  {difficulty.label}: {len(chart.notes)} notes", flush=True)
        manifest_songs.append(
            {
                "file": source.name,
                "music_hash": analysis.music_hash,
                "bpm": analysis.bpm,
                "duration": analysis.duration,
                "analyzer_version": analysis.analyzer_version,
                "charts": chart_info,
            }
        )

    write_json(demo_root / "demo_manifest.json", {"version": BUNDLE_VERSION, "songs": manifest_songs})
    print(f"\nPrepared {len(manifest_songs)} demo song bundle(s).", flush=True)


if __name__ == "__main__":
    main()
