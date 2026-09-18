"""Task 3: choice で分類し、確信度で処理を分岐する。

判断の出力を、コード側の分岐条件として使う例。
確信度が高いものだけ自動処理し、低いものは人間に回す。
"""

from common import AUTO_THRESHOLD, REVIEW_THRESHOLD, evaluate

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


def route(answers: dict) -> dict:
    """answers を確信度で3段階に振り分ける。

    閾値は教材用の例示値。自運用で較正すること。
    """
    result = answers["department"]
    confidence = result.get("confidence", 0.0)

    if confidence >= AUTO_THRESHOLD:
        action = "auto"
    elif confidence >= REVIEW_THRESHOLD:
        action = "review"
    else:
        action = "fallback"

    return {
        "choice": result.get("choice"),
        "confidence": confidence,
        "action": action,
    }


def main() -> None:
    state = "請求書の金額が間違っています。"
    answers = evaluate(state, QUESTIONS)
    print(route(answers))


if __name__ == "__main__":
    main()
