"""Read an analysis cache and compare standard charts without writing saves."""
import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from chart_balance import balance_chart, internal_gaps
from chart_generator import ChartGenerator
from chart_validator import ChartValidator
from models import AnalysisResult, Difficulty


def metrics(chart):
    seconds = {"empty": 0.0, "normal": 0.0, "dense": 0.0}
    for start in range(math.ceil(chart.song_duration)):
        end = min(start + 1, chart.song_duration)
        count = sum(start <= n.time < end for n in chart.notes)
        holding = any(n.end_time is not None and n.time < end and n.end_time > start
                      for n in chart.notes)
        category = "dense" if count / (end-start) >= 4 else (
            "empty" if count == 0 and not holding else "normal")
        seconds[category] += end-start
    return {
        "notes": len(chart.notes),
        "seconds": seconds,
        "percent": {k: round(v/chart.song_duration*100, 2) for k, v in seconds.items()},
        "longest_internal_gap": round(max((b-a for a, b in internal_gaps(chart)), default=0), 3),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis_cache", type=Path)
    parser.add_argument("--lanes", type=int, choices=(3, 5, 7), default=5)
    args = parser.parse_args()
    analysis = AnalysisResult.from_dict(json.loads(args.analysis_cache.read_text(encoding="utf-8")))
    results = []
    for difficulty in Difficulty:
        chart = ChartGenerator().generate(analysis, difficulty, lane_count=args.lanes)
        ChartValidator().validate(chart)
        before = metrics(chart)
        moved = balance_chart(chart, analysis)
        after = metrics(chart)
        assert before["notes"] == after["notes"]
        assert ChartValidator().validate(chart).removed_notes == 0
        results.append(dict(difficulty=difficulty.value, moves=moved, before=before, after=after))
    print(json.dumps(dict(duration=analysis.duration, lanes=args.lanes, results=results), indent=2))


if __name__ == "__main__":
    main()
