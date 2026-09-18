"""Task 5: 同じ判断を汎用 LLM にやらせる（比較用の基準線）。

このファイルは `common.py` を使わない。Jev ではなく ollama 上の
汎用 LLM に、同じ state と同じ問いを投げる。

Jev（task2〜4）と並べることで、何が同じで何が違うかを見る。
答えを「判断」として使うのではなく、**どこが違うかを観察する**のが目的。

必要なもの:
    ollama が動いていること（http://localhost:11434）
    モデル（既定 gemma4:12b。OLLAMA_MODEL で変えられる）

注意:
    ここで得られる数値は確率として校正されていない。
    Jev の確率と同じ意味で扱ってはいけない。
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434") + "/api/chat"
MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:12b")

# 思考モデル（gemma4:12b など）は長い thinking を返し、推論に数十秒かかる。
# 判断だけを取るなら思考は不要なので既定で切る。実測では eval_count が
# 222 → 10〜12 になり、形式（JSON schema）は think ありのときと同じく守られた。
# 思考を有効にしたい場合は OLLAMA_THINK=1 を設定する。
THINK = os.environ.get("OLLAMA_THINK", "0") in ("1", "true", "yes")

# 架空のサンプル。実データは使わない。
STATE = "サービスが急に繋がらなくなりました。至急確認してください。"

# Jev の noul に相当する問い。JSON schema で形式を縛る。
SCHEMA = {
    "type": "object",
    "properties": {"noul": {"type": "number", "minimum": 0, "maximum": 1}},
    "required": ["noul"],
    "additionalProperties": False,
}

# 判定基準は両側を書く。片側だけだと境界がぶれる。
CRITERIA = """- urgent (near 1): work is stopped, or the sender explicitly asks
  for immediate action.
- not urgent (near 0): a routine request or question that can wait."""

PROMPT = f"""Judge whether the support message reports an urgent problem.
Return P(urgent) as a number from 0 to 1.

Criteria:
{CRITERIA}

Message: {{state}}"""


class LlmError(RuntimeError):
    """LLM 呼び出しの失敗。握りつぶさず呼び出し側に渡す。"""


def evaluate_noul(state: str, *, model: str = MODEL, timeout: float = 300.0) -> float:
    """state が緊急かどうかを確率で返す。

    形式は JSON schema で縛るので、JSON として読めない応答は返らない。
    ただし **値が確率として正しい保証はない**。

    Raises:
        LlmError: ollama に繋がらない、または応答が想定の形でない。
    """
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": PROMPT.format(state=state)}],
        "stream": False,
        "format": SCHEMA,
        "think": THINK,
        # 同じ入力なら同じ答えを返させる。LLM の揺れを消して比較しやすくする。
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
        raise LlmError(
            f"ollama に接続できない（{OLLAMA_URL}）。ollama serve が動いているか、"
            f"モデル {model} があるかを確認する: {e}"
        ) from e

    content = body.get("message", {}).get("content", "")
    if not content.strip():
        # 思考モデルが思考だけで終わり、content を返さないことがある。
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
    print(f"モデル: {MODEL}（ollama、Jev ではない）")
    print(f"state: {STATE}\n")

    start = time.monotonic()
    probability = evaluate_noul(STATE)
    elapsed = time.monotonic() - start

    print(f"緊急である確率（LLM の自己申告）: {probability:.2f}")
    print(f"所要時間: {elapsed:.1f} 秒")
    print()
    print("これは Jev の noul と同じ形だが、意味は同じではない。")
    print("確率として較正されているかは、正解ラベル付きで測る必要がある。")


if __name__ == "__main__":
    main()
