"""ネットワーク不要のテスト。

Jev の呼び出しをモックし、判定後の分岐ロジックだけを検証する。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))

from task3_pipeline import route  # noqa: E402


def test_auto_when_confidence_high() -> None:
    answers = {"department": {"choice": "billing", "confidence": 0.95}}
    result = route(answers)
    assert result["action"] == "auto"
    assert result["choice"] == "billing"


def test_review_when_confidence_medium() -> None:
    answers = {"department": {"choice": "billing", "confidence": 0.70}}
    result = route(answers)
    assert result["action"] == "review"


def test_fallback_when_confidence_low() -> None:
    answers = {"department": {"choice": "other", "confidence": 0.50}}
    result = route(answers)
    assert result["action"] == "fallback"


def test_boundary_values() -> None:
    """境界値: 0.90 は auto、0.60 は review。"""
    assert route({"department": {"choice": "x", "confidence": 0.90}})["action"] == "auto"
    assert route({"department": {"choice": "x", "confidence": 0.60}})["action"] == "review"
