"""生成譜面のプレイ可能性を検査し、機械的に危険な配置を除去する。"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import groupby

from chart_generator import RULES
from models import Chart, Difficulty, Note, NoteType, chart_lane_count


@dataclass(slots=True)
class ValidationReport:
    removed_notes: int = 0
    shifted_notes: int = 0
    issues: list[str] | None = None

    def __post_init__(self) -> None:
        if self.issues is None:
            self.issues = []


class ChartValidator:
    """5レーンの手分担を前提に、難易度ごとの入力密度を制限する。"""

    def validate(self, chart: Chart) -> ValidationReport:
        report = ValidationReport()
        rule = RULES[chart.difficulty]
        chart.sort()
        lane_count = chart_lane_count(chart)
        filtered = self._limit_same_lane_gaps(chart.notes, rule.min_gap, report, lane_count)
        filtered = self._limit_chords(filtered, min(rule.max_chord_size, 2 if lane_count == 3 else lane_count), report)
        filtered = self._remove_impossible_holds(filtered, chart.difficulty, report, lane_count)
        filtered = self._limit_hand_bursts(filtered, chart.difficulty, report, lane_count)
        chart.notes = sorted(filtered, key=lambda note: (note.time, note.lane))
        chart.sort()
        return report

    @staticmethod
    def _limit_same_lane_gaps(notes: list[Note], min_gap: float, report: ValidationReport, lane_count: int = 5) -> list[Note]:
        latest = [-999.0] * lane_count
        result: list[Note] = []
        for note in sorted(notes, key=lambda item: (item.time, -item.strength)):
            if not 0 <= note.lane < lane_count:
                report.removed_notes += 1
                report.issues.append(f"lane {note.lane + 1}: レーン数外のノーツを除去")
                continue
            if note.time - latest[note.lane] < min_gap:
                report.removed_notes += 1
                report.issues.append(f"lane {note.lane + 1}: 同一キー間隔が短すぎるノーツを除去")
                continue
            result.append(note)
            latest[note.lane] = note.time
        return result

    @staticmethod
    def _limit_chords(notes: list[Note], maximum: int, report: ValidationReport) -> list[Note]:
        result: list[Note] = []
        for _, group in groupby(sorted(notes, key=lambda item: (round(item.time, 4), item.kind is not NoteType.HOLD, -item.strength)), key=lambda item: round(item.time, 4)):
            same_time = list(group)
            original_count = len(same_time)
            if original_count > maximum:
                same_time = sorted(same_time, key=lambda item: (item.kind is not NoteType.HOLD, -item.strength))[:maximum]
                report.removed_notes += original_count - maximum
                report.issues.append("難易度上限を超える同時押しを抑制")
            result.extend(same_time)
        return result

    @staticmethod
    def _remove_impossible_holds(notes: list[Note], difficulty: Difficulty, report: ValidationReport, lane_count: int = 5) -> list[Note]:
        holds = [note for note in notes if note.kind is NoteType.HOLD]
        rejected: set[str] = set()
        for hold in holds:
            end = hold.end_time or hold.time
            center = lane_count // 2
            hand_lanes = {lane for lane in range(lane_count) if (lane < center and hold.lane < center) or (lane > center and hold.lane > center) or (lane == center and hold.lane == center)}
            # 同じ手の二重ホールドは禁止。中央は親指として独立扱い。
            for other in holds:
                if other is hold:
                    continue
                other_end = other.end_time or other.time
                overlaps = max(hold.time, other.time) < min(end, other_end)
                if overlaps and other.lane in hand_lanes:
                    weaker = hold if hold.strength <= other.strength else other
                    rejected.add(weaker.id)
            # ホールド中に同じ手側のTapを要求しない。反対側と中央は演奏可能として残す。
            for tap in notes:
                if tap is hold or tap.kind is NoteType.HOLD:
                    continue
                if hold.time < tap.time < end and tap.lane in hand_lanes:
                    rejected.add(tap.id)
        if rejected:
            report.removed_notes += len(rejected)
            report.issues.append("長押しと同一手の衝突を除去")
        return [note for note in notes if note.id not in rejected]

    @staticmethod
    def _limit_hand_bursts(notes: list[Note], difficulty: Difficulty, report: ValidationReport, lane_count: int = 5) -> list[Note]:
        # 0.4秒における片手キー入力数を上限化。Spaceは親指として両手負荷から除外する。
        maximum = {
            Difficulty.BEGINNER: 3,
            Difficulty.EASY: 4,
            Difficulty.NORMAL: 5,
            Difficulty.HARD: 7,
            Difficulty.EXPERT: 9,
        }[difficulty]
        sorted_notes = sorted(notes, key=lambda item: (item.time, -item.strength))
        keep: list[Note] = []
        center = lane_count // 2
        for note in sorted_notes:
            if note.lane == center:
                keep.append(note)
                continue
            same_hand = [
                previous
                for previous in keep
                if previous.lane != center
                and (previous.lane < center) == (note.lane < center)
                and 0 <= note.time - previous.time < 0.4
            ]
            if len(same_hand) >= maximum:
                report.removed_notes += 1
                report.issues.append("片手への短時間入力集中を抑制")
                continue
            keep.append(note)
        return keep

