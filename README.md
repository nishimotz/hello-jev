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

## セットアップ

Cloudflare Workers AI 経由で呼ぶ。

```bash
export CLOUDFLARE_ACCOUNT_ID=...
export CLOUDFLARE_API_TOKEN=...
uv run --with requests python examples/task2_basic.py
```

## 構成

```
examples/
  common.py           Jev を呼ぶ薄いクライアント
  task2_basic.py      noul で単一の判断
  task3_pipeline.py   choice で分類し、確信度で分岐
  task4_sequential.py 時系列。文脈を state に入れる
tests/
  test_tasks_offline.py  ネットワーク不要のロジック検証
docs/
  01-why-judgment-models.md
  02-question-types.md
  03-pipeline.md
  04-sequential.md
  05-verification.md
```

## 確認

```bash
uv run --with pytest --with requests pytest tests/ -q
```

## 注意

- 確信度の閾値は**教材用の例示値**。自分のデータで較正するもの
- `criteria` は判定基準の「書き方」を示す。中身は自分の運用に合わせる
