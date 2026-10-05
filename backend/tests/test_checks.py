"""课程核对阈值测试：阈值只做判读，不改变任何产率数值。"""
from __future__ import annotations

import pytest

from app.checks import evaluate_checks, normalize_thresholds
from app.curve import prepare_curve
from app.planning import evaluate_plan


def pc(ts, rs):
    return prepare_curve([{"temp_c": t, "recovered_pct": r} for t, r in zip(ts, rs)])


def _linear_curve():
    return pc([10, 50, 100, 150, 200], [0, 25, 50, 75, 100])


# ---------- 纯函数判读 ----------
def test_tightening_overlap_threshold_flips_status_not_values():
    """验收①：同一方案收紧重叠阈值后状态变化而数值不变。"""
    c = _linear_curve()
    cuts = [
        {"name": "a", "start_temp_c": 10, "end_temp_c": 120},
        {"name": "b", "start_temp_c": 100, "end_temp_c": 200},
    ]
    res = evaluate_plan(c, cuts, 0.0)
    overlap = res["totals"]["overlap_pct"]
    assert overlap == pytest.approx(10.0, abs=1e-6)

    loose = evaluate_checks(res, {"max_overlap_pct": 10})
    tight = evaluate_checks(res, {"max_overlap_pct": 10.0 - 0.01})

    li = next(i for i in loose["items"] if i["key"] == "max_overlap_pct")
    ti = next(i for i in tight["items"] if i["key"] == "max_overlap_pct")
    assert li["passed"] is True
    assert ti["passed"] is False
    # 实际值与区间数值完全一致，只有判定翻转
    assert li["actual_pct"] == ti["actual_pct"] == overlap
    assert li["interval_pct"] == "[0, 10] %"
    assert ti["interval_pct"] == "[0, 9.99] %"
    assert loose["all_passed"] is True and tight["all_passed"] is False


def test_min_union_yield_threshold_directions_and_interval():
    c = _linear_curve()
    res = evaluate_plan(c, [{"name": "a", "start_temp_c": 10, "end_temp_c": 200}], 0.0)
    assert res["totals"]["union_yield_pct"] == pytest.approx(100.0)
    ok = evaluate_checks(res, {"min_union_yield_pct": 60})
    i_ok = next(i for i in ok["items"] if i["key"] == "min_union_yield_pct")
    assert i_ok["passed"] is True
    # 实际 100% 低于阈值 101（直接构造合法 dict，越界值由 Pydantic/normalize 拦截）
    bad = evaluate_checks(res, {"min_union_yield_pct": 101.0})
    i_bad = next(i for i in bad["items"] if i["key"] == "min_union_yield_pct")
    assert i_bad["configured"] is False  # 超界阈值被丢弃 => 该项不评
    # 边界：actual == threshold 算通过（>=）
    edge = evaluate_checks(res, {"min_union_yield_pct": 100})
    assert next(
        i for i in edge["items"] if i["key"] == "min_union_yield_pct"
    )["passed"] is True
    assert i_ok["interval_pct"] == "[60, 100] %"


def test_in_range_gap_excludes_fully_out_of_range_gap():
    """越界尾缺口（无数据）不计入“范围内缺口”，避免与越界提示重复判罚。"""
    c = _linear_curve()  # 实测范围 10~200℃
    # 80~120 中间缺口在范围内；200~260 尾缺口完全越界
    cuts = [
        {"name": "a", "start_temp_c": 10, "end_temp_c": 80},
        {"name": "b", "start_temp_c": 120, "end_temp_c": 260},
    ]
    res = evaluate_plan(c, cuts, 0.0)
    inter = sum(g["volume_pct"] for g in res["gaps"] if g["kind"] == "inter")
    tail = [g for g in res["gaps"] if g["kind"] == "tail"][0]
    assert tail["fully_outside_range"] and tail["volume_pct"] is None

    chk = evaluate_checks(res, {"max_in_range_gap_pct": 50})
    item = next(i for i in chk["items"] if i["key"] == "max_in_range_gap_pct")
    assert item["actual_pct"] == pytest.approx(inter)
    assert item["passed"] is True
    tight = evaluate_checks(res, {"max_in_range_gap_pct": 5})
    assert not next(
        i for i in tight["items"] if i["key"] == "max_in_range_gap_pct"
    )["passed"]


def test_no_thresholds_yields_neutral_items_with_actuals():
    """验收②（核心层）：未设置阈值时每项仍返回实际值，但不评通过状态。"""
    c = _linear_curve()
    res = evaluate_plan(c, [{"name": "a", "start_temp_c": 10, "end_temp_c": 200}], 0.0)
    chk = evaluate_checks(res, None)
    assert chk["all_passed"] is None
    assert chk["configured_keys"] == []
    assert len(chk["items"]) == 3
    for it in chk["items"]:
        assert it["configured"] is False and it["passed"] is None
        assert it["threshold_pct"] is None and it["interval_pct"] is None
        assert isinstance(it["actual_pct"], float)


def test_thresholds_do_not_change_curve_or_yields():
    """阈值是教学判读：evaluate_plan 结果不随阈值变化（阈值只进 evaluate_checks）。"""
    c = _linear_curve()
    cuts = [
        {"name": "a", "start_temp_c": 10, "end_temp_c": 120},
        {"name": "b", "start_temp_c": 100, "end_temp_c": 200},
    ]
    r1 = evaluate_plan(c, cuts, 0.0)
    r2 = evaluate_plan(c, cuts, 0.0)
    assert r1["totals"] == r2["totals"]
    evaluate_checks(r1, {"min_union_yield_pct": 0, "max_overlap_pct": 0,
                         "max_in_range_gap_pct": 0})
    # 附加判读后原始 totals 不变
    assert r1["totals"] == r2["totals"]


def test_normalize_thresholds_drops_invalid_keys_and_out_of_range_values():
    assert normalize_thresholds(None) == {}
    assert normalize_thresholds({}) == {}
    assert normalize_thresholds({"max_overlap_pct": 3.5}) == {"max_overlap_pct": 3.5}
    # 越界值 / 非法类型 / 未知键 一律忽略
    assert normalize_thresholds({"max_overlap_pct": 101}) == {}
    assert normalize_thresholds({"max_overlap_pct": -1}) == {}
    assert normalize_thresholds({"max_overlap_pct": "x"}) == {}
    assert normalize_thresholds({"unknown_key": 1}) == {}
