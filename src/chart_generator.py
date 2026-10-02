"""音楽の特徴量を5レーン譜面へ変換する決定論的な生成器。"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from math import inf
from typing import Iterable

import numpy as np

from models import AnalysisResult, Chart, Difficulty, Note, NoteType, normalize_lane_count


@dataclass(frozen=True, slots=True)
class DifficultyRule:
    strength_percentile: float
    min_gap: float
    allow_chords: bool
    max_chord_size: int
    max_chord_ratio: float
    allow_holds: bool
    max_hold_ratio: float
    min_hold_duration: float
    allow_dense_patterns: bool
    max_notes_per_second: float


# ノーツが画面上端から判定線へ届く時間より少し長く確保する。
# カウントダウン後に音源が始まっても、最初の入力を準備できる。
START_LEAD_IN_SECONDS = 1.20
CHART_STYLE_LABELS = {"standard": "標準", "bass": "低音重視", "rhythm": "リズム重視"}

RULES: dict[Difficulty, DifficultyRule] = {
    Difficulty.BEGINNER: DifficultyRule(80, 0.48, False, 1, 0.00, False, 0.00, 0.00, False, 2.0),
    Difficulty.EASY: DifficultyRule(65, 0.30, False, 1, 0.00, True, 0.08, 1.10, False, 3.5),
    Difficulty.NORMAL: DifficultyRule(53, 0.19, True, 2, 0.10, True, 0.12, 0.85, True, 5.0),
    Difficulty.HARD: DifficultyRule(35, 0.10, True, 3, 0.15, True, 0.16, 0.60, True, 8.0),
    Difficulty.EXPERT: DifficultyRule(20, 0.07, True, 3, 0.20, True, 0.20, 0.60, True, 11.0),
}


class ChartGenerator:
    VERSION = "1.9"

    @staticmethod
    def _lane_rule(rule: DifficultyRule, difficulty: Difficulty, lane_count: int) -> DifficultyRule:
        if lane_count == 3:
            return DifficultyRule(
                min(92.0, rule.strength_percentile + 5.0),
                rule.min_gap + 0.02,
                rule.allow_chords and difficulty not in (Difficulty.BEGINNER, Difficulty.EASY),
                min(rule.max_chord_size, 2),
                rule.max_chord_ratio,
                rule.allow_holds,
                rule.max_hold_ratio,
                rule.min_hold_duration,
                rule.allow_dense_patterns and difficulty is not Difficulty.NORMAL,
                max(1.0, rule.max_notes_per_second * 0.86),
            )
        if lane_count == 7 and difficulty in (Difficulty.HARD, Difficulty.EXPERT):
            return DifficultyRule(
                max(12.0, rule.strength_percentile - 4.0),
                max(0.055, rule.min_gap - 0.005),
                rule.allow_chords,
                rule.max_chord_size,
                rule.max_chord_ratio,
                rule.allow_holds,
                rule.max_hold_ratio,
                rule.min_hold_duration,
                rule.allow_dense_patterns,
                rule.max_notes_per_second * 1.08,
            )
        return rule

    @staticmethod
    def _style_matches(analysis: AnalysisResult, index: int, style: str) -> bool:
        if style == "bass":
            bands = ChartGenerator._bands_at(analysis, index)
            total = sum(bands)
            return total > 0 and sum(bands[:2]) / total >= 0.45
        if style == "rhythm":
            return ChartGenerator._at(analysis.percussive_strengths, index, 0.0) >= 0.35
        return False

    @classmethod
    def candidate_style(cls, analysis: AnalysisResult, variant: int) -> str:
        if variant <= 0 or not analysis.onsets:
            return "standard"
        styles = ["standard"]
        for style in ("bass", "rhythm"):
            matching = sum(cls._style_matches(analysis, i, style) for i in range(len(analysis.onsets)))
            if matching >= max(3, len(analysis.onsets) * 0.20):
                styles.append(style)
        return styles[variant % len(styles)]

    def generate(self, analysis: AnalysisResult, difficulty: Difficulty, *, variant: int = 0, lane_count: int = 5, style: str = "standard") -> Chart:
        """同じvariantでは再現可能に、variantを変えると別のレーン候補を生成する。"""
        lane_count = normalize_lane_count(lane_count)
        rule = self._lane_rule(RULES[difficulty], difficulty, lane_count)
        variant = max(0, int(variant))
        if style not in CHART_STYLE_LABELS:
            raise ValueError(f"unknown chart style: {style}")
        style_targets: dict[float, int] = {}
        seed = int(hashlib.sha256(f"{analysis.music_hash}:{difficulty.value}:{lane_count}:{variant}".encode()).hexdigest()[:16], 16)
        notes: list[Note] = []
        candidates = self._select_candidates(analysis, rule)
        last_by_lane = [-inf] * lane_count
        previous_lane = lane_count // 2

        for index in candidates:
            time = self._quantize(float(analysis.onsets[index]), analysis.beats, difficulty)
            if time < START_LEAD_IN_SECONDS or time > analysis.duration - 0.05:
                continue
            bands = self._bands_at(analysis, index)
            if self._style_matches(analysis, index, style):
                style_targets[time] = max(0, lane_count // 2 - 1) if style == "bass" else lane_count // 2
            strength = self._at(analysis.onset_strengths, index, 0.0)
            percussion = self._at(analysis.percussive_strengths, index, 0.0)
            downbeat = self._near_downbeat(time, analysis.downbeats)
            lanes = self._assign_lanes(bands, strength, percussion, previous_lane, rule, downbeat, variant, lane_count)
            lanes = [lane for lane in lanes if time - last_by_lane[lane] >= rule.min_gap]
            if not lanes:
                continue
            for lane in lanes:
                source = "downbeat" if downbeat and lane == lane_count // 2 else "onset"
                notes.append(Note(time=time, lane=lane, source=source, strength=strength))
                last_by_lane[lane] = time
                previous_lane = lane

        if rule.allow_dense_patterns:
            self._shape_roll_patterns(notes, analysis, difficulty, lane_count)
        if rule.allow_holds:
            self._add_holds(notes, analysis, rule, lane_count)
        notes = self._cap_chord_frequency(notes, rule.max_chord_ratio)
        notes = self._cap_density(notes, analysis.duration, rule.max_notes_per_second)
        self._spread_lane_load(notes, rule, lane_count, style_targets=style_targets)
        # sustain候補はonset候補とは別経路で加わるため、最後に先頭の助走時間を統一する。
        notes = [note for note in notes if note.time >= START_LEAD_IN_SECONDS]
        chart = Chart(
            version=1,
            music_hash=analysis.music_hash,
            difficulty=difficulty,
            seed=seed,
            song_duration=analysis.duration,
            notes=notes,
            generator_version=self.VERSION,
            metadata={
                "bpm": analysis.bpm,
                "source_path": analysis.source_path,
                "analysis_version": analysis.analyzer_version,
                "algorithm": "hpss-frequency-onset-downbeat-sustain-roll-v2",
                "start_lead_in_seconds": START_LEAD_IN_SECONDS,
                "downbeats": len(analysis.downbeats),
                "local_tempo_points": len(analysis.local_bpms),
                "generation_variant": variant,
                "generation_style": style,
                "generation_style_version": 1,
                "lane_count": lane_count,
                "lane_mode": f"{lane_count}lane",
                "lane_balance": "windowed-load-v2",
                "lane_tuning": "lane-count-v1",
            },
        )
        chart.sort()
        return chart

    @staticmethod
    def _at(values: list[float], index: int, default: float) -> float:
        return float(values[index]) if index < len(values) else default

    @staticmethod
    def _bands_at(analysis: AnalysisResult, index: int) -> list[float]:
        if index < len(analysis.band_energy):
            result = list(analysis.band_energy[index])
            return (result + [0.0] * 5)[:5]
        return [0.0] * 5

    def _select_candidates(self, analysis: AnalysisResult, rule: DifficultyRule) -> list[int]:
        if not analysis.onsets:
            return []
        strengths = np.asarray(analysis.onset_strengths or [0.0] * len(analysis.onsets), dtype=float)
        if len(strengths) < len(analysis.onsets):
            strengths = np.pad(strengths, (0, len(analysis.onsets) - len(strengths)))
        percussion = np.asarray(analysis.percussive_strengths or [0.0] * len(analysis.onsets), dtype=float)
        if len(percussion) < len(analysis.onsets):
            percussion = np.pad(percussion, (0, len(analysis.onsets) - len(percussion)))
        combined = strengths[: len(analysis.onsets)] * 0.70 + percussion[: len(analysis.onsets)] * 0.30
        threshold = float(np.percentile(combined, rule.strength_percentile))
        chosen = [index for index, value in enumerate(combined) if value >= threshold]
        # 初級は拍と小節頭の骨格を必ず残し、上級は音の細部を段階的に追加する。
        if rule is RULES[Difficulty.BEGINNER] and analysis.beats:
            for beat in analysis.beats[::2]:
                nearest = min(range(len(analysis.onsets)), key=lambda i: abs(analysis.onsets[i] - beat))
                if abs(analysis.onsets[nearest] - beat) < 0.13:
                    chosen.append(nearest)
        for downbeat in analysis.downbeats:
            nearest = min(range(len(analysis.onsets)), key=lambda i: abs(analysis.onsets[i] - downbeat))
            if abs(analysis.onsets[nearest] - downbeat) < 0.11:
                chosen.append(nearest)
        return sorted(set(chosen), key=lambda i: analysis.onsets[i])

    @staticmethod
    def _quantize(time: float, beats: list[float], difficulty: Difficulty) -> float:
        """onsetを尊重しつつ、近い拍の細分へだけ寄せる。可変beat間隔にも追従する。"""
        if not beats or difficulty is Difficulty.EXPERT:
            return round(time, 5)
        subdivision = 2 if difficulty in (Difficulty.BEGINNER, Difficulty.EASY) else 4
        candidates: list[float] = []
        for index, beat in enumerate(beats):
            if index + 1 < len(beats):
                interval = beats[index + 1] - beat
            elif index > 0:
                interval = beat - beats[index - 1]
            else:
                interval = 0.5
            for step in range(subdivision):
                candidates.append(beat + interval * step / subdivision)
        nearest = min(candidates, key=lambda candidate: abs(candidate - time))
        local_interval = min((abs(candidate - time) for candidate in beats), default=0.5)
        tolerance = min(0.045, max(0.020, local_interval * 0.35))
        if abs(nearest - time) <= tolerance:
            return round(float(nearest), 5)
        return round(time, 5)

    @staticmethod
    def _near_downbeat(time: float, downbeats: list[float]) -> bool:
        return any(abs(time - downbeat) <= 0.085 for downbeat in downbeats)

    def _assign_lanes(
        self,
        bands: list[float],
        strength: float,
        percussion: float,
        previous_lane: int,
        rule: DifficultyRule,
        downbeat: bool,
        variant: int = 0,
        lane_count: int = 5,
    ) -> list[int]:
        ranked_bands = sorted(range(5), key=lambda band: bands[band], reverse=True)
        center = lane_count // 2
        primary = self._source_band_to_lane(ranked_bands[0], lane_count)
        # 強い広帯域トランジェント、小節頭のリズム、キック・スネアに近い成分は中心レーンを優先する。
        if (percussion >= 0.58 and strength >= 0.42) or (downbeat and percussion >= 0.28):
            primary = center
        elif primary == previous_lane and lane_count > 1:
            direction = -1 if primary > center else 1
            primary = max(0, min(lane_count - 1, primary + direction))

        # 再生成は音価・タイミングを保ち、左右レーンの選択だけを決定論的に切り替える。
        if variant % 2 and primary != center:
            primary = lane_count - 1 - primary

        lanes = [primary]
        max_chord_size = min(rule.max_chord_size, 2 if lane_count == 3 else lane_count)
        if rule.allow_chords:
            for band in ranked_bands:
                candidate = self._source_band_to_lane(band, lane_count)
                if candidate == primary:
                    continue
                separated = abs(candidate - primary) >= (2 if lane_count >= 5 else 1)
                strong_enough = bands[band] >= max(0.12, bands[ranked_bands[0]] * 0.42)
                if separated and strong_enough:
                    lanes.append(candidate)
                if len(lanes) >= max_chord_size:
                    break
        return sorted(set(lanes))

    @staticmethod
    def _source_band_to_lane(source_band: int, lane_count: int) -> int:
        lane_count = normalize_lane_count(lane_count)
        return max(0, min(lane_count - 1, round(int(source_band) * (lane_count - 1) / 4)))

    def _shape_roll_patterns(self, notes: list[Note], analysis: AnalysisResult, difficulty: Difficulty, lane_count: int = 5) -> None:
        """連続onsetを、同一手の無理な反復でなく演奏感のある交互配置へ寄せる。"""
        if difficulty not in (Difficulty.NORMAL, Difficulty.HARD, Difficulty.EXPERT):
            return
        notes.sort(key=lambda note: (note.time, note.lane))
        by_time: dict[float, list[Note]] = {}
        for note in notes:
            by_time.setdefault(round(note.time, 4), []).append(note)
        isolated = [note for note in notes if note.kind is NoteType.TAP and len(by_time[round(note.time, 4)]) == 1]
        if len(isolated) < 3:
            return
        beat_interval = 60.0 / max(analysis.bpm, 1.0)
        run_gap = min(0.22, beat_interval * 0.58)
        start = 0
        while start < len(isolated):
            end = start + 1
            while end < len(isolated) and isolated[end].time - isolated[end - 1].time <= run_gap:
                end += 1
            run = isolated[start:end]
            if len(run) >= 3:
                dominant = max(set(note.lane for note in run), key=lambda lane: sum(note.lane == lane for note in run))
                center = lane_count // 2
                if dominant < center:
                    pattern = (max(0, center - 1), 0)
                elif dominant > center:
                    pattern = (min(lane_count - 1, center + 1), lane_count - 1)
                elif difficulty in (Difficulty.HARD, Difficulty.EXPERT):
                    pattern = (0, center, lane_count - 1, center)
                else:
                    pattern = (center,)
                for index, note in enumerate(run):
                    note.lane = pattern[index % len(pattern)]
                    note.source = "roll"
            start = end

    def _spread_lane_load(self, notes: list[Note], rule: DifficultyRule, lane_count: int = 5, *, style_targets: dict[float, int] | None = None) -> None:
        """直近のレーン使用率を見て、通常ノーツだけを無理なく分散する。

        小節頭・ロール・長押しは音楽的／演奏的な意味を持つため固定する。通常のonsetノーツは、
        1.75秒の時間窓で使用回数が少ないレーンを優先し、同一レーンの連打も避ける。
        """
        if not notes:
            return
        notes.sort(key=lambda note: (note.time, note.lane))
        groups: dict[float, list[Note]] = {}
        for note in notes:
            groups.setdefault(round(note.time, 5), []).append(note)

        window_seconds = 1.75
        recent: list[tuple[float, int]] = []
        total_counts = [0] * lane_count
        last_time_by_lane = [-inf] * lane_count
        previous_lane: int | None = None
        fixed_sources = {"downbeat", "roll", "sustain"}

        for moment in sorted(groups):
            group = groups[moment]
            recent = [(time, lane) for time, lane in recent if moment - time <= window_seconds]
            recent_counts = [sum(1 for _time, lane in recent if lane == target) for target in range(lane_count)]
            used = {note.lane for note in group if note.kind is NoteType.HOLD or note.source in fixed_sources}

            # 音楽的なアンカーは先に確定して、可動ノーツが同時位置へ重ならないようにする。
            for note in group:
                if note.kind is NoteType.HOLD or note.source in fixed_sources:
                    total_counts[note.lane] += 1
                    last_time_by_lane[note.lane] = moment
                    previous_lane = note.lane

            for note in group:
                if note.kind is NoteType.HOLD or note.source in fixed_sources:
                    continue
                original_lane = note.lane
                candidates = [
                    lane
                    for lane in range(lane_count)
                    if lane not in used and moment - last_time_by_lane[lane] >= rule.min_gap
                ]
                if not candidates:
                    # 高密度譜面などで安全な移動先がない場合は、元の配置を尊重する。
                    candidates = [lane for lane in range(lane_count) if lane not in used] or [original_lane]

                def placement_cost(lane: int) -> float:
                    local_load = recent_counts[lane] * 4.4
                    global_load = total_counts[lane] * 0.45
                    distance = abs(lane - original_lane) * 0.65
                    repeat = 2.5 if lane == previous_lane else 0.0
                    target = (style_targets or {}).get(note.time)
                    # Musical affinity is a preference, never an override of playable lanes.
                    affinity = abs(lane - target) * 6.0 if target is not None else 0.0
                    return local_load + global_load + distance + repeat + affinity

                lane = min(candidates, key=placement_cost)
                note.lane = lane
                used.add(lane)
                total_counts[lane] += 1
                last_time_by_lane[lane] = moment
                previous_lane = lane

            recent.extend((moment, note.lane) for note in group)
        notes.sort(key=lambda note: (note.time, note.lane))

    def _add_holds(self, notes: list[Note], analysis: AnalysisResult, rule: DifficultyRule, lane_count: int = 5) -> None:
        occupied: dict[int, list[tuple[float, float]]] = {lane: [] for lane in range(lane_count)}
        for note in notes:
            occupied[note.lane].append((note.time, note.time))
        hold_limit = self._hold_limit(notes, rule.max_hold_ratio)
        added = 0
        segments = sorted(analysis.sustained_segments, key=lambda segment: (segment[1] - segment[0], segment[0]), reverse=True)
        for start, end, natural_lane in segments:
            if added >= hold_limit:
                break
            duration = end - start
            if duration < rule.min_hold_duration:
                continue
            lane = self._source_band_to_lane(int(natural_lane), lane_count)
            hold_start = self._nearest_existing_or_time(notes, start, lane)
            hold_end = min(end, analysis.duration - 0.05)
            if hold_end - hold_start < rule.min_hold_duration:
                continue
            if any(self._overlap((hold_start, hold_end), interval) for interval in occupied[lane]):
                continue
            # 同一手の二重ホールドは禁止。中央は親指として独立扱い。
            center = lane_count // 2
            hand = "left" if lane < center else "right" if lane > center else "center"
            if any(
                note.kind is NoteType.HOLD
                and self._overlap((hold_start, hold_end), (note.time, note.end_time or note.time))
                and ((note.lane < center and hand == "left") or (note.lane > center and hand == "right"))
                for note in notes
            ):
                continue
            # 同じ開始時刻・同じレーンのtapはholdの始点に統合する。
            notes[:] = [
                note
                for note in notes
                if not (note.kind is NoteType.TAP and note.lane == lane and abs(note.time - hold_start) <= 0.03)
            ]
            notes.append(Note(time=round(hold_start, 5), lane=lane, kind=NoteType.HOLD, end_time=round(hold_end, 5), source="sustain", strength=0.6))
            occupied[lane].append((hold_start, hold_end))
            added += 1

    @staticmethod
    def _hold_limit(notes: list[Note], max_hold_ratio: float) -> int:
        if max_hold_ratio <= 0.0:
            return 0
        moments = {round(note.time, 5) for note in notes}
        return max(1, int(len(moments) * max_hold_ratio))

    @staticmethod
    def _nearest_existing_or_time(notes: Iterable[Note], time: float, lane: int) -> float:
        near = [note.time for note in notes if note.lane == lane and abs(note.time - time) <= 0.18]
        return min(near, key=lambda value: abs(value - time)) if near else time

    @staticmethod
    def _overlap(left: tuple[float, float], right: tuple[float, float]) -> bool:
        return max(left[0], right[0]) < min(left[1], right[1])

    @staticmethod
    def _cap_density(notes: list[Note], duration: float, max_nps: float) -> list[Note]:
        if duration <= 0:
            return notes
        limit = max(1, int(duration * max_nps))
        if len(notes) <= limit:
            return notes
        ordered = sorted(notes, key=lambda note: (note.strength, note.kind is NoteType.HOLD), reverse=True)[:limit]
        return sorted(ordered, key=lambda note: (note.time, note.lane))

    @staticmethod
    def _cap_chord_frequency(notes: list[Note], max_chord_ratio: float) -> list[Note]:
        if not notes:
            return notes
        groups: dict[float, list[Note]] = {}
        for note in notes:
            groups.setdefault(round(note.time, 5), []).append(note)
        chord_moments = [time for time, group in groups.items() if len(group) > 1]
        allowed = max(0, int(len(groups) * max(0.0, max_chord_ratio)))
        if len(chord_moments) <= allowed:
            return sorted(notes, key=lambda note: (note.time, note.lane))

        def group_priority(time: float) -> tuple[float, int, int]:
            group = groups[time]
            has_anchor = any(note.kind is NoteType.HOLD or note.source in {"downbeat", "sustain"} for note in group)
            return (max(note.strength for note in group), int(has_anchor), len(group))

        keep_chords = set(sorted(chord_moments, key=group_priority, reverse=True)[:allowed])
        capped: list[Note] = []
        for time in sorted(groups):
            group = groups[time]
            if len(group) <= 1 or time in keep_chords:
                capped.extend(group)
                continue
            capped.append(max(group, key=lambda note: (note.kind is NoteType.HOLD, note.strength, note.source == "downbeat")))
        return sorted(capped, key=lambda note: (note.time, note.lane))
