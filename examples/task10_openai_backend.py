"""Task 10: 同じ判断を OpenAI（gpt-6-luna）経路にやらせる（比較用）。

`common.py` の4つ目のバックエンドとして OpenAI Responses API を使う。
task2〜4 と同じ state・同じ questions を投げ、`common.evaluate()` が
経路の違いを吸収して同じ形の answers を返すことを確かめる。

task5（ollama）との違い:
    task5 は common.py を使わず、ollama に直接 JSON schema を渡す。
    task10 は `common.py` の経路として呼ぶ。経路は OPENAI_API_KEY で
    選ばれる（TYPESAFE / AI_GATEWAY / CLOUDFLARE が無いとき）。

必要なもの:
    OPENAI_API_KEY
    requests（task2〜4 と同じ）

注意:
    ここで得られる数値は OpenAI の自己申告であり、Jev の確率と同じ意味で
    扱ってはいけない。較正は未検証（docs/06 / docs/07 と同じ結論）。
"""

from __future__ import annotations

import os
import time

from common import _ENV_OPENAI_API_KEY, _select_backend, _openai_model, evaluate

# task2 と同じ架空のサンプル。実データは使わない。
STATE = "サービスが急に繋がらなくなりました。至急確認してください。"

# task2〜4 と同じ questions を、まとめて 1 回で聞く。
QUESTIONS = {
    "is_urgent": {
        "type": "noul",
        "instructions": "Does this message report an urgent problem?",
        "criteria": {
            "true": "業務が止まっている、または至急の対応を求める",
            "false": "急ぎではない、または単なる質問",
        },
    },
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
    "severity": {
        "type": "score",
        "instructions": "How harmful is this if left unattended?",
        "criteria": ["影響なし", "軽微", "重大"],
    },
}


def main() -> None:
    backend = _select_backend()
    print(f"選ばれた経路: {backend}")
    if backend != "openai":
        print(
            "OPENAI_API_KEY より優先される経路のキーが設定されている。"
            "task10 を試すには Jev 側の環境変数を外す。"
        )
    print(f"モデル: {_openai_model()}（OpenAI、Jev ではない）")
    print(f"state: {STATE}\n")

    if not os.environ.get(_ENV_OPENAI_API_KEY, "").strip():
        print(f"{_ENV_OPENAI_API_KEY} が無いので呼ばずに終了する。")
        print("このスクリプトは鍵が無い環境では API を叩かない。")
        return

    start = time.monotonic()
    answers = evaluate(STATE, QUESTIONS)
    elapsed = time.monotonic() - start

    for qid, answer in answers.items():
        print(f"{qid}: {answer}")
    print(f"\n所要時間: {elapsed:.1f} 秒")
    print()
    print("これは Jev の answers と同じ形だが、意味は同じではない。")
    print("confidence が確率として較正されているかは、正解ラベル付きで測る。")


if __name__ == "__main__":
    main()
