"""ネットワーク不要のテスト。

Jev の呼び出しをモックし、判定後の分岐ロジックだけを検証する。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))

import common  # noqa: E402
from task3_pipeline import route  # noqa: E402


def test_backend_prefers_typesafe_when_key_present(monkeypatch) -> None:
    """TYPESAFE_API_KEY があれば直 API を最優先する。"""
    monkeypatch.setenv("TYPESAFE_API_KEY", "dummy")
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "dummy")
    assert common._select_backend() == "typesafe"


def test_backend_uses_vercel_when_only_gateway_key(monkeypatch) -> None:
    """AI_GATEWAY_API_KEY だけなら Vercel 経由。"""
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "dummy")
    assert common._select_backend() == "vercel"


def test_backend_falls_back_to_cloudflare(monkeypatch) -> None:
    """どちらのキーも無ければ Cloudflare 経由。"""
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("AI_GATEWAY_API_KEY", raising=False)
    assert common._select_backend() == "cloudflare"


def test_blank_key_is_treated_as_absent(monkeypatch) -> None:
    """空文字や空白だけの値は未設定と同じ扱いにする。"""
    monkeypatch.setenv("TYPESAFE_API_KEY", "   ")
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "   ")
    assert common._select_backend() == "cloudflare"


def test_noul_becomes_boolean_for_vercel() -> None:
    """教材の noul は Vercel の boolean に変換される。"""
    questions = {
        "a": {"type": "noul", "instructions": "x"},
        "b": {"type": "choice", "instructions": "y", "criteria": {"p": "q"}},
    }
    out = common._to_vercel_questions(questions)
    assert out["a"]["type"] == "boolean"
    assert out["b"]["type"] == "choice"
    # 元の dict を書き換えない
    assert questions["a"]["type"] == "noul"


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
