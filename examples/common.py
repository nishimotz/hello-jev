"""Jev (TypeSafe System One Model) を呼ぶ薄いクライアント。

経路は 3 つ。上から順に優先する。

1. `TYPESAFE_API_KEY`    TypeSafe 直 API。Cloudflare / Vercel を挟まない
2. `AI_GATEWAY_API_KEY`  Vercel AI Gateway の `typesafe-ai/jev`
3. それ以外               Cloudflare Workers AI の `typesafe/jev`

Vercel と Cloudflare は `noul` / `confidence` の位置が異なるので、
このモジュールで同じ形に正規化してから返す。

環境変数:
    TYPESAFE_API_KEY          これがあれば直 API
    AI_GATEWAY_API_KEY        Vercel AI Gateway 経由（クレジットが必要）
    CLOUDFLARE_ACCOUNT_ID     Cloudflare 経由のとき必要
    CLOUDFLARE_API_TOKEN      Cloudflare 経由のとき必要
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

try:
    import requests
except ImportError:  # Jev を呼ばない教材（task7〜9）でも import できるようにする
    requests = None  # type: ignore[assignment]

if TYPE_CHECKING:
    # 型注釈のためだけに読む。実行時は requests が None でもよい。
    from requests import Response

# Cloudflare Workers AI 経由（Third-party モデル。AI Gateway のクレジットが要る）
_CF_ENDPOINT = "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run"
_CF_MODEL = "typesafe/jev"

# Vercel AI Gateway 経由。モデル名はヘッダで渡す
_VC_ENDPOINT = "https://ai-gateway.vercel.sh/v4/ai/evaluation-model"
_VC_MODEL = "typesafe-ai/jev"
# 実測で確定させた値。欠けると Unsupported gateway protocol version になる
_VC_PROTOCOL_VERSION = "0.0.1"
_VC_SPEC_VERSION = "4"

# TypeSafe 直 API（Cloudflare / Vercel を挟まない）
_TS_ENDPOINT = "https://api.typesafe.ai/v1/systemone"
_TS_MODEL = "jev-latest"

# 環境変数名は分割して組み立てる（値そのものは扱わない）
_ENV_CF_ACCOUNT_ID = "CLOUDFLARE_" + "ACCOUNT_ID"
_ENV_CF_API_TOKEN = "CLOUDFLARE_" + "API_TOKEN"
_ENV_TS_API_KEY = "TYPESAFE_" + "API_KEY"
_ENV_VC_API_KEY = "AI_GATEWAY_" + "API_KEY"


class JevError(RuntimeError):
    """Jev 呼び出しの失敗。握りつぶさず呼び出し側に渡す。"""


def evaluate(
    state: Any,
    questions: dict[str, dict[str, Any]],
    *,
    model: str | None = None,
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
        model: モデル名。省略時は経路ごとの既定（Cloudflare なら
            "typesafe/jev"、Vercel なら "typesafe-ai/jev"、直 API なら
            "jev-latest"）。
        timeout: 秒。

    Returns:
        answers の dict。例:
            {"is_urgent": {"type": "noul", "noul": 0.95}}

    Raises:
        JevError: 認証情報の欠落、HTTP エラー、レスポンス形式の不一致。
    """
    backend = _select_backend()
    if backend == "typesafe":
        return _call_typesafe(state, questions, model or _TS_MODEL, timeout)
    if backend == "vercel":
        return _call_vercel(state, questions, model or _VC_MODEL, timeout)
    return _call_cloudflare(state, questions, model or _CF_MODEL, timeout)


def _select_backend() -> str:
    """どの経路で呼ぶかを決める。

    優先順は TYPESAFE_API_KEY、AI_GATEWAY_API_KEY、Cloudflare の順。
    Cloudflare は環境変数の有無にかかわらず既定として選ばれる。
    """
    if os.environ.get(_ENV_TS_API_KEY, "").strip():
        return "typesafe"
    if os.environ.get(_ENV_VC_API_KEY, "").strip():
        return "vercel"
    return "cloudflare"


def _call_vercel(
    state: Any, questions: dict[str, dict[str, Any]], model: str, timeout: float
) -> dict[str, Any]:
    """Vercel AI Gateway を叩く。

    Cloudflare と違い、モデル名はボディではなくヘッダ `ai-model-id` で渡し、
    ボディは `state` と `questions` を直下に置く（`input` で包まない）。
    質問の型名も `boolean` / `choice` / `score` になる。
    """
    api_key = os.environ.get(_ENV_VC_API_KEY, "").strip()
    if not api_key:
        raise JevError(f"{_ENV_VC_API_KEY} が設定されていない")

    payload = {"state": state, "questions": _to_vercel_questions(questions)}
    response = _post(
        _VC_ENDPOINT,
        {
            "Authorization": f"Bearer {api_key}",
            "ai-model-id": model,
            "ai-gateway-protocol-version": _VC_PROTOCOL_VERSION,
            "ai-evaluation-model-specification-version": _VC_SPEC_VERSION,
            "Content-Type": "application/json",
        },
        payload,
        timeout,
    )
    if response.status_code != 200:
        raise JevError(_format_http_error(response, _VC_ERROR_HINTS))
    return _parse_vercel_answers(response)


def _to_vercel_questions(
    questions: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """質問の型名を Vercel の表記に合わせる。

    教材の他のコードは TypeSafe 本来の `noul` を使うので、経路の違いは
    ここで吸収する。
    """
    out: dict[str, dict[str, Any]] = {}
    for qid, question in questions.items():
        if question.get("type") == "noul":
            out[qid] = {**question, "type": "boolean"}
        else:
            out[qid] = dict(question)
    return out


def _call_typesafe(
    state: Any, questions: dict[str, dict[str, Any]], model: str, timeout: float
) -> dict[str, Any]:
    """TypeSafe 直 API を叩く。"""
    api_key = os.environ.get(_ENV_TS_API_KEY, "").strip()
    if not api_key:
        raise JevError(f"{_ENV_TS_API_KEY} が設定されていない")

    payload = {"state": state, "model": model, "questions": questions}
    response = _post(
        _TS_ENDPOINT,
        {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        payload,
        timeout,
    )
    if response.status_code != 200:
        raise JevError(_format_http_error(response, _TS_ERROR_HINTS))
    return _parse_answers(response)


def _call_cloudflare(
    state: Any, questions: dict[str, dict[str, Any]], model: str, timeout: float
) -> dict[str, Any]:
    """Cloudflare Workers AI を叩く。"""
    account_id = os.environ.get(_ENV_CF_ACCOUNT_ID, "").strip()
    api_token = os.environ.get(_ENV_CF_API_TOKEN, "").strip()
    if not account_id:
        raise JevError(
            f"{_ENV_CF_ACCOUNT_ID} が設定されていない"
            f"（または {_ENV_TS_API_KEY} を設定して直 API を使う）"
        )
    if not api_token:
        raise JevError(
            f"{_ENV_CF_API_TOKEN} が設定されていない"
            f"（または {_ENV_TS_API_KEY} を設定して直 API を使う）"
        )

    payload = {"model": model, "input": {"state": state, "questions": questions}}
    response = _post(
        _CF_ENDPOINT.format(account_id=account_id),
        {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        },
        payload,
        timeout,
    )
    if response.status_code != 200:
        raise JevError(_format_http_error(response, _CF_ERROR_HINTS))
    return _parse_answers(response)


def _post(
    url: str, headers: dict[str, str], payload: dict[str, Any], timeout: float
) -> Response:
    """POST する。接続失敗は JevError に包む。"""
    if requests is None:
        raise JevError(
            "requests が入っていない。Jev を呼ぶには "
            "`uv run --with requests python examples/task2_basic.py` のように "
            "requests を入れて実行する（pip なら requirements.txt から）。"
        )
    try:
        return requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.RequestException as e:
        raise JevError(f"接続失敗: {e}") from e


def _parse_answers(response: Response) -> dict[str, Any]:
    """レスポンスを JSON として読み、answers を取り出す。"""
    try:
        body = response.json()
    except ValueError as e:
        raise JevError(f"レスポンスが JSON でない: {e}") from e
    return _extract_answers(body)


def _parse_vercel_answers(response: Response) -> dict[str, Any]:
    """Vercel のレスポンスを読み、他の経路と同じ形に正規化する。

    Vercel は `probability` と `confidence` の位置が違う。
      - boolean は `noul` ではなく `probability` で返る
      - confidence は answer ではなく
        `providerMetadata.typesafe.confidence[質問名]` に入る
      - score / choice は `confidence` を持たないことがある
    ここで `noul` と `confidence` を補い、呼び出し側の分岐が
    経路を意識しなくて済むようにする。
    """
    try:
        body = response.json()
    except ValueError as e:
        raise JevError(f"レスポンスが JSON でない: {e}") from e

    if "error" in body:
        raise JevError(f"Vercel がエラーを返した: {body['error']}")

    answers = _extract_answers(body)
    confidence = (
        (body.get("providerMetadata") or {}).get("typesafe", {}) or {}
    ).get("confidence") or {}

    normalized: dict[str, Any] = {}
    for qid, answer in answers.items():
        item = dict(answer)
        if item.get("type") == "boolean" and "probability" in item:
            # 教材の他コードに合わせて noul の名前でも読めるようにする
            item.setdefault("noul", item["probability"])
        if item.get("confidence") is None and qid in confidence:
            item["confidence"] = confidence[qid]
        normalized[qid] = item
    return normalized


def _extract_answers(body: dict[str, Any]) -> dict[str, Any]:
    """レスポンスから answers を取り出す。

    TypeSafe 直 API は `answers` を直下に置く。
    Cloudflare Workers AI は `result` で包むことがある。
    """
    if "answers" in body:
        return body["answers"]
    result = body.get("result")
    if isinstance(result, dict) and "answers" in result:
        return result["answers"]
    raise JevError(f"answers がレスポンスに無い: {list(body)[:10]}")


# HTTP エラーのうち、原因が本文から読み取りにくいものに対処を添える。
# 経路によって意味が違うので、ヒントは分けて持つ。
_CF_ERROR_HINTS = {
    401: "認証に失敗した。CLOUDFLARE_API_TOKEN が正しいか、失効していないかを確認する。",
    402: (
        "残高不足。typesafe/jev は Third-party モデルなので、Workers AI の無料枠"
        "（10,000 neurons/日）では呼べない。ダッシュボードの AI > AI Gateway で"
        "「Credits Available」→ Manage → Top-up credits からクレジットを購入する。"
        "Workers Paid プランでは解決しない。BYOK も TypeSafe には非対応。"
        "購入せずに試すなら TYPESAFE_API_KEY を設定して直 API に切り替える。"
    ),
    403: (
        "権限またはプランの不足。トークンに Workers AI の読み取りと編集があるか、"
        "Third-party モデルを呼べる課金設定かを確認する。"
    ),
    429: "レート制限。少し待ってから再試行する。",
}

_TS_ERROR_HINTS = {
    401: "認証に失敗した。TYPESAFE_API_KEY が正しいかを確認する。",
    422: "リクエストが不正。questions の type / instructions / criteria を見直す。",
    429: "レート制限。少し待ってから再試行する。",
    529: "TypeSafe が一時的に混雑している。少し待ってから再試行する。",
}

_VC_ERROR_HINTS = {
    401: "認証に失敗した。AI_GATEWAY_API_KEY を確認する。",
    402: "残高不足。AI Gateway のクレジットを購入する（modal=top-up から）。",
    403: (
        "支払い方法またはモデル権限の問題。カード未登録なら「Add a Card」を"
        "完了させる（無料クレジットの解放にもカード登録が要る）。"
        "モデルが無料枠の対象外なら、クレジットを購入する。"
        "レート制限なら少し待って再試行する。"
    ),
    429: (
        "レート制限。無料枠はモデルごとの上限が低く、連続して呼ぶと当たる。"
        "少し待って再試行するか、クレジットを購入して paid tier に上げる"
        "（制限が外れる）。"
    ),
}


def _format_http_error(
    response: Response, hints: dict[int, str]
) -> str:
    """HTTP エラーを、次に何をすればよいか分かる文字列にする。"""
    body = response.text[:500]
    hint = hints.get(response.status_code)
    if hint:
        return f"HTTP {response.status_code}: {hint} / 応答: {body}"
    return f"HTTP {response.status_code}: {body}"


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
