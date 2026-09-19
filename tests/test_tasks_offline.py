"""ネットワーク不要のテスト。

Jev の呼び出しをモックし、判定後の分岐ロジックだけを検証する。
Apple FM（task7〜9）は SDK が無くても import でき、スキーマの組み立てまで
検証できる。生成そのものは呼ばない。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))

import common
import pytest
from questions import render_prompt, score_levels
from task3_pipeline import route
from task5_llm_baseline import THINK, LlmError
from task5_llm_baseline import evaluate_noul as llm_evaluate_noul
from task7_apple_fm_structured import (
    FmError,
    _to_answers,
    criteria_levels,
)
from task7_apple_fm_structured import (
    repeat as fm_repeat,
)

# apple-fm-sdk は重いので、このモジュールでは読み込まない。
# 型を組み立てる部分だけをダミーで検証する。


def _has_fm() -> bool:
    try:
        import apple_fm_sdk  # noqa: F401
    except ImportError:
        return False
    return True


def test_think_is_off_by_default() -> None:
    """思考は既定で切る。判断だけを取るのに思考は不要で、10倍以上速い。"""
    assert THINK is False


def test_llm_raises_when_ollama_is_unreachable() -> None:
    """ollama が落ちていれば LlmError になる。例外を握りつぶさない。"""
    import task5_llm_baseline as t5

    original = t5.OLLAMA_URL
    try:
        # 誰も listen していないポートへ向ける
        t5.OLLAMA_URL = "http://127.0.0.1:1/api/chat"
        try:
            llm_evaluate_noul("test")
        except LlmError:
            pass  # 期待どおり
        else:
            raise AssertionError("LlmError が送出されなかった")
    finally:
        t5.OLLAMA_URL = original


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


# --- questions.py（プロンプト組み立て） ---------------------------------


def test_render_prompt_includes_state_and_criteria() -> None:
    """questions が本文に開かれ、state が最後に置かれる。"""
    questions = {
        "department": {
            "type": "choice",
            "instructions": "Which team?",
            "criteria": {"billing": "請求", "other": "その他"},
        },
    }
    prompt = render_prompt("請求書が違います。", questions)
    assert "Which team?" in prompt
    assert "billing: 請求" in prompt
    assert prompt.endswith("Message: 請求書が違います。")


def test_render_prompt_omits_score_criteria() -> None:
    """score のレベル名は本文に開かない。

    長い説明を本文に並べると、どの入力にも同じレベルを返すようになる。
    レベル名はスキーマの guide に短く置く。
    """
    questions = {
        "severity": {
            "type": "score",
            "instructions": "How harmful?",
            "criteria": ["Safe: no action", "Dangerous: credentials"],
        },
    }
    prompt = render_prompt("テスト", questions)
    assert "How harmful?" in prompt
    assert "Safe: no action" not in prompt


def test_score_levels_reports_max_level() -> None:
    """score のレベルの最大値が取れる（スキーマの range に使う）。"""
    questions = {
        "severity": {"type": "score", "criteria": ["a", "b", "c"]},
        "is_urgent": {"type": "noul", "criteria": {}},
    }
    assert score_levels(questions) == {"severity": 2}


def test_criteria_levels_has_three_steps() -> None:
    """criteria は なし / 片側 / 両側 の 3 水準。task6 と同じ考え方。"""
    levels = criteria_levels()
    assert list(levels) == ["なし", "片側だけ", "両側を書く"]
    assert levels["なし"]["is_urgent"]["criteria"] == {}
    assert "true" in levels["片側だけ"]["is_urgent"]["criteria"]
    both = levels["両側を書く"]["is_urgent"]["criteria"]
    assert set(both) == {"true", "false"}


# --- task7（Apple FM の写像） -------------------------------------------


def test_to_answers_normalizes_to_jev_shape() -> None:
    """生成された型を、Jev の answers と同じ形の辞書にする。

    int で返った値も float に矯正する。confidence は付かない。
    """

    class Result:
        is_urgent = 1  # float で宣言しても int で返ることがある
        department = "billing"
        severity = 1

    questions = {
        "is_urgent": {"type": "noul"},
        "department": {"type": "choice"},
        "severity": {"type": "score", "criteria": ["a", "b", "c"]},
    }
    answers = _to_answers(Result(), questions)
    assert answers["is_urgent"] == {"type": "noul", "noul": 1.0}
    assert isinstance(answers["is_urgent"]["noul"], float)
    assert answers["department"] == {"type": "choice", "choice": "billing"}
    assert answers["severity"] == {"type": "score", "score": 1.0}
    # confidence は返らない。Jev との差がここに出る。
    assert "confidence" not in answers["department"]


def test_fm_answers_can_feed_the_same_router() -> None:
    """同じ辞書の形なので、task3 の route() にそのまま渡せる。

    choice は confidence を持たないので 0.0 として扱われ、fallback になる。
    「確信度で分岐する設計がそのままでは使えない」ことの表現。
    """

    class Result:
        department = "billing"

    answers = _to_answers(Result(), {"department": {"type": "choice"}})
    result = route(answers)
    assert result["choice"] == "billing"
    assert result["action"] == "fallback"


def test_fm_repeat_is_at_least_one(monkeypatch) -> None:
    """FM_REPEAT は 1 未満にならない。壊れた値は既定に戻す。"""
    monkeypatch.setenv("FM_REPEAT", "0")
    assert fm_repeat() == 1
    monkeypatch.setenv("FM_REPEAT", "abc")
    assert fm_repeat() == 5
    monkeypatch.setenv("FM_REPEAT", "12")
    assert fm_repeat() == 12


def test_fm_raises_when_sdk_is_absent() -> None:
    """apple-fm-sdk が無ければ FmError。他の例外は投げない。

    SDK が入っている環境では、このテストは意味を持たないので飛ばす。
    """
    if _has_fm():
        pytest.skip("apple-fm-sdk が入っている環境では省略")
    import task7_apple_fm_structured as t7

    try:
        t7._load_fm()
    except FmError:
        pass  # 期待どおり
    else:
        raise AssertionError("FmError が送出されなかった")


def test_unknown_question_type_is_rejected() -> None:
    """未知の型は黙って通さない。"""
    if _has_fm():
        pytest.skip("apple-fm-sdk が入っている環境では省略")
    import task7_apple_fm_structured as t7

    with pytest.raises(FmError):
        t7.build_generable({"x": {"type": "mystery"}})
