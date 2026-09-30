"""Task 11: 同じ判断をローカルの Ollama（nimble）経路にやらせる。

`common.py` の5つ目のバックエンドとして Ollama の `/v1/systemone` を使う。
task2〜4 と同じ state・同じ questions を投げ、`common.evaluate()` が
経路の違いを吸収して同じ形の answers を返すことを確かめる。

task5（ollama /api/chat）との違い:
    task5 は common.py を使わず、汎用チャット API に JSON schema を渡す。
    task11 は `/v1/systemone`（System One モデル）を common.py の経路として
    呼ぶ。Jev と同じ `{model, state, questions}` をそのまま受ける。

必要なもの:
    Ollama v0.35.0 以降と、`ollama pull nimble` 済みのモデル。
    API キーは要らない（ローカル）。
    この呼び出しは requests を使う（task2〜4 と同じ）。

環境変数:
    OLLAMA_HOST   既定 http://localhost:11434
    OLLAMA_MODEL  既定 nimble

注意:
    得られる確率は Jev の較正済み確率と同じ意味ではない（docs/06〜08 と同じ）。
"""

from __future__ import annotations

import time

from common import _ollama_host, _ollama_model, _select_backend, evaluate

# task2 / task10 と同じ架空のサンプル。実データは使わない。
STATE = "サービスが急に繋がらなくなりました。至急確認してください。"

# task2〜4 / task10 と同じ questions を、まとめて 1 回で聞く。
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
    if backend != "ollama":
        print(
            "Jev か OpenAI のキーが設定されている。"
            "このスクリプトで Ollama を試すには、それらの環境変数を外す。"
        )
    print(f"接続先: {_ollama_host()}/v1/systemone")
    print(f"モデル: {_ollama_model()}（System One、Jev ではない）")
    print(f"state: {STATE}\n")

    start = time.monotonic()
    answers = evaluate(STATE, QUESTIONS)
    elapsed = time.monotonic() - start

    for qid, answer in answers.items():
        print(f"{qid}: {answer}")
    print(f"\n所要時間: {elapsed:.1f} 秒")
    print()
    print("形は Jev の answers と同じだが、確率の意味は同じではない。")
    print("閾値に使う前に、自分のデータで較正する（docs/06〜08）。")


if __name__ == "__main__":
    main()
