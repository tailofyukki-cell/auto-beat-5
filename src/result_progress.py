"""Result comparisons and achievable next-rank targets, without save mutations."""
from __future__ import annotations


def comparison_lines(last: dict, chart_key: str, score: int, accuracy: float, misses: int) -> list[str]:
    if last.get("chart_key") != chart_key:
        return ["自己ベスト比較: 記録なし"]
    previous = last.get("previous_best")
    if not previous:
        old_score = int(last.get("previous_best_score", 0))
        return ([f"自己ベスト比 SCORE {score - old_score:+,}", "過去の精度・MISS記録なし"]
                if old_score else ["初回記録！ 次回から自己ベストと比較"])
    lines = [f"自己ベスト比 SCORE {score - int(previous['score']):+,}",
             f"精度 {accuracy - float(previous['accuracy']):+.2f} pt"]
    if "miss_count" in previous:
        lines[-1] += f" / MISS {misses - int(previous['miss_count']):+d}"
    else:
        lines[-1] += " / 過去のMISS記録なし"
    return lines


def next_rank_goal(accuracy: float, misses: int) -> str:
    for threshold, rank in ((70, "C"), (80, "B"), (90, "A"), (95, "S")):
        if accuracy < threshold:
            return f"ランク {rank} まで精度あと {threshold - accuracy:.2f} pt"
    if accuracy < 98:
        return f"S+ まで精度あと {98 - accuracy:.2f} pt・MISS 0"
    if misses:
        return "S+ を目指そう: 精度98%以上で MISS 0"
    if accuracy < 100:
        return f"ALL PERFECT まで精度あと {100 - accuracy:.2f} pt"
    return "ALL PERFECT 達成！ 別の難易度にも挑戦"
