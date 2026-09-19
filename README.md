# hello-jev

「かしこい選択だけを行う AI」を組み合わせて、高信頼なシステムを作れるか。
その仮説を手を動かして確かめる Python チュートリアル。

## 何を学ぶか

汎用 LLM に文章を書かせるのではなく、**判断・選択に特化したモデル**を使う。
判断だけを型付きで取り出し、コード側で組み合わせる。確信度で自動実行と人間レビューを分ける。

題材は TypeSafe の Jev（System One Model）。

## 前提

- Jev は**文章を生成しない**。`noul` / `choice` / `score` の3種類の問いに、確率付きで答えるだけ
- 入力はテキストのみ（画像は不可）
- 会話履歴を持たない。文脈はコードが `state` に入れる

## 依存関係

Jev の呼び出し（`examples/common.py`）は `requests` を使う。

| タスク | 必要なもの |
|---|---|
| `task2` 〜 `task4`（Jev） | `requests` |
| `task5` / `task6`（ollama） | 標準ライブラリのみ。`requests` 不要 |
| `task7` 〜 `task9`（Apple FM） | `apple-fm-sdk` と macOS 27 以降。`requests` 不要 |
| テスト | `pytest` のみ。`requests` も SDK も無くてよい |

**uv を使う場合**は、その場で入れて実行できる。仮想環境は不要。

```bash
uv run --with requests python examples/task2_basic.py
uv run --with apple-fm-sdk python examples/task7_apple_fm_structured.py
uv run --with pytest pytest tests/ -q
```

**uv を使わない場合**は `requirements.txt` から入れる。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python examples/task2_basic.py
pytest tests/ -q
```

`task5` / `task6` は `requests` を使わないので、どちらの方法でもよく、
素の `python3` でも動く。

`task7` 〜 `task9` は macOS 27 以降で、Apple Intelligence が有効な必要がある。
モデルは OS に付いてくるので、API キーも課金も要らない。

**SDK のパッケージ情報は「macOS 26.0+」と書いているが、実際に要るのは 27。**
SDK 自身のコードが `macOS 27 SDK` に言及しており、`libFoundationModels.dylib`
も macOS 27 SDK でビルドされている。26 では動かない前提で扱う（`docs/07`）。

```bash
pip install apple-fm-sdk          # uv なら --with apple-fm-sdk で足りる
uv run --with apple-fm-sdk python examples/task7_apple_fm_structured.py
```

## セットアップ

Jev の呼び出し経路は 3 つ。上から順に優先される。

| 経路 | 必要なもの | 課金 |
|---|---|---|
| **TypeSafe 直 API** | `TYPESAFE_API_KEY` | Cloudflare / Vercel を挟まない |
| **Vercel AI Gateway** | `AI_GATEWAY_API_KEY` | クレジット制（月の無料枠あり。カード登録が前提） |
| Cloudflare Workers AI | `CLOUDFLARE_ACCOUNT_ID` + `CLOUDFLARE_API_TOKEN` | Third-party モデルのため無料枠外。402 で止まる |

**Vercel が実用的な選択肢。** キーは AI Gateway の API Keys ページで発行する。
Jev は無料枠モデルの一覧に含まれている。

### 認証情報の渡し方

**`.envrc` を使う場合（推奨）**

秘密はリポジトリの外に置く。`.envrc` 自体には秘密を書かないのでコミットしてよい。

```bash
mkdir -p ~/.config/hello-jev
cp env.example ~/.config/hello-jev/env
chmod 600 ~/.config/hello-jev/env
$EDITOR ~/.config/hello-jev/env   # 使う経路の値を埋める
direnv allow                      # リポジトリ直下で 1 回だけ
```

これ以降はシェルに入るだけで環境変数が入る。1Password に保管したい場合は
`.envrc` 内の `op read` の行を有効にして、`~/.config/hello-jev/env` の行を消す。

**環境変数を直接 export する場合**

```bash
export AI_GATEWAY_API_KEY=...
uv run --with requests python examples/task2_basic.py
```

`examples/common.py` は環境変数を直接読むだけで `.env` は読まない。
リポジトリ内の `.env` を読ませたい場合は `.envrc` を `dotenv_if_exists .env` に変える。

### Vercel で使う手順

1. [AI Gateway の API Keys](https://vercel.com/d?to=%2F%5Bteam%5D%2F%7E%2Fai-gateway%2Fapi-keys) でキーを作り、`AI_GATEWAY_API_KEY` に入れる
2. **カードを登録する。** 無料クレジットの解放にもカード登録が要る。クレジットが `$0` のまま
   呼ぶと `403 customer_verification_required` になる。
   カードの登録は **AI Gateway のクレジット用モーダル**（`.../ai?modal=top-up`）から行う。
   Settings → Billing や Pro アップグレード（$20/月）ではない点に注意。
   Pro は不要。
3. クレジットを最小額だけ購入してもよい。Jev は $42/Btok（1回 約 $0.000014）なので、
   $5 で約35万回分。購入すると paid tier になり、毎月の無料クレジットは適用外になる
   （購入クレジットは1年で失効）
4. 無料で挙動を見たいだけなら [Playground](https://console.typesafe.ai/playground) が早い

**無料枠にはレート制限がある。** モデルごとの上限が低く、連続して呼ぶと `429` になる。
教材の実行（1回）は問題ないが、較正のようにまとめて回すならクレジットを購入して
paid tier に上げると制限が外れる。

### 経路ごとの違い（実装が吸収する分）

`common.py` が違いを吸収するので、教材のコードは経路を意識しなくてよい。

| | Vercel | Cloudflare | TypeSafe 直 |
|---|---|---|---|
| モデル名 | `typesafe-ai/jev` | `typesafe/jev` | `jev-latest` |
| モデルの渡し方 | ヘッダ `ai-model-id` | ボディ | ボディ |
| ボディ | `{state, questions}` | `{model, input:{...}}` | `{model, state, questions}` |
| boolean の型名 | `boolean` | `noul` | `noul` |
| boolean の答え | `probability` | `noul` | `noul` |
| confidence の位置 | `providerMetadata.typesafe` | answer 内 | answer 内 |

Vercel 経由では `probability` と `noul` の両方、および補った `confidence` が返る。

### 実行

```bash
uv run --with requests python examples/task2_basic.py
```

## 汎用 LLM と比べる

同じ判断を、汎用 LLM（ollama）と Apple のオンデバイスモデルの両方にやらせて、
Jev と並べる。API キーは不要で、ネットワークも使わない。

```bash
# ollama 上の汎用 LLM
python3 examples/task5_llm_baseline.py     # LLM に確率を出させる
python3 examples/task6_criteria_matters.py # criteria の書き方で値が変わる

# Apple Intelligence のオンデバイスモデル（macOS 27 以降）
uv run --with apple-fm-sdk python examples/task7_apple_fm_structured.py
uv run --with apple-fm-sdk python examples/task8_fm_criteria.py
uv run --with apple-fm-sdk python examples/task9_fm_independence.py
```

ollama の既定のモデルは `gemma4:12b`。`OLLAMA_MODEL` で変えられる。
思考モデルは既定で思考を切る（`OLLAMA_THINK=1` で有効）。

**Apple のモデルは構造化出力を持つ。** `@fm.generable` と `fm.guide()` で
スキーマを定義すると、Jev の `noul` / `choice` / `score` をそのまま写像できる。
`task7` は task2〜4 の `questions` を書き換えずに渡す。

`FM_REPEAT` で繰り返し回数を変えられる。**値を 1 回だけ見ると気づけない**ので、
増やして確かめること。

実測した内容と限界は `docs/06-llm-baseline.md` と `docs/07-apple-fm.md` にある。
**どちらも1環境の観測であり、一般則ではない。**

要点だけ挙げると、構造化出力が保証するのは**形**であって**確信度**ではない。
Apple のモデルが返す 0〜1 の値は、同じ入力でも 0.00 から 1.00 まで動いた。
判断が要るなら、確率ではなく判断そのものを聞く方が安定する（`task8`）。
それでも判断は独立せず、順序や会話履歴で動く（`task9`）。

## 構成

```
.envrc                direnv で認証情報を読み込む（秘密は書かない）
env.example           認証情報のテンプレート。実値は入れない
examples/
  common.py           Jev を呼ぶ薄いクライアント（3経路を吸収）
  questions.py        questions をプロンプトに組み替える（標準ライブラリのみ）
  task2_basic.py      noul で単一の判断
  task3_pipeline.py   choice で分類し、確信度で分岐
  task4_sequential.py 時系列。文脈を state に入れる
  task5_llm_baseline.py     同じ判断を ollama の LLM にやらせる
  task6_criteria_matters.py criteria の書き方で値が変わることを見る
  task7_apple_fm_structured.py  Jev の型を構造化出力に写像する
  task8_fm_criteria.py          criteria と、確率か判断かの違い
  task9_fm_independence.py      判断が独立しているかを確かめる
tests/
  test_tasks_offline.py  ネットワーク不要のロジック検証
docs/
  01-why-judgment-models.md
  02-question-types.md
  03-pipeline.md
  04-sequential.md
  05-verification.md
  06-llm-baseline.md
  07-apple-fm.md
```

## 確認

```bash
uv run --with pytest pytest tests/ -q
```

## 注意

- 確信度の閾値は**教材用の例示値**。自分のデータで較正するもの
- `criteria` は判定基準の「書き方」を示す。中身は自分の運用に合わせる
