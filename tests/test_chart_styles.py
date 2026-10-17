import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from chart_generator import ChartGenerator, RULES
from chart_validator import ChartValidator
from models import Chart, Difficulty
from test_chart_summary import fixture_analysis


class ChartStyleTests(unittest.TestCase):
    def analysis(self):
        analysis = fixture_analysis()
        analysis.duration = 34.0
        analysis.onsets = [2 + i * 0.5 for i in range(60)]
        analysis.onset_strengths = [0.8] * 60
        analysis.percussive_strengths = [0.4] * 60
        analysis.band_energy = [[0.7, 0.2, 0.05, 0.03, 0.02]] * 60
        analysis.beats = []
        analysis.sustained_segments = []
        return analysis

    def test_frequency_keeps_dominant_band_despite_percussion_and_variant(self):
        analysis = self.analysis()
        analysis.percussive_strengths = [1.0] * len(analysis.onsets)
        analysis.downbeats = list(analysis.onsets)
        for count in (3, 5, 7):
            for band in range(5):
                analysis.band_energy = [[1.0 if i == band else 0.0 for i in range(5)]] * len(analysis.onsets)
                charts = [ChartGenerator().generate(analysis, Difficulty.EXPERT, lane_count=count,
                          variant=variant, style="frequency") for variant in (0, 1, 2)]
                expected = ChartGenerator._source_band_to_lane(band, count)
                self.assertTrue(charts[0].notes)
                self.assertEqual({n.lane for n in charts[0].notes}, {expected})
                signature = lambda c: [(n.time, n.lane, n.kind, n.end_time) for n in c.notes]
                self.assertEqual(signature(charts[0]), signature(charts[1]))
                self.assertEqual(signature(charts[0]), signature(charts[2]))

    def test_frequency_does_not_use_percussion_to_select_events_or_fill_gaps(self):
        from chart_balance import balance_chart
        analysis = self.analysis()
        analysis.onset_strengths = [0.2, 0.8, 0.4] * 20
        first = ChartGenerator().generate(analysis, Difficulty.NORMAL, style="frequency")
        analysis.percussive_strengths = [0.0, 1.0, 0.9] * 20
        second = ChartGenerator().generate(analysis, Difficulty.NORMAL, style="frequency")
        self.assertEqual(first.to_dict(), second.to_dict())
        before = first.to_dict()
        self.assertEqual(balance_chart(first, analysis), 0)
        self.assertEqual(before, first.to_dict())
        self.assertEqual(first.metadata['lane_balance'], 'none')

    def test_frequency_without_band_energy_does_not_invent_taps(self):
        analysis = self.analysis()
        analysis.band_energy = []
        chart = ChartGenerator().generate(analysis, Difficulty.EXPERT, style="frequency")
        self.assertEqual(chart.notes, [])

    def test_frequency_chord_thinning_keeps_strongest_high_band(self):
        analysis = self.analysis()
        analysis.band_energy = [[0.6, 0, 0, 0, 1.0]] * len(analysis.onsets)
        chart = ChartGenerator().generate(analysis, Difficulty.NORMAL, style="frequency")
        groups = {}
        for note in chart.notes:
            groups.setdefault(note.time, []).append(note)
        singles = [notes[0] for notes in groups.values() if len(notes) == 1]
        self.assertTrue(singles)
        self.assertEqual({note.lane for note in singles}, {4})

    def test_initial_standard_and_repeated_style_rotation(self):
        analysis = self.analysis()
        self.assertEqual([ChartGenerator.candidate_style(analysis, i) for i in range(7)],
                         ["standard", "bass", "rhythm", "standard", "bass", "rhythm", "standard"])
        analysis.band_energy = []
        analysis.percussive_strengths = []
        self.assertTrue(all(ChartGenerator.candidate_style(analysis, i) == "standard" for i in range(8)))
        analysis.onsets = []
        self.assertEqual(ChartGenerator.candidate_style(analysis, 1), "standard")

    def test_style_affinity_preserves_times_and_is_deterministic(self):
        analysis = self.analysis()
        generator = ChartGenerator()
        for lanes in (3, 5, 7):
            standard = generator.generate(analysis, Difficulty.EASY, lane_count=lanes)
            for style in ("bass", "rhythm"):
                chart = generator.generate(analysis, Difficulty.EASY, lane_count=lanes, style=style)
                self.assertEqual([n.time for n in chart.notes], [n.time for n in standard.notes])
                target = lanes // 2 - 1 if style == "bass" else lanes // 2
                self.assertLess(sum(abs(n.lane-target) for n in chart.notes), sum(abs(n.lane-target) for n in standard.notes))
                self.assertEqual(chart.to_dict(), generator.generate(analysis, Difficulty.EASY, lane_count=lanes, style=style).to_dict())
                self.assertEqual(Chart.from_dict(chart.to_dict()).metadata["generation_style"], style)

    def test_all_styles_use_existing_safety_validation(self):
        generator = ChartGenerator()
        for lanes in (3, 5, 7):
            for difficulty in Difficulty:
                for style in ("standard", "bass", "rhythm", "frequency"):
                    with self.subTest(lanes=lanes, difficulty=difficulty, style=style):
                        chart = generator.generate(fixture_analysis(), difficulty, lane_count=lanes, style=style)
                        ChartValidator().validate(chart)
                        self.assertTrue(all(0 <= n.lane < lanes and n.time >= 1.2 for n in chart.notes))
                        last = {}
                        for note in chart.notes:
                            self.assertGreaterEqual(note.time-last.get(note.lane, -100), RULES[difficulty].min_gap-1e-8)
                            last[note.lane] = note.time


if __name__ == "__main__":
    unittest.main()
