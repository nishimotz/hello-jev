"""Task 8: criteria の書き方と「確率か判断か」で何が変わるか。

Task 7 で、Apple のオンデバイスモデルに確率を出させることはできた。
ここでは **その確率が何に依存しているか** と、**確率で聞くべきか
判断で聞くべきか** を見る。

モデルも state も sampling も固定して、変えるのは criteria の書き方だけ。
task6 が ollama でやったことを、Apple のモデルで確かめる形。

分かったこと（docs/07 に実測を書く）:
    - criteria を書いても、値は「正しい」方向ではなく「別の位置」に動く
    - 確率で聞くと値が散る。帯（urgent / not_urgent）で聞くと安定する
    - 帯には confidence が付かない。確からしさが分からない

必要なもの:
    task7 と同じ（macOS 27 以降、apple-fm-sdk）

環境変数:
    FM_REPEAT   各条件の繰り返し回数（既定 10）
"""

from __future__ import annotations

from typing import Any

from task7_apple_fm_structured import (
    CASES,
    FmError,
    _load_fm,
    criteria_levels,
    evaluate,
    probe_noul,
    repeat,
)

# 同じ問いを、確率ではなく 2 つの帯で答える形にしたもの。
# `choice` として写像すると anyOf になり、定義した 2 語しか返らない。
BAND_QUESTIONS: dict[str, dict[str, Any]] = {
    "is_urgent": {
        "type": "choice",
        "instructions": "Is this message urgent? Choose exactly one.",
        "criteria": {
            "urgent": "業務が止まっている、または至急の対応を求める",
            "not_urgent": "急ぎではない、または単なる質問",
        },
    },
}


def probe_values(
    state: str, questions: dict[str, dict[str, Any]], times: int
) -> list[float]:
    """同じ state を times 回評価し、noul の値の一覧を返す。"""
    return probe_noul(state, times=times, questions=questions)


def bands_for(
    questions: dict[str, dict[str, Any]], *, times: int | None = None
) -> dict[str, dict[str, int]]:
    """3 つの case について、帯を times 回ずつ集計する。"""
    times = times or repeat()
    out: dict[str, dict[str, int]] = {}
    for case, state in CASES.items():
        counts: dict[str, int] = {}
        for _ in range(times):
            answers = evaluate(state, questions)
            band = answers["is_urgent"]["choice"]
            counts[band] = counts.get(band, 0) + 1
        out[case] = counts
    return out


def _summary(values: list[float], width: int) -> str:
    average = sum(values) / len(values)
    span = f"{min(values):.2f}-{max(values):.2f}"
    return f"{f'{average:.2f} ({span})':>{width}}"


def main() -> None:
    try:
        fm = _load_fm()
    except FmError as e:
        print(e)
        return

    available, reason = fm.SystemLanguageModel().is_available()
    print("モデル: Apple Foundation Models（オンデバイス、Jev ではない）")
    print(f"利用可否: {available} {reason or ''}")
    if not available:
        return

    from common import route_by_confidence

    times = repeat()
    print(f"\n=== 1. criteria の書き方で値が動く（{times} 回）===")
    print("state と sampling は同じ。変えるのは criteria だけ。\n")

    levels = criteria_levels()
    width = 24
    print(f"{'':<12}" + "".join(f"{label:>{width}}" for label in levels))
    print("-" * (12 + width * len(levels)))
    for case in CASES:
        row = f"{case:<12}"
        for questions in levels.values():
            values = probe_values(CASES[case], questions, times)
            row += _summary(values, width)
        print(row)
    print("\n各セルは「平均（観測した最小-最大）」。")
    print("criteria を足すと値は動く。ただし動く向きも大きさも一定ではない。")
    print("criteria は正解を教えるのではなく、値の位置を動かしている。")

    print(f"\n=== 2. 確率で聞くか、判断で聞くか（{times} 回）===")
    print("同じ state を、noul（0-1 の数値）と choice（urgent / not_urgent）で聞く。\n")
    floats = probe_values(CASES["要確認の依頼"], levels["両側を書く"], times)
    bands = bands_for(BAND_QUESTIONS, times=times)

    noul_actions = sorted({route_by_confidence(v) for v in floats})
    print(f"state: {CASES['要確認の依頼']}")
    print(f"noul  : {[f'{v:.2f}' for v in floats]}")
    print(f"        観測した幅 {min(floats):.2f}-{max(floats):.2f}、"
          f"閾値で振り分けると {noul_actions}")
    for case, counts in bands.items():
        total = sum(counts.values())
        top = max(counts, key=lambda k: counts[k])
        print(f"band  : {case:<12} {top} {counts[top]}/{total}  {counts}")
    print("\nnoul は同じ入力でも動く。band は同じ答えに落ち着く。")
    print("回数を増やすと noul の幅はさらに広がる（N=20 では 0.00-1.00 まで振れた）。")
    print("0.50 は「確信 50%」ではない。判断が定まらないときの既定の値に見える。")
    print("確率として較正されている証拠にはならない。")

    print("\n=== 3. 帯の一致率は測れる。ただし別のことを測っている ===")
    for case, counts in bands.items():
        total = sum(counts.values())
        top = max(counts, key=lambda k: counts[k])
        agree = counts[top] / total
        print(f"  {case:<12} {top:<11} 一致率 {agree:.2f}（{counts[top]}/{total}）")
    print("\n一致率は「モデルが迷っていないか」を測っている。")
    print("「その答えが正しいか」は測っていない。較正の検証はこれとは別に要る。")
    print("帯は confidence を返さないので、確からしさは複数回の一致率で測ることになる。")
    print(f"1 回 0.5 秒として、{times} 回で {times * 0.5:.1f} 秒。判断 1 つにこれだけかかる。")
    print("（Jev は 1 回で確率と confidence を返す）")


if __name__ == "__main__":
    main()
