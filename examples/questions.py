"""Jev の questions を、他のモデルにも渡せるプロンプトに組み替える。

標準ライブラリだけで動く。ネットワークも認証情報も使わない。

`common.py` は Jev に questions をそのまま渡す。汎用 LLM や Apple の
Foundation Models には、同じ questions を**文章にして**渡す必要がある。
その組み替えをここに集める。task5 / task6 は prompt を手で書き分けて
criteria の効き方を見る教材なので、あえてこれを使っていない。
"""

from __future__ import annotations

from typing import Any

_HEADER = "Answer the following questions about the message."


def criteria_lines(question: dict[str, Any]) -> list[str]:
    """criteria を、モデルに読ませる行に開く。

    criteria は型によって形が違う。

    - noul   : `{"true": ..., "false": ...}`。両側を書く（`docs/02`）
    - choice : `{"選択肢": "説明", ...}`
    - score  : `["レベル0", "レベル1", ...]`。順序がある

    **score だけは開かない。** レベルの説明（長い英文）を本文に並べると、
    Apple のモデルはどの入力にも同じレベルを返すようになる。実測では
    3 ケースすべてが 1 になった。score のレベル名は、スキーマの guide に
    短く置く（`task7` の `build_generable`）。
    """
    if question.get("type") == "score":
        return []
    criteria = question.get("criteria")
    if isinstance(criteria, dict):
        return [f"    {key}: {value}" for key, value in criteria.items()]
    if isinstance(criteria, list):
        return [f"    {index}: {value}" for index, value in enumerate(criteria)]
    return []


def render_prompt(state: Any, questions: dict[str, dict[str, Any]]) -> str:
    """state と questions を 1 つのプロンプトにする。

    Jev は state と questions を別々に受け取るが、汎用 LLM は受け取れない。
    だから questions を本文に埋め込み、state を最後に置く。
    """
    lines = [_HEADER, ""]
    for qid, question in questions.items():
        lines.append(f"- {qid}: {question['instructions']}")
        lines.extend(criteria_lines(question))
    lines.extend(["", f"Message: {state}"])
    return "\n".join(lines)


def score_levels(questions: dict[str, dict[str, Any]]) -> dict[str, int]:
    """score 型の問いについて、レベルの最大値を返す。

    スキーマの上限（`range`）を決めるのに使う。
    """
    levels: dict[str, int] = {}
    for qid, question in questions.items():
        if question.get("type") == "score":
            levels[qid] = len(question["criteria"]) - 1
    return levels
