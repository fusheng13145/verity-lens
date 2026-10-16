"""orchestrator.budget.evaluate_budget 单元测试（审计 #3 模块抽取）。"""
from orchestrator.budget import SOFT_WARN_RATIO, evaluate_budget


def _project(cap: float, used: float) -> dict:
    return {"token_budget": {"total": {"cap": cap, "used": used}}}


def test_ok_when_under_soft_threshold():
    st = evaluate_budget(_project(cap=100, used=10))
    assert st.level == "ok"
    assert st.ratio == 0.1
    assert st.cap == 100 and st.used == 10


def test_soft_warning_at_threshold():
    cap = 100.0
    used = cap * SOFT_WARN_RATIO
    st = evaluate_budget(_project(cap=cap, used=used))
    assert st.level == "soft"
    assert st.ratio == SOFT_WARN_RATIO


def test_hard_block_when_exhausted():
    st = evaluate_budget(_project(cap=100, used=100))
    assert st.level == "hard"
    assert st.ratio == 1.0


def test_hard_block_when_over_cap():
    st = evaluate_budget(_project(cap=100, used=120))
    assert st.level == "hard"


def test_no_cap_means_ok_ratio_zero():
    st = evaluate_budget({"token_budget": {"total": {"used": 50}}})
    assert st.level == "ok"
    assert st.ratio == 0.0


def test_missing_fields_default_to_ok():
    assert evaluate_budget({}).level == "ok"
    assert evaluate_budget({"token_budget": {}}).level == "ok"
    assert evaluate_budget({"token_budget": {"total": {}}}).level == "ok"
