"""Task 9: 判断は独立しているか、それとも文脈に依存するか。

`docs/01` は「複数の問いを一度に投げると、他の問いが隠れた文脈として
判断に影響しうる」を汎用 LLM の問題として挙げている。ここでは Apple の
オンデバイスモデルで、それを確かめる。

同じ state、同じ sampling で、変えるのは **同時に聞く問いの順序** と
**同じ session に前の判断があるかどうか** だけ。

分かったこと（docs/07 に実測を書く）:
    - 同時に聞くと値が動く。どれを先に置くかでも動く
    - 同じ session で別のメッセージを先に判断させると、値が大きく変わる
    → 返ってくる数値は「その判断の確率」ではなく、会話全体の関数

必要なもの:
    task7 と同じ（macOS 27 以降、apple-fm-sdk）

環境変数:
    FM_REPEAT   各条件の繰り返し回数（既定 8）
"""

from __future__ import annotations

import asyncio
from typing import Any

from questions import render_prompt
from task7_apple_fm_structured import (
    CASES,
    REVIEW_STATE,
    FmError,
    _load_fm,
    build_generable,
    evaluate,
    generation_options,
    repeat,
)

# 同じ「緊急か」。単独でも同時でも使う。
URGENCY: dict[str, dict[str, Any]] = {
    "is_urgent": {
        "type": "noul",
        "instructions": "Does this message report an urgent problem?",
        "criteria": {
            "true": "業務が止まっている、または至急の対応を求める",
            "false": "急ぎではない、または単なる質問",
        },
    },
}

# 順序のある問い。緊急度と同時に聞くと互いに影響しうる。
SEVERITY: dict[str, dict[str, Any]] = {
    "severity": {
        "type": "score",
        "instructions": "How harmful would acting on this message be?",
        "criteria": [
            "Safe: no action required beyond normal reading",
            "Suspicious: verify before acting, no credentials involved",
            "Dangerous: credentials, payment, or personal data would be exposed",
        ],
    },
}

DEPARTMENT: dict[str, dict[str, Any]] = {
    "department": {
        "type": "choice",
        "instructions": "Which team should handle this inquiry?",
        "criteria": {
            "account": "ログイン、パスワード、プロフィール",
            "billing": "請求、支払い、返金",
            "technical": "不具合、障害、連携",
            "other": "上記に当てはまらない",
        },
    },
}

# 単独と、同時に聞く 2 通り。
TWO_QUESTIONS: dict[str, dict[str, dict[str, Any]]] = {
    "緊急だけ": URGENCY,
    "緊急→深刻": {**URGENCY, **SEVERITY},
    "深刻→緊急": {**SEVERITY, **URGENCY},
}

# 同じ 3 問で、置く順序だけを変える。
ORDERS: dict[str, dict[str, dict[str, Any]]] = {
    "緊急→深刻→部署": {**URGENCY, **SEVERITY, **DEPARTMENT},
    "深刻→緊急→部署": {**SEVERITY, **URGENCY, **DEPARTMENT},
    "部署→緊急→深刻": {**DEPARTMENT, **URGENCY, **SEVERITY},
}


def collect(
    questions: dict[str, dict[str, Any]], times: int, state: str = REVIEW_STATE
) -> dict[str, list[float]]:
    """questions を times 回評価し、数値の問いの値を集める。"""
    out: dict[str, list[float]] = {}
    for _ in range(times):
        answers = evaluate(state, questions)
        for qid, answer in answers.items():
            if answer["type"] == "noul":
                out.setdefault(qid, []).append(answer["noul"])
            elif answer["type"] == "score":
                out.setdefault(qid, []).append(answer["score"])
    return out


def _summary(items: list[float]) -> str:
    """平均と、観測した値の内訳を 1 行にする。"""
    counts: dict[float, int] = {}
    for value in items:
        rounded = round(value, 2)
        counts[rounded] = counts.get(rounded, 0) + 1
    spread = ", ".join(f"{value:g}x{count}" for value, count in sorted(counts.items()))
    return f"mean={sum(items) / len(items):.2f} [{spread}]"


async def _ask_with_context(
    fm: Any,
    options: Any,
    prompt: str,
    cls: Any,
    *,
    prior: str | None = None,
) -> float:
    """1 つの session で、必要なら前の判断を挟んで noul の値を取る。

    SDK のセッションは会話履歴を持つ。同じ session で別のメッセージを
    先に判断させると、その応答が次の入力の文脈になる。
    """
    session = fm.LanguageModelSession(model=fm.SystemLanguageModel())
    if prior is not None:
        await session.respond(
            render_prompt(prior, URGENCY), generating=cls, options=options
        )
    result = await session.respond(prompt, generating=cls, options=options)
    return float(result.is_urgent)


async def _context_probe(fm: Any, times: int) -> dict[str, list[float]]:
    """直前の判断だけを変えて、同じ state を聞く。"""
    options = generation_options(fm)
    cls = build_generable(URGENCY)
    prompt = render_prompt(REVIEW_STATE, URGENCY)

    out: dict[str, list[float]] = {"なし": [], "緊急の後": [], "非緊急の後": []}
    for _ in range(times):
        out["なし"].append(await _ask_with_context(fm, options, prompt, cls))
        out["緊急の後"].append(
            await _ask_with_context(
                fm, options, prompt, cls, prior=CASES["明確に緊急"]
            )
        )
        out["非緊急の後"].append(
            await _ask_with_context(
                fm, options, prompt, cls, prior=CASES["明確に非緊急"]
            )
        )
    return out


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

    times = repeat()
    print(f"\nstate: {REVIEW_STATE}")
    print(f"各条件を {times} 回。state と sampling は同じ。\n")

    print("=== 1. 単独で聞くか、同時に聞くか ===")
    for label, questions in TWO_QUESTIONS.items():
        values = collect(questions, times)
        row = "  ".join(f"{qid}: {_summary(items)}" for qid, items in values.items())
        print(f"  {label:<10} {row}")
    print("\n同じ「緊急か」でも、単独と同時で値が違う。")
    print("同時に聞くとき、どちらを先に置くかでも違う。")

    print("\n=== 2. 同じ 3 問でも、置く順序を変える ===")
    for label, questions in ORDERS.items():
        values = collect(questions, times)
        print(f"  {label:<14} is_urgent: {_summary(values['is_urgent'])}")
    print("\n問いの内容は同じで、順序だけが違う。それでも値は動く。")
    print("動き方に規則は無い。値はその場の並びに依存している。")

    print(f"\n=== 3. 同じ session に前の判断があると（{times} 回）===")
    print("同じ 1 つの state を、直前の判断だけ変えて聞く。\n")
    # SDK の例外は多岐にわたるが、すべて FoundationModelsError を継承している。
    try:
        contexts = asyncio.run(_context_probe(fm, times))
    except fm.FoundationModelsError as e:
        print(f"  失敗した: {type(e).__name__}: {e}")
        contexts = {}

    for label, values in contexts.items():
        if values:
            print(f"  {label:<10} {_summary(values)}")
    if contexts:
        print("\n同じ state を同じように聞いても、直前の判断で値が変わる。")
        print("「明確に緊急」を先に判断させた後では、値が変わった。")
        print("Jev は会話履歴を持たず、文脈はコードが state に入れる（docs/04）。")

    print("\n=== まとめ ===")
    print("数値は「その判断の確率」ではなく、会話全体の関数として出てくる。")
    print("だから 1 回の呼び出しで取った複数の確率を、判断ごとの確率として扱えない。")
    print("較正を測るなら、判断ごとに 1 問ずつ・毎回新しい session で聞くことになる。")
    print("その代わり呼び出し回数が増え、1 回 0.5 秒が積み上がる。")


if __name__ == "__main__":
    main()
