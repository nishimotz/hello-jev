"""Task 4: 時系列を扱う。

Jev は会話履歴を持たない。だから文脈はコードが state に明示的に入れる。
直近の判断結果を state に含めて、文脈を持ち越す例。
"""

from common import evaluate

QUESTIONS = {
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

# 架空のサンプル。直近の判断結果（要約のみ）を持ち越す。
RECENT_DECISIONS = [
    {"summary": "請求金額の問い合わせ", "department": "billing"},
    {"summary": "パスワード再設定の依頼", "department": "account"},
]


def build_state(message: str, recent: list[dict]) -> dict:
    """今回の入力と直近の判断結果をまとめて state を作る。"""
    return {"current": message, "recent_decisions": recent}


def main() -> None:
    state = build_state("またログインできません。", RECENT_DECISIONS)
    answers = evaluate(state, QUESTIONS)
    print(answers)


if __name__ == "__main__":
    main()
