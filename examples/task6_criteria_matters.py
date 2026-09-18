"""Task 6: 同じ state で、判定基準の書き方だけを変えて比べる。

Task 5 で LLM が数値を返すことは確かめた。ここでは **その数値が
何に依存しているか** を見る。モデルも state も temperature も同じで、
prompt の criteria だけを変える。

Jev は criteria が判断の定義そのものになる。LLM では criteria が
「お願い」になるため、同じ state でも値が動く。

必要なもの:
    ollama（Task 5 と同じ）
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from task5_llm_baseline import MODEL, OLLAMA_URL, SCHEMA, THINK, LlmError

# 3段階の criteria。上から順に詳しくする。
CRITERIA_LEVELS = {
    "なし（数値だけ頼む）": """Judge whether the support message reports an urgent problem.
Return P(urgent) as a number from 0 to 1.""",
    "片側だけ": """Judge whether the support message reports an urgent problem.
Return P(urgent) as a number from 0 to 1.

Criteria:
- urgent (near 1): work is stopped, or the sender explicitly asks
  for immediate action.""",
    "両側を書く": """Judge whether the support message reports an urgent problem.
Return P(urgent) as a number from 0 to 1.

Criteria:
- urgent (near 1): work is stopped, or the sender explicitly asks
  for immediate action.
- not urgent (near 0): a routine request or question that can wait.
  Asking someone to "check" or "confirm" something is not by itself urgent.""",
}

# 緊急度が違う 3 件。架空のサンプル。
CASES = {
    "明確に緊急": "本番が落ちて全顧客が使えません。至急復旧してください。",
    "要確認の依頼": "請求書の金額が間違っています。確認をお願いします。",
    "明確に非緊急": "ドキュメントの誤字を見つけました。お時間あるときに直してください。",
}


def evaluate_with(
    state: str, prompt: str, *, model: str = MODEL, timeout: float = 300.0
) -> float:
    """prompt を差し替えて noul を取る。

    Raises:
        LlmError: 接続失敗、または応答が想定の形でない。
    """
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": f"{prompt}\n\nMessage: {state}"}],
        "stream": False,
        "format": SCHEMA,
        "think": THINK,
        "options": {"temperature": 0},
    }
    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.load(response)
    except urllib.error.URLError as e:
        raise LlmError(f"ollama に接続できない: {e}") from e

    content = body.get("message", {}).get("content", "")
    if not content.strip():
        raise LlmError(
            "応答が空だった。思考モデルなら OLLAMA_THINK=0 を試す"
            "（思考だけで生成が終わることがある）。"
        )
    try:
        value = json.loads(content)
    except ValueError as e:
        raise LlmError(f"応答が JSON でない: {content[:100]!r}") from e

    noul = value.get("noul") if isinstance(value, dict) else None
    if not isinstance(noul, (int, float)):
        raise LlmError(f"noul が数値でない: {content[:100]!r}")
    return float(noul)


def main() -> None:
    print(f"モデル: {MODEL}（temperature=0、JSON schema で形式を固定）")
    print("state は同じ。criteria の書き方だけを変える。\n")

    labels = list(CRITERIA_LEVELS)
    print(f"{'':<14}" + "".join(f"{label:>20}" for label in labels))
    print("-" * (14 + 20 * len(labels)))

    for case_label, state in CASES.items():
        row = f"{case_label:<14}"
        for prompt in CRITERIA_LEVELS.values():
            start = time.monotonic()
            value = evaluate_with(state, prompt)
            elapsed = time.monotonic() - start
            row += f"{f'{value:.2f} ({elapsed:.0f}s)':>20}"
        print(row)

    print()
    print("同じ state でも criteria で値が動く。")
    print("LLM の数値は「基準をどう書いたか」に依存する。")
    print("Jev は criteria が判断の定義になるが、それでも較正の検証は要る。")


if __name__ == "__main__":
    main()
