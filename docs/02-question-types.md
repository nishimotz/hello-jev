# 02. 3つの問いの型

Jev に渡せる問いは3種類だけ。どれを使うかで、返ってくる答えの形が決まる。

## noul — あるか / ないか

yes である確率を返す。

```python
"is_urgent": {
    "type": "noul",
    "instructions": "Does this message report an urgent problem?",
    "criteria": {
        "true": "業務が止まっている、または至急の対応を求める",
        "false": "急ぎではない、または単なる質問",
    },
}
```

返り値:

```json
{"type": "noul", "noul": 0.95}
```

`0.95` は「95% の確からしさで yes」。文字列の `"yes"` ではなく確率なので、
そのまま閾値にかけられる。

**criteria は両側を書く。** true 側だけでなく false 側も書くと、境界がぶれにくい。

## choice — どれか

定義済みの選択肢から1つを選ぶ。選んだ値、各選択肢の確率、confidence が返る。

```python
"department": {
    "type": "choice",
    "instructions": "Which team should handle this inquiry?",
    "criteria": {
        "account": "ログイン、パスワード、プロフィール",
        "billing": "請求、支払い、返金",
        "technical": "不具合、障害、連携",
        "other": "上記に当てはまらない",
    },
}
```

返り値:

```json
{
  "type": "choice",
  "choice": "billing",
  "confidence": 0.8,
  "probabilities": {"account": 0, "billing": 0.87, "technical": 0.13, "other": 0}
}
```

`probabilities` があるので、**2番目の候補も見える**。
「billing が0.87、technical が0.13」なら、技術寄りの問い合わせかもしれないと分かる。

## score — どのくらいか

順序付きのレベルで評価する。スコア、各レベルの確率、confidence が返る。

```python
"severity": {
    "type": "score",
    "instructions": "How harmful would acting on this message be?",
    "criteria": [
        "Safe: no action required beyond normal reading",
        "Suspicious: verify before acting, no credentials involved",
        "Dangerous: credentials, payment, or personal data would be exposed",
    ],
}
```

返り値:

```json
{
  "type": "score",
  "score": 1.04,
  "confidence": 0.94,
  "legend": {"0": "Safe...", "1": "Suspicious...", "2": "Dangerous..."},
  "probabilities": {"0": 0, "1": 0.96, "2": 0.04}
}
```

スコアは小数で返る。`1.04` は「レベル1寄りだが、わずかにレベル2側」。

## どれを選ぶか

| 判断の形 | 型 |
|---|---|
| あるかないか | noul |
| 既知のカテゴリのどれか | choice |
| 順序のある段階 | score |

**迷ったら、答えをどう使うかで決める。**
「閾値で自動実行 / 人間レビューに分ける」なら noul か choice の confidence を使う。
「深刻度で優先順位をつける」なら score。

## 確信度の読み方

- `noul` は確率そのもの（0〜1）
- `choice` / `score` は `confidence` と `probabilities` が別々に返る
  - `confidence` — その判断全体の確からしさ
  - `probabilities` — 各選択肢・各レベルの分布

**confidence が高くても、probabilities が割れていることがある。**
その場合は中身を確認する。数値は1つだけで判断しない。
