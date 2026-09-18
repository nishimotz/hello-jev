"""Jev (TypeSafe System One Model) を呼ぶ薄いクライアント。

Cloudflare Workers AI 経由で `typesafe/jev` を叩く。

環境変数:
    CLOUDFLARE_ACCOUNT_ID
    CLOUDFLARE_API_TOKEN
"""

from __future__ import annotations

import os
from typing import Any

import requests

DEFAULT_MODEL = "typesafe/jev"
_ENDPOINT = "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run"

# 環境変数名は分割して組み立てる（値そのものは扱わない）
_ENV_ACCOUNT_ID = "CLOUDFLARE_" + "ACCOUNT_ID"
_ENV_API_TOKEN = "CLOUDFLARE_" + "API_TOKEN"


class JevError(RuntimeError):
    """Jev 呼び出しの失敗。握りつぶさず呼び出し側に渡す。"""


def evaluate(
    state: Any,
    questions: dict[str, dict[str, Any]],
    *,
    model: str = DEFAULT_MODEL,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """state と型付きの questions を Jev に評価させ、answers を返す。

    Args:
        state: 判定対象。文字列でも JSON 構造でもよい。
        questions: 質問名をキーにした dict。各値は type / instructions /
            criteria を持つ。
            - noul の criteria: {"true": "...", "false": "..."}
            - choice の criteria: {"選択肢": "説明", ...}
            - score の criteria: ["レベル0", "レベル1", ...]
        model: モデル名。既定は "typesafe/jev"。
        timeout: 秒。

    Returns:
        answers の dict。例:
            {"is_urgent": {"type": "noul", "noul": 0.95}}

    Raises:
        JevError: 認証情報の欠落、HTTP エラー、レスポンス形式の不一致。
    """
    account_id = os.environ.get(_ENV_ACCOUNT_ID, "").strip()
    api_token = os.environ.get(_ENV_API_TOKEN, "").strip()
    if not account_id:
        raise JevError(f"{_ENV_ACCOUNT_ID} が設定されていない")
    if not api_token:
        raise JevError(f"{_ENV_API_TOKEN} が設定されていない")

    payload = {"model": model, "input": {"state": state, "questions": questions}}
    try:
        response = requests.post(
            _ENDPOINT.format(account_id=account_id),
            headers={
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
    except requests.RequestException as e:
        raise JevError(f"接続失敗: {e}") from e

    if response.status_code != 200:
        raise JevError(f"HTTP {response.status_code}: {response.text[:500]}")

    try:
        body = response.json()
    except ValueError as e:
        raise JevError(f"レスポンスが JSON でない: {e}") from e

    return _extract_answers(body)


def _extract_answers(body: dict[str, Any]) -> dict[str, Any]:
    """Cloudflare のレスポンスから answers を取り出す。

    Cloudflare Workers AI は結果を `result` で包むことがある。
    """
    if "answers" in body:
        return body["answers"]
    result = body.get("result")
    if isinstance(result, dict) and "answers" in result:
        return result["answers"]
    raise JevError(f"answers がレスポンスに無い: {list(body)[:10]}")


# --- 確信度の分岐（教材用の例示値。自運用で較正するもの） -----------------

AUTO_THRESHOLD = 0.90
REVIEW_THRESHOLD = 0.60


def route_by_confidence(probability: float) -> str:
    """確率を3段階に振り分ける。

    教材用の例示値であり、自運用の設定値ではない。
    実際の閾値は自分のデータで較正すること。

    Returns:
        "auto" / "review" / "reject" のいずれか。
    """
    if probability >= AUTO_THRESHOLD:
        return "auto"
    if probability >= REVIEW_THRESHOLD:
        return "review"
    return "reject"
