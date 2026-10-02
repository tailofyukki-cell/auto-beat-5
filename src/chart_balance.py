"""Redistribute isolated taps without changing the validated note budget."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy

from chart_generator import ChartGenerator
from chart_validator import ChartValidator
from models import AnalysisResult, Chart, Difficulty, Note, NoteType, chart_lane_count


GAP_LIMITS = dict(zip(Difficulty, (2.5, 2.0, 1.5, 1.0, 1.0)))


def internal_gaps(chart: Chart) -> list[tuple[float, float]]:
    """Exclude lead-in/tail and consider sustained notes active throughout."""
    gaps = []
    end = None
    for note in sorted(chart.notes, key=lambda n: n.time):
        if end is not None and note.time > end:
            gaps.append((end, note.time))
        end = max(end or 0.0, note.end_time or note.time)
    return gaps


def balance_chart(chart: Chart, analysis: AnalysisResult) -> int:
    """Run after safety validation; accept only one-for-one safe replacements."""
    if chart.metadata.get("gap_balance_version") in (1, 2):
        return int(chart.metadata.get("gap_balance_moves", 0))
    limit = GAP_LIMITS[chart.difficulty]
    moved = 0
    while True:
        gaps = sorted((g for g in internal_gaps(chart) if g[1]-g[0] >= limit),
                      key=lambda g: (-(g[1]-g[0]), g[0]))
        counts = Counter(round(n.time, 4) for n in chart.notes)
        donors = []
        for n in chart.notes:
            if n.kind is not NoteType.TAP or n.source != "onset" or counts[round(n.time, 4)] != 1:
                continue
            neighbors = [x for x in chart.notes if x is not n]
            before = max((x.end_time or x.time for x in neighbors if x.time < n.time), default=-999)
            after = min((x.time for x in neighbors if x.time > n.time), default=999999)
            density = sum(abs(x.time-n.time) < 0.5 for x in chart.notes)
            if density >= 4 and after-before < limit:
                donors.append((n.strength, -density, n.time, n))
        donors.sort(key=lambda item: item[:3])
        accepted = False
        for start, end in gaps:
            candidates = []
            for i, onset in enumerate(analysis.onsets):
                strength = ChartGenerator._at(analysis.onset_strengths, i, 0.0)
                time = ChartGenerator._quantize(onset, analysis.beats, chart.difficulty)
                if strength > 0 and start+0.4 <= time <= end-0.4:
                    candidates.append((abs(time-(start+end)/2), -strength, time, strength))
            for _, _, time, strength in sorted(candidates):
                for _, _, _, donor in donors:
                    for lane in sorted(range(chart_lane_count(chart)), key=lambda x: (abs(x-donor.lane), x)):
                        trial = deepcopy(chart)
                        trial.notes = [deepcopy(n) for n in chart.notes if n is not donor]
                        trial.notes.append(Note(time, lane, source="gap_balance", strength=strength))
                        report = ChartValidator().validate(trial)
                        if report.removed_notes or len(trial.notes) != len(chart.notes):
                            continue
                        chart.notes = trial.notes
                        moved += 1
                        accepted = True
                        break
                    if accepted:
                        break
                if accepted:
                    break
            if accepted:
                break
        if not accepted:
            break
    chart.sort()
    chart.metadata.update(gap_balance_version=2, gap_balance_moves=moved,
                          gap_balance_limit_seconds=limit)
    return moved
