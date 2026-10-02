"""譜面をプレイ前に説明するための軽量な集計モデル。"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import ceil

from models import AnalysisResult, Chart, NoteType, chart_lane_count


@dataclass(frozen=True, slots=True)
class ChartSummary:
    difficulty_label: str
    lane_count: int
    bpm: float
    duration_seconds: float
    total_notes: int
    tap_notes: int
    hold_notes: int
    chord_events: int
    max_chord_size: int
    notes_per_second: float
    peak_notes_per_second: int
    first_note_seconds: float | None
    validation_removed: int
    validation_issues: int
    lane_usage_text: str
    quality_note: str
    tendency: str

    @property
    def notes_per_minute(self) -> int:
        return int(round(self.notes_per_second * 60))

    @property
    def lane_count_label(self) -> str:
        return f"{self.lane_count} LANE"

    @property
    def first_note_text(self) -> str:
        return "ノーツなし" if self.first_note_seconds is None else f"{self.first_note_seconds:.2f} 秒"


def build_chart_summary(chart: Chart, analysis: AnalysisResult) -> ChartSummary:
    """譜面データと解析結果から、画面表示用の品質指標を安定して集計する。"""
    notes = chart.notes
    tap_notes = sum(note.kind is NoteType.TAP for note in notes)
    hold_notes = sum(note.kind is NoteType.HOLD for note in notes)
    grouped: dict[float, list[object]] = {}
    for note in notes:
        grouped.setdefault(round(note.time, 4), []).append(note)
    chord_sizes = [len(group) for group in grouped.values()]
    chord_events = sum(size > 1 for size in chord_sizes)
    max_chord_size = max(chord_sizes, default=0)
    duration = max(float(chart.song_duration), 0.001)
    notes_per_second = len(notes) / duration
    peak = _peak_notes_per_second(notes)
    first_note = min((note.time for note in notes), default=None)
    lane_count = chart_lane_count(chart)
    lane_counts = [sum(note.lane == lane for note in notes) for lane in range(lane_count)]
    used_lanes = sum(count > 0 for count in lane_counts)
    return ChartSummary(
        difficulty_label=chart.difficulty.label,
        lane_count=lane_count,
        bpm=float(analysis.bpm),
        duration_seconds=float(chart.song_duration),
        total_notes=len(notes),
        tap_notes=tap_notes,
        hold_notes=hold_notes,
        chord_events=chord_events,
        max_chord_size=max_chord_size,
        notes_per_second=notes_per_second,
        peak_notes_per_second=peak,
        first_note_seconds=first_note,
        validation_removed=int(chart.metadata.get("validation_removed", 0)),
        validation_issues=len(chart.metadata.get("validation_issues", [])),
        lane_usage_text=_lane_usage_text(lane_counts),
        quality_note=_quality_note(lane_count, used_lanes, notes_per_second, peak, chord_events),
        tendency=_estimate_tendency(notes_per_second, peak, chord_events, hold_notes),
    )


def _lane_usage_text(lane_counts: list[int]) -> str:
    if not lane_counts:
        return "なし"
    total = max(1, sum(lane_counts))
    used = sum(count > 0 for count in lane_counts)
    peak = max(lane_counts, default=0)
    peak_ratio = peak / total
    return f"{used}/{len(lane_counts)} lanes  最大{peak_ratio:.0%}"


def _quality_note(lane_count: int, used_lanes: int, notes_per_second: float, peak: int, chord_events: int) -> str:
    if used_lanes <= max(1, lane_count // 2):
        return "レーン偏りを確認"
    if lane_count == 3 and (notes_per_second >= 4.0 or peak >= 6):
        return "3レーンでは高密度"
    if lane_count == 7 and chord_events == 0 and notes_per_second >= 3.0:
        return "単押し中心で広く展開"
    if peak >= 8:
        return "瞬間密度に注意"
    return "バランス良好"


def _peak_notes_per_second(notes: list[object]) -> int:
    """1秒ごとの最大ノーツ数を返す。境界に強いよう連続する整数秒窓で数える。"""
    if not notes:
        return 0
    times = sorted(float(note.time) for note in notes)
    peak = 0
    for start in range(0, ceil(max(times)) + 1):
        peak = max(peak, sum(start <= value < start + 1 for value in times))
    return peak


def _estimate_tendency(notes_per_second: float, peak: int, chord_events: int, hold_notes: int) -> str:
    """難易度名とは別に、プレイヤーが読むべき操作傾向を短く表す。"""
    if notes_per_second < 1.8 and chord_events == 0 and hold_notes == 0:
        return "ゆったりした単押し中心"
    if chord_events > 0 and hold_notes > 0:
        return "同時押しと長押しを含む複合型"
    if peak >= 8 or notes_per_second >= 6.0:
        return "高速な連続入力に注意"
    if hold_notes > 0:
        return "長押しの終端を意識"
    if chord_events > 0:
        return "同時押しの見極めが必要"
    return "基本リズムを幅広く反映"
