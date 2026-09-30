# 08. OpenAI 経路を足す（4つ目のバックエンド）

`common.py` に **OpenAI Responses API** を4つ目の経路として足す。
Jev ではない汎用 LLM だが、同じ `state` と同じ `questions` を渡し、
同じ形の `answers` に正規化して返す。呼び出し側（task2〜4）は経路を
意識しない。

**なぜ4つ目なのか。** 優先順は `typesafe → vercel → cloudflare → openai`。
`OPENAI_API_KEY` は**最後**に判定する。Jev 本命（TypeSafe / Vercel /
Cloudflare）のキーがあればそちらが選ばれる。両方設定しても Jev が勝つ。

## 実行

```bash
# task10: 同じ state・同じ questions を OpenAI 経路で投げる
uv run --with requests python examples/task10_openai_backend.py
```

環境変数:

| 変数 | 既定 | 意味 |
|---|---|---|
| `OPENAI_API_KEY` | （無し） | OpenAI 経由のとき必要。これが最後の経路 |
| `OPENAI_MODEL` | `gpt-6-luna` | 使うモデル。差し替えられる |
| `OPENAI_API_KEY` より優先される経路のキー | | `TYPESAFE_API_KEY` / `AI_GATEWAY_API_KEY` / `CLOUDFLARE_*` があればそちらが選ばれる |

`OPENAI_API_KEY` が無い環境では `task10` は API を叩かず、その旨を表示して
終了する。

## 公式情報（実装の根拠）

実装は推測で書かず、OpenAI 公式ドキュメントに合わせる。

- Responses API（Create a model response、`POST /responses`）
  <https://developers.openai.com/api/reference/resources/responses/methods/create>
- 構造化出力（`text.format`、`type: json_schema`、`strict: true`）
  <https://developers.openai.com/api/docs/guides/structured-outputs>
- モデル `gpt-6-luna`
  <https://developers.openai.com/api/docs/models/gpt-6-luna>

確認した事実:

| 項目 | 公式の値 |
|---|---|
| エンドポイント | `POST https://api.openai.com/v1/responses` |
| 認証 | `Authorization: Bearer $OPENAI_API_KEY` |
| 入力 | `input`（文字列、または role/content のメッセージ配列） |
| 構造化出力 | `text.format = {type: "json_schema", name, strict: true, schema}` |
| 出力の取り出し | `output[].content[].text`（JSON 文字列が入る） |
| `gpt-6-luna` の存在 | **存在する**（Model ID `gpt-6-luna`、Responses / Chat Completions 両対応） |

`gpt-6-luna` は公式に存在する。既定はこのモデル名で、`OPENAI_MODEL` で
差し替えられるようにしてある（モデルが変わっても実装は変えずに済む）。

## 経路ごとの違い（実装が吸収する分）

`common.py` が違いを吸収するので、教材のコードは経路を意識しなくてよい。

| | OpenAI | Vercel | Cloudflare | TypeSafe 直 |
|---|---|---|---|---|
| モデル名 | `gpt-6-luna` | `typesafe-ai/jev` | `typesafe/jev` | `jev-latest` |
| エンドポイント | `/v1/responses` | `/v4/ai/evaluation-model` | `/ai/run` | `/v1/systemone` |
| ボディ | `{model, input, text, reasoning}` | `{state, questions}` | `{model, input:{...}}` | `{model, state, questions}` |
| 形式の縛り | `text.format`（json_schema） | モデル側 | モデル側 | モデル側 |
| 出力の位置 | `output[].content[].text` | 直下の answers | `result.answers` | 直下の answers |
| boolean の答え | `answer`（数値に正規化） | `probability` | `noul` | `noul` |
| confidence | `answer` と同じ階層 | `providerMetadata.typesafe` | answer 内 | answer 内 |

## 正規化の形

`_call_openai()` は次の形に正規化する（他の経路と同じ）。

```
{"質問名": {"type": "noul"|"choice"|"score",
            "noul"|"choice"|"score": 値,
            "confidence": 0〜1}}
```

構造化出力の schema は、問い名ごとに `{answer, confidence}` を要求する。
`choice` は `enum` で取り得る値を縛り、`score` は `0〜最大レベル` に縛る。

## 注意

- **Jev ではない。** 返る `confidence` は確率として較正されていない
  （docs/06 / docs/07 と同じ結論）。Jev の確率と同じ意味で閾値に使わない
- 優先順は `typesafe → vercel → cloudflare → openai`。Jev 本命を先に置く
- 実際の API 呼び出しは鍵が要る。鍵が無い環境では呼ばずに終了する
