"""Task 7: 同じ問いを Apple のオンデバイスモデルに、構造化出力でやらせる。

このファイルは Jev を呼ばない。`apple-fm-sdk`（Apple Intelligence の
オンデバイスモデル）に、**Jev と同じ questions をそのまま写像して**投げる。

Apple のモデルは文章を生成するモデルなので、Jev の型（noul / choice / score）
は無い。`fm.guide()` の制約で同じ形を作り、返り値を 1 つの辞書に正規化する。
正規化した形は task3 の `route()` にそのまま渡せる。

分かったこと（docs/07 に実測を書く）:
    - 形式は構造化出力で守られる。choice は定義した選択肢しか返らない
    - noul の確率は**生成された値**であり、較正されていない。
      同じ入力でも値が動き、criteria の書き方で値の位置が動く
    - 判断ごとの confidence のようなものは返らない
    - score のレベル名は guide に短く置く。長い説明を guide や本文に
      入れると、どの入力にも同じレベルを返すようになる

必要なもの:
    macOS 27 以降（Apple Intelligence が有効）
    pip install apple-fm-sdk  （uv なら --with apple-fm-sdk）

    SDK のメタデータは「macOS 26.0+」と書いているが、同梱の dylib は
    26 では動かない。dylib が要求する FoundationModels のシンボルのうち
    7 個が macOS 26 SDK に無い（27 SDK には全部ある）。この教材が使う
    GenerationOptions の初期化子もその 1 つ。詳しくは docs/07。

環境変数:
    FM_REPEAT   同じ条件を繰り返す回数（既定 5）
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

# 架空のサンプル。実データは使わない。
STATE = "サービスが急に繋がらなくなりました。至急確認してください。"
REVIEW_STATE = "請求書の金額が間違っています。確認をお願いします。"

# 緊急度が違う 3 件。task6 と同じものを使う。
CASES = {
    "明確に緊急": "本番が落ちて全顧客が使えません。至急復旧してください。",
    "要確認の依頼": REVIEW_STATE,
    "明確に非緊急": "ドキュメントの誤字を見つけました。お時間あるときに直してください。",
}

# task2 / task3 / task4 と同じ questions。Jev と同じものを写像する。
QUESTIONS = {
    "is_urgent": {
        "type": "noul",
        "instructions": "Does this message report an urgent problem?",
        "criteria": {
            "true": "業務が止まっている、または至急の対応を求める",
            "false": "急ぎではない、または単なる質問",
        },
    },
}

CHOICE_QUESTIONS = {
    "department": {
        "type": "choice",
        "instructions": "Which team should handle this inquiry?",
        "criteria": {
            "account": "ログイン、パスワード、プロフィール",
            "billing": "請求、支払い、返金",
            "technical": "不具合、障害、連携",
            "other": "上記に当てはまらない",
        },
    },
}

SCORE_QUESTIONS = {
    "severity": {
        "type": "score",
        "instructions": "How harmful would acting on this message be?",
        "criteria": [
            "Safe: no action required beyond normal reading",
            "Suspicious: verify before acting, no credentials involved",
            "Dangerous: credentials, payment, or personal data would be exposed",
        ],
    },
}


def criteria_levels() -> dict[str, dict[str, dict[str, Any]]]:
    """criteria の書き方を 3 水準に変えた questions を返す。

    task6 と同じ 3 水準。同じ state でも、基準の書き方だけで値が動くことを見る。
    """
    base = "Does this message report an urgent problem?"
    return {
        "なし": {
            "is_urgent": {"type": "noul", "instructions": base, "criteria": {}},
        },
        "片側だけ": {
            "is_urgent": {
                "type": "noul",
                "instructions": base,
                "criteria": {
                    "true": "業務が止まっている、または至急の対応を求める",
                },
            },
        },
        "両側を書く": {
            "is_urgent": {
                "type": "noul",
                "instructions": base,
                "criteria": {
                    "true": "業務が止まっている、または至急の対応を求める",
                    "false": "急ぎではない、または単なる質問",
                },
            },
        },
    }


class FmError(RuntimeError):
    """Apple Foundation Models 呼び出しの失敗。

    認証情報の欠落と同じように、環境の不足も握りつぶさず呼び出し側に渡す。
    呼び出し側（テストを含む）はこの例外だけを捕まえればよい。
    """


def repeat() -> int:
    """繰り返し回数。環境変数で変えられる。"""
    try:
        value = int(os.environ.get("FM_REPEAT", "5"))
    except ValueError:
        return 5
    return max(1, value)


def _load_fm() -> Any:
    """apple_fm_sdk を読み込む。無ければ FmError にする。

    import はここで行う。SDK が無い環境でもこのファイルを import でき、
    テストが分岐を検証できるようにするため。
    """
    try:
        import apple_fm_sdk as fm
    except ImportError as e:
        raise FmError(
            "apple-fm-sdk が入っていない。macOS 27 以降で `pip install "
            "apple-fm-sdk` を実行する（uv なら `uv run --with apple-fm-sdk "
            "python examples/task7_apple_fm_structured.py`）。"
        ) from e
    return fm


def build_generable(questions: dict[str, dict[str, Any]]) -> Any:
    """Jev の questions から、対応する @generable の型を作る。

    型は静的に書くのではなく、questions から組み立てる。こうすると
    task2〜4 の questions をそのまま使い回せる。

    写像:
        noul  -> float に `range=(0, 1)`
        choice -> str に `anyOf=[選択肢...]`
        score -> float に `range=(0, レベル数)`

    Raises:
        FmError: SDK が無い、または未知の型が来た。
    """
    fm = _load_fm()
    from questions import score_levels  # 遅延 import（common.py と同じ理由）

    fields: dict[str, Any] = {}
    annotations: dict[str, Any] = {}
    levels = score_levels(questions)

    for qid, question in questions.items():
        kind = question["type"]
        if kind == "noul":
            annotations[qid] = float
            fields[qid] = fm.guide(
                f"{question['instructions']} Return P(yes) as a number from 0 to 1.",
                range=(0.0, 1.0),
            )
        elif kind == "choice":
            annotations[qid] = str
            fields[qid] = fm.guide(
                question["instructions"],
                anyOf=list(question["criteria"]),
            )
        elif kind == "score":
            annotations[qid] = float
            # レベル名は短く、スキーマの guide に置く。長い説明を guide や
            # 本文に入れると、どの入力にも同じレベルを返すようになる（実測）。
            # レベル名は criteria の先頭の語（"Safe: ..." なら "Safe"）。
            names = [
                str(value).split(":")[0].strip() for value in question["criteria"]
            ]
            legend = " ".join(
                f"{index}={name}" for index, name in enumerate(names)
            )
            fields[qid] = fm.guide(
                f"{legend}. May be fractional.",
                range=(0.0, float(levels[qid])),
            )
        else:
            raise FmError(f"未知の型: {qid}={kind!r}")

    fields["__annotations__"] = annotations
    # @fm.generable を動的なクラスに適用する
    return fm.generable("Typed judgments for one message")(type("Judgments", (), fields))


def generation_options(fm: Any, *, greedy: bool = True, temperature: float = 0.0) -> Any:
    """決定的な生成を頼むオプション。

    greedy と temperature=0 を指定しても値は揺れる（docs/07 に実測）。
    ここで指定するのは、比較条件を ollama（task5）とそろえるため。
    """
    if greedy:
        return fm.GenerationOptions(
            sampling=fm.SamplingMode.greedy(), temperature=temperature
        )
    return fm.GenerationOptions(temperature=temperature)


def _to_answers(result: Any, questions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """生成された型を、Jev の answers と同じ形の辞書にする。

    こうすると task3 の `route()` にそのまま渡せる。
    Jev と違い confidence は返らないので、付かないままにする。
    """
    answers: dict[str, Any] = {}
    for qid, question in questions.items():
        value = getattr(result, qid)
        kind = question["type"]
        if kind == "noul":
            # float で宣言しても int で返ることがある。確率として扱うので矯正する。
            answers[qid] = {"type": "noul", "noul": float(value)}
        elif kind == "choice":
            answers[qid] = {"type": "choice", "choice": value}
        else:
            answers[qid] = {"type": "score", "score": float(value)}
    return answers


async def _evaluate_async(
    state: Any,
    questions: dict[str, dict[str, Any]],
    *,
    session: Any = None,
    greedy: bool = True,
) -> dict[str, Any]:
    """state と questions を 1 回評価して answers を返す。"""
    fm = _load_fm()
    from questions import render_prompt

    model = fm.SystemLanguageModel()
    available, reason = model.is_available()
    if not available:
        raise FmError(
            f"オンデバイスモデルが使えない: {reason}。"
            "Apple Intelligence を有効にし、対応する Mac で実行する。"
        )

    cls = build_generable(questions)
    options = generation_options(fm, greedy=greedy)
    target = session or fm.LanguageModelSession(model=model)
    result = await target.respond(
        render_prompt(state, questions), generating=cls, options=options
    )
    return _to_answers(result, questions)


def evaluate(
    state: Any,
    questions: dict[str, dict[str, Any]],
    *,
    session: Any = None,
    greedy: bool = True,
) -> dict[str, Any]:
    """同期の入り口。中で asyncio を回す。

    Returns:
        answers の dict。例: {"is_urgent": {"type": "noul", "noul": 0.3}}

    Raises:
        FmError: SDK が無い、モデルが使えない、生成に失敗した。
    """
    try:
        return asyncio.run(
            _evaluate_async(state, questions, session=session, greedy=greedy)
        )
    except FmError:
        raise
    except Exception as e:  # SDK の例外は多岐にわたるのでここで包む
        raise FmError(f"生成に失敗した: {type(e).__name__}: {e}") from e


def probe_noul(
    state: str,
    *,
    times: int = 5,
    questions: dict[str, dict[str, Any]] | None = None,
) -> list[float]:
    """同じ state を times 回評価し、noul の値の一覧を返す。

    値が動くこと自体を見るためのもの。1 回だけ見ると気づけない。
    """
    questions = questions or QUESTIONS
    qid = next(
        qid for qid, question in questions.items() if question["type"] == "noul"
    )
    values: list[float] = []
    for _ in range(times):
        answers = evaluate(state, questions)
        values.append(answers[qid]["noul"])
    return values


def main() -> None:
    try:
        fm = _load_fm()
    except FmError as e:
        print(e)
        return

    available, reason = fm.SystemLanguageModel().is_available()
    print("モデル: Apple Foundation Models（オンデバイス、Jev ではない）")
    print(f"利用可否: {available} {reason or ''}")
    if not available:
        return

    from common import AUTO_THRESHOLD, REVIEW_THRESHOLD, route_by_confidence

    times = repeat()
    print(f"\n=== noul: 同じ state と criteria を {times} 回ずつ ===")
    print("greedy + temperature=0 を指定しても、値は揺れる。\n")

    levels = criteria_levels()
    width = 24
    print(f"{'':<10}" + "".join(f"{label:>{width}}" for label in levels))
    print("-" * (10 + width * len(levels)))
    for case, state in CASES.items():
        row = f"{case:<10}"
        for questions in levels.values():
            values = probe_noul(state, times=times, questions=questions)
            span = f"{min(values):.2f}-{max(values):.2f}"
            row += f"{f'{sum(values) / len(values):.2f} ({span})':>{width}}"
        print(row)
    print("\n各セルは「平均（観測した最小-最大）」。1 回の値は信用できない。")

    print("\n=== 閾値で振り分けると、criteria の書き方で結果が変わる ===")
    for label, questions in levels.items():
        values = probe_noul(CASES["要確認の依頼"], times=times, questions=questions)
        actions = sorted({route_by_confidence(v) for v in values})
        span = f"{min(values):.2f}-{max(values):.2f}"
        print(f"  {label:<8} 幅 {span:<9} 出た行動 {actions}")
    print(f"  （auto {AUTO_THRESHOLD:g} 以上 / review {REVIEW_THRESHOLD:g} 以上）")
    print("\n基準を書かないと、同じ入力から auto も review も reject も出る。")
    print("どれが出るかを決めているのは、入力ではなく criteria の書き方。")

    print("\n=== choice は定義した選択肢しか返らない ===")
    for state in (REVIEW_STATE, "ログインできません。", "アプリが起動時に落ちます。"):
        answers = evaluate(state, CHOICE_QUESTIONS)
        print(f"  {state[:16]:<18} -> {answers['department']['choice']}")

    print("\n=== score は順序を返す。確率は返らない ===")
    for state in (CASES["明確に緊急"], REVIEW_STATE, CASES["明確に非緊急"]):
        answers = evaluate(state, SCORE_QUESTIONS)
        print(f"  {state[:16]:<18} -> severity={answers['severity']['score']:.2f}")

    print("\n形式は構造化出力で守られる。だが noul の値は較正されていない。")
    print("confidence も返らないので、確信度で分岐する設計がそのままでは使えない。")
    print("同じ 1 つの判断でも、値は criteria と実行のたびに動く（docs/07）。")


if __name__ == "__main__":
    main()
