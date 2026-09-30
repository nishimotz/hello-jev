# 09. Ollama 経路を足す（5つ目のバックエンド）

`common.py` に **Ollama の `/v1/systemone`** を5つ目の経路として足す。
System One モデル（`nimble`）は Jev ではないが、**同じ `state` と同じ
`questions` を TypeSafe 直 API と同じ形で受け取り**、同じ位置（直下の
`answers`）に同じ形で返す。正規化は要らない。呼び出し側（task2〜4）は
経路を意識しない。

**なぜ5つ目なのか。** 優先順は
`typesafe → vercel → cloudflare → openai → ollama`。
Ollama は**鍵が 1 つも無いときの既定**になる。ローカルで完結し、
API キーも課金も要らないので、教材を最初に動かす経路として都合がよい。
Jev 本命のキーがあればそちらが勝つ。

## 実行

```bash
# task11: 同じ state・同じ questions を Ollama 経路で投げる
uv run --with requests python examples/task11_ollama_backend.py
```

前提:

```bash
# Ollama v0.35.0 以降
ollama pull nimble
```

環境変数:

| 変数 | 既定 | 意味 |
|---|---|---|
| `OLLAMA_HOST` | `http://localhost:11434` | 接続先。差し替えられる |
| `OLLAMA_MODEL` | `nimble` | 使うモデル。差し替えられる |

鍵は要らない。Jev 側のキー（`TYPESAFE_*` / `AI_GATEWAY_*` /
`CLOUDFLARE_*`）や `OPENAI_API_KEY` が設定されていると、そちらが優先される。
Ollama を試すときはそれらを外す。

## 公式情報（実装の根拠）

実装は推測で書かず、Ollama 公式ドキュメントに合わせる。

- System One API（`POST /v1/systemone`）
  <https://docs.ollama.com/api/systemone>
- Decision ガイド（choice / noul / score の例）
  <https://docs.ollama.com/capabilities/decision>

確認した事実:

| 項目 | 公式の値 |
|---|---|
| エンドポイント | `POST http://localhost:11434/v1/systemone` |
| 認証 | 不要（ローカル） |
| ボディ | `{model, state, questions}`（TypeSafe 直 API と同じ） |
| 出力の位置 | 直下の `answers`（他経路と同じ） |
| モデル | `nimble`（`ollama pull nimble`） |
| 必要バージョン | Ollama v0.35.0 以降 |
| 制約 | ストリーミング・画像・ツール・生成パラメータは非対応。1 リクエスト 64 KiB 以内 |

`answers` の形は TypeSafe 直 API と同じ（`noul` / `choice` / `score` と
`confidence`）。`_extract_answers` がそのまま読めるので、正規化コードは
足していない。

## 注意

- **Jev ではない。** 返る `confidence` は確率として較正されていない
  （docs/06〜08 と同じ結論）。Jev の確率と同じ意味で閾値に使わない
- 優先順は `typesafe → vercel → cloudflare → openai → ollama`。
  Jev 本命を先に、汎用 LLM は後段、鍵不要のローカルは最後（既定）
- ローカルなので実 API 呼び出しに鍵は要らない。Ollama が起動していることと
  `nimble` を pull 済みであることが条件
- `/v1/systemone` は**文章を生成しない**。判断だけを確率付きで返す
- `input` は 64 KiB 以内。超過は 413 になる。判定対象が大きいときは
  コード側で分割する
