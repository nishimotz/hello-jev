"""Task 2: noul で単一の判断を取る。

問い合わせが「緊急か」を yes の確率で返させる。
実行するには環境変数 CLOUDFLARE_ACCOUNT_ID と
CLOUDFLARE_API_TOKEN が必要（リポジトリ直下の .envrc で direnv が入れる）。
"""

from common import evaluate

# 架空のサンプル。実データは使わない。
STATE = "サービスが急に繋がらなくなりました。至急確認してください。"

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


def main() -> None:
    answers = evaluate(STATE, QUESTIONS)
    result = answers["is_urgent"]
    probability = result["noul"]
    print(f"緊急である確率: {probability:.2f}")


if __name__ == "__main__":
    main()
