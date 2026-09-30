"""Jev (TypeSafe System One Model) を呼ぶ薄いクライアント。

経路は 5 つ。上から順に優先する。

1. `TYPESAFE_API_KEY`    TypeSafe 直 API。Cloudflare / Vercel を挟まない
2. `AI_GATEWAY_API_KEY`  Vercel AI Gateway の `typesafe-ai/jev`
3. `CLOUDFLARE_*`        Cloudflare Workers AI の `typesafe/jev`
4. `OPENAI_API_KEY`      OpenAI Responses API（汎用 LLM。Jev ではない）
5. `OLLAMA_HOST`         Ollama の `/v1/systemone`（ローカル。鍵不要）。
                         既定の経路。`nimble` は Jev ではない

Vercel / Cloudflare / OpenAI は `noul` / `confidence` の位置が異なるので、
このモジュールで同じ形に正規化してから返す。

環境変数:
    TYPESAFE_API_KEY          これがあれば直 API
    AI_GATEWAY_API_KEY        Vercel AI Gateway 経由（クレジットが必要）
    CLOUDFLARE_ACCOUNT_ID     Cloudflare 経由のとき必要
    CLOUDFLARE_API_TOKEN      Cloudflare 経由のとき必要
    OPENAI_API_KEY            OpenAI 経由のとき必要
    OPENAI_MODEL              OpenAI のモデル名（既定 gpt-6-luna）
    OLLAMA_HOST               Ollama の URL（既定 http://localhost:11434）
    OLLAMA_MODEL              Ollama のモデル名（既定 nimble）

経路の優先順は、Jev 本命（TypeSafe / Vercel / Cloudflare）を OpenAI より
先に置く。OPENAI_API_KEY は最後に判定するので、両方設定しても Jev が勝つ。
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

# OpenAI Responses API（汎用 LLM。Jev ではない）
# 出典: https://developers.openai.com/api/reference/resources/responses/methods/create
# 構造化出力は text.format（type=json_schema, strict=true）。
# 出力は output[].content[].text に JSON 文字列で入る。
_OPENAI_ENDPOINT = "https://api.openai.com/v1/responses"
_OPENAI_MODEL = "gpt-6-luna"
# 構造化出力の format 名。任意の識別子でよい。
_OPENAI_FORMAT_NAME = "jev_answers"
# reasoning を切って出力を決定的にする（gpt-6-luna は none を受理する）。
_OPENAI_REASONING_EFFORT = "none"

# 環境変数名は分割して組み立てる（値そのものは扱わない）
_ENV_CF_ACCOUNT_ID = "CLOUDFLARE_" + "ACCOUNT_ID"
_ENV_CF_API_TOKEN = "CLOUDFLARE_" + "API_TOKEN"
_ENV_TS_API_KEY = "TYPESAFE_" + "API_KEY"
_ENV_VC_API_KEY = "AI_GATEWAY_" + "API_KEY"
_ENV_OPENAI_API_KEY = "OPENAI_" + "API_KEY"
_ENV_OPENAI_MODEL = "OPENAI_" + "MODEL"

# Ollama の /v1/systemone（System One モデル）。ローカルなので鍵は要らない。
# 出典: https://docs.ollama.com/api/systemone
#   - POST /v1/systemone、ボディは {model, state, questions}
#   - 出力は直下の answers。他の Jev 経路と同じ形（確率・confidence 付き）
#   - ストリーミング・画像・ツール・生成パラメータは非対応
_OLLAMA_HOST = "http://localhost:11434"
_OLLAMA_MODEL = "nimble"
_ENV_OLLAMA_HOST = "OLLAMA_" + "HOST"
_ENV_OLLAMA_MODEL = "OLLAMA_" + "MODEL"


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
    if backend == "openai":
        return _call_openai(state, questions, model or _openai_model(), timeout)
    if backend == "ollama":
        return _call_ollama(state, questions, model or _ollama_model(), timeout)
    return _call_cloudflare(state, questions, model or _CF_MODEL, timeout)


def _select_backend() -> str:
    """どの経路で呼ぶかを決める。

    優先順は TYPESAFE_API_KEY、AI_GATEWAY_API_KEY、CLOUDFLARE_*、
    OPENAI_API_KEY の順。キーが 1 つも無ければローカルの Ollama
    （/v1/systemone、鍵不要）を既定にする。Jev 本命のキーが設定されて
    いれば、OpenAI よりも Ollama よりも Jev が選ばれる。
    """
    if os.environ.get(_ENV_TS_API_KEY, "").strip():
        return "typesafe"
    if os.environ.get(_ENV_VC_API_KEY, "").strip():
        return "vercel"
    if (
        os.environ.get(_ENV_CF_ACCOUNT_ID, "").strip()
        and os.environ.get(_ENV_CF_API_TOKEN, "").strip()
    ):
        return "cloudflare"
    if os.environ.get(_ENV_OPENAI_API_KEY, "").strip():
        return "openai"
    # 最後はローカルの Ollama（/v1/systemone）。鍵不要なので既定になる。
    return "ollama"


def _openai_model() -> str:
    """OpenAI のモデル名を決める。OPENAI_MODEL で差し替えられる。"""
    return os.environ.get(_ENV_OPENAI_MODEL, "").strip() or _OPENAI_MODEL


def _ollama_host() -> str:
    """Ollama の URL を決める。OLLAMA_HOST で差し替えられる。"""
    return os.environ.get(_ENV_OLLAMA_HOST, "").strip() or _OLLAMA_HOST


def _ollama_model() -> str:
    """Ollama のモデル名を決める。OLLAMA_MODEL で差し替えられる。"""
    return os.environ.get(_ENV_OLLAMA_MODEL, "").strip() or _OLLAMA_MODEL


def _call_ollama(
    state: Any, questions: dict[str, dict[str, Any]], model: str, timeout: float
) -> dict[str, Any]:
    """Ollama の /v1/systemone を叩く。

    System One は TypeSafe 直 API と同じ `{model, state, questions}` を受け、
    同じ位置（直下の answers）に同じ形で返す。他経路のような正規化は要らない
    （`_extract_answers` がそのまま読める）。

    鍵は要らない。既定の接続先はローカルの Ollama。
    """
    url = _ollama_host().rstrip("/") + "/v1/systemone"
    payload = {"model": model, "state": state, "questions": questions}
    response = _post(url, {"Content-Type": "application/json"}, payload, timeout)
    if response.status_code != 200:
        raise JevError(_format_http_error(response, _OLLAMA_ERROR_HINTS))
    return _parse_answers(response)


def _call_openai(
    state: Any, questions: dict[str, dict[str, Any]], model: str, timeout: float
) -> dict[str, Any]:
    """OpenAI Responses API を叩く。

    Jev ではない汎用 LLM 経路。同じ state と同じ問いを渡し、answers を
    他の経路と同じ形に正規化して返す。

    エンドポイント・payload・応答形式は OpenAI 公式ドキュメントに合わせる。
    - POST https://api.openai.com/v1/responses
    - 入力は `input`（文字列または message の配列）
    - 構造化出力は `text.format`（type=json_schema, strict=true）
    - 出力は `output[].content[].text` に JSON 文字列で入る
    """
    api_key = os.environ.get(_ENV_OPENAI_API_KEY, "").strip()
    if not api_key:
        raise JevError(f"{_ENV_OPENAI_API_KEY} が設定されていない")

    payload = {
        "model": model,
        "input": [
            {"role": "developer", "content": _OPENAI_INSTRUCTIONS},
            {"role": "user", "content": _openai_input(state, questions)},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": _OPENAI_FORMAT_NAME,
                "strict": True,
                "schema": _openai_schema(questions),
            }
        },
        "reasoning": {"effort": _OPENAI_REASONING_EFFORT},
    }
    response = _post(
        _OPENAI_ENDPOINT,
        {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        payload,
        timeout,
    )
    if response.status_code != 200:
        raise JevError(_format_http_error(response, _OPENAI_ERROR_HINTS))
    return _parse_openai_answers(response, questions)


# 構造化出力でモデルに守らせる指示。
# 確率の意味は Jev と似せるが、較正されていない点は task10 / docs で述べる。
_OPENAI_INSTRUCTIONS = (
    "You are answering typed judgment questions about a message. "
    "Return only the JSON object that matches the given schema."
)


def _openai_input(state: Any, questions: dict[str, dict[str, Any]]) -> str:
    """state と questions を 1 つの入力文にする。

    汎用 LLM は Jev のように state と questions を別々に受け取れないので、
    質問を本文に開き、state を最後に置く（questions.py と同じ考え方）。
    """
    lines = ["Answer the following questions about the message.", ""]
    for qid, question in questions.items():
        lines.append(f"- {qid}: {question.get('instructions', '')}")
        criteria = question.get("criteria")
        if isinstance(criteria, dict):
            for key, value in criteria.items():
                lines.append(f"    {key}: {value}")
        elif isinstance(criteria, list):
            for index, value in enumerate(criteria):
                lines.append(f"    {index}: {value}")
    lines.extend(["", f"Message: {state}"])
    return "\n".join(lines)


def _openai_schema(questions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """構造化出力用の JSON schema を組み立てる。

    問い名ごとに答えと confidence（0〜1）を持たせる。
    choice は取り得る値を enum で縛る。score は 0〜最大レベルに縛る。
    """
    properties: dict[str, Any] = {}
    required: list[str] = []
    for qid, question in questions.items():
        qtype = question.get("type")
        answer: dict[str, Any]
        if qtype == "noul":
            answer = {"type": "number"}
        elif qtype == "choice":
            criteria = question.get("criteria") or {}
            values = list(criteria) if isinstance(criteria, dict) else []
            answer = {"type": "string"}
            if values:
                answer["enum"] = values
        elif qtype == "score":
            criteria = question.get("criteria") or []
            max_level = max(len(criteria) - 1, 0)
            answer = {"type": "number", "minimum": 0, "maximum": max_level}
        else:
            # 未知の型は黙って通さない
            raise JevError(f"未知の質問型: {qtype!r}（{qid}）")
        answer["description"] = question.get("instructions", "")
        properties[qid] = {
            "type": "object",
            "properties": {
                "answer": answer,
                "confidence": {"type": "number"},
            },
            "required": ["answer", "confidence"],
            "additionalProperties": False,
        }
        required.append(qid)
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _parse_openai_answers(
    response: Response, questions: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """OpenAI のレスポンスを読み、他の経路と同じ形に正規化する。

    Responses API の出力は output[].content[].text に JSON 文字列で入る。
    中身は {問い名: {answer, confidence}} なので、Jev の
    {問い名: {type, noul/score/choice, confidence}} に写す。
    """
    try:
        body = response.json()
    except ValueError as e:
        raise JevError(f"レスポンスが JSON でない: {e}") from e

    if body.get("error"):
        raise JevError(f"OpenAI がエラーを返した: {body['error']}")

    text = _openai_output_text(body)
    if not text:
        raise JevError(
            "Responses API の出力本文が空だった（output[].content[].text）"
        )
    import json as _json

    try:
        parsed = _json.loads(text)
    except ValueError as e:
        raise JevError(f"出力が JSON でない: {text[:100]!r}") from e
    if not isinstance(parsed, dict):
        raise JevError(f"出力が object でない: {text[:100]!r}")

    normalized: dict[str, Any] = {}
    for qid, question in questions.items():
        item = parsed.get(qid)
        if not isinstance(item, dict):
            raise JevError(f"{qid} が出力に無い: {list(parsed)}")
        qtype = question.get("type")
        answer = item.get("answer")
        out: dict[str, Any] = {"type": qtype}
        if qtype == "noul":
            out["noul"] = _as_float(answer)
        elif qtype == "score":
            out["score"] = _as_float(answer)
        elif qtype == "choice":
            out["choice"] = answer
        if item.get("confidence") is not None:
            out["confidence"] = _as_float(item["confidence"])
        normalized[qid] = out
    return normalized


def _openai_output_text(body: dict[str, Any]) -> str:
    """Responses API の output から output_text を集める。"""
    chunks: list[str] = []
    for item in body.get("output") or []:
        if item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if part.get("type") == "output_text" and isinstance(
                part.get("text"), str
            ):
                chunks.append(part["text"])
    return "".join(chunks)


def _as_float(value: Any) -> float:
    """数値を float に矯正する。数値でなければエラーにする。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise JevError(f"数値でない値: {value!r}")
    return float(value)


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

_OPENAI_ERROR_HINTS = {
    401: (
        "認証に失敗した。OPENAI_API_KEY が正しいか、失効していないかを確認する。"
    ),
    403: "このモデルまたは機能への権限がない。OPENAI_MODEL を確認する。",
    404: "モデル名またはエンドポイントが無い。OPENAI_MODEL の値を確認する。",
    429: (
        "レート制限または残高不足。少し待って再試行するか、"
        "OpenAI の使用量・残高を確認する。"
    ),
}

_OLLAMA_ERROR_HINTS = {
    404: (
        "エンドポイントまたはモデルが無い。Ollama v0.35.0 以降か、"
        "`ollama pull nimble` 済みかを確認する。"
    ),
    405: "メソッドが合わない。/v1/systemone への POST か確認する。",
    413: "リクエストが大きすぎる（上限 64 KiB）。state を分割する。",
    422: "リクエストが不正。questions の type / instructions / criteria を見直す。",
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
