"""方案阈值核对（教学判读）测试。

验收口径：
1. 同一方案收紧重叠阈值后，判定状态变化而实际数值不变；
2. 未设置阈值的旧方案仍正常展示（threshold_checks 为空、导出正常）；
3. 含越界切点时，阈值结果与原有越界提示同时可见。
"""
from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def seeded(client):
    r = client.post("/api/seed")
    assert r.status_code in (200, 409), r.text  # 其它模块可能已导入过
    return client, client.get("/api/experiments").json()


def _plan(**thresholds):
    return {
        "name": "thr-plan",
        "basis": "volume",
        "loss_pct": 0.0,
        "cuts": [
            {"name": "a", "start_temp_c": 55, "end_temp_c": 200},
            {"name": "b", "start_temp_c": 190, "end_temp_c": 340},
        ],
        "thresholds": thresholds,
    }


def test_evaluate_returns_threshold_checks(seeded):
    client, exps = seeded
    exp_id = exps[0]["id"]  # 示例A：实测 55~340 ℃
    plan = _plan(min_union_yield_pct=50, max_overlap_pct=1.0, max_in_range_gap_pct=30)
    r = client.post(f"/api/experiments/{exp_id}/evaluate", json=plan).json()

    checks = {c["key"]: c for c in r["threshold_checks"]}
    assert set(checks) == {
        "min_union_yield_pct", "max_overlap_pct", "max_in_range_gap_pct"
    }
    t = r["totals"]
    # 每项都带实际值、通过状态与判定区间，且实际值与总量核对完全一致
    assert checks["min_union_yield_pct"]["actual_pct"] == t["union_yield_pct"]
    assert checks["min_union_yield_pct"]["interval_pct"] == [50.0, 100.0]
    assert checks["min_union_yield_pct"]["passed"] is True

    assert checks["max_overlap_pct"]["actual_pct"] == t["overlap_pct"]
    assert checks["max_overlap_pct"]["interval_pct"] == [0.0, 1.0]
    assert checks["max_overlap_pct"]["passed"] is False  # 190~200 ℃ 重叠超过 1%

    gap_total = t["front_gap_pct"] + t["inter_gap_pct"] + t["tail_gap_pct"]
    assert checks["max_in_range_gap_pct"]["actual_pct"] == round(gap_total, 4)
    assert checks["max_in_range_gap_pct"]["interval_pct"] == [0.0, 30.0]


def test_tightening_overlap_threshold_flips_status_not_values(seeded):
    """验收1：同一方案收紧重叠阈值 => 状态翻转，实际值与产率数值不变。"""
    client, exps = seeded
    exp_id = exps[0]["id"]
    loose = client.post(
        f"/api/experiments/{exp_id}/evaluate", json=_plan(max_overlap_pct=100)
    ).json()
    tight = client.post(
        f"/api/experiments/{exp_id}/evaluate", json=_plan(max_overlap_pct=0.5)
    ).json()

    (loose_ck,) = loose["threshold_checks"]
    (tight_ck,) = tight["threshold_checks"]
    assert loose_ck["passed"] is True
    assert tight_ck["passed"] is False
    # 数值不变：实际值、区间端点语义与全部产率结果一致
    assert loose_ck["actual_pct"] == tight_ck["actual_pct"]
    assert loose["totals"] == tight["totals"]
    assert loose["cuts"] == tight["cuts"]
    assert loose["overlaps"] == tight["overlaps"]


def test_no_thresholds_backward_compatible(seeded):
    """验收2：未设置阈值的方案照常计算、保存、导出，threshold_checks 为空。"""
    client, exps = seeded
    exp_id = exps[0]["id"]
    plan = {
        "name": "legacy-no-thresholds",
        "basis": "volume",
        "loss_pct": 1.5,
        "cuts": [{"name": "f", "start_temp_c": 55, "end_temp_c": 340}],
    }
    r = client.post(f"/api/experiments/{exp_id}/evaluate", json=plan).json()
    assert r["threshold_checks"] == []

    saved = client.post(f"/api/experiments/{exp_id}/plans", json=plan).json()
    pid = saved["id"]
    got = client.get(f"/api/plans/{pid}").json()
    assert got["plan"]["thresholds"] is None
    assert got["result"]["threshold_checks"] == []

    md = client.get(f"/api/plans/{pid}/export?format=markdown")
    assert md.status_code == 200 and "阈值核对" not in md.text
    js = client.get(f"/api/plans/{pid}/export?format=json").json()
    assert js["plan"]["thresholds"] is None
    assert js["result"]["threshold_checks"] == []


def test_thresholds_coexist_with_out_of_range(seeded):
    """验收3：含越界切点时，阈值结果与原有越界提示同时可见。"""
    client, exps = seeded
    exp_id = exps[0]["id"]  # 实测终点 340 ℃
    plan = _plan(max_overlap_pct=100)
    plan["cuts"].append({"name": "越界尾段", "start_temp_c": 340, "end_temp_c": 370})
    r = client.post(f"/api/experiments/{exp_id}/evaluate", json=plan).json()

    assert any(i["code"] == "out_of_range" for i in r["issues"])
    assert "out_of_range" in r["cuts"][2]["flags"]
    (ck,) = r["threshold_checks"]
    assert ck["key"] == "max_overlap_pct"
    assert ck["actual_pct"] is not None


def test_thresholds_saved_and_exported(seeded):
    """阈值随方案保存，并进入 Markdown / JSON 导出。"""
    client, exps = seeded
    exp_id = exps[0]["id"]
    plan = _plan(min_union_yield_pct=50, max_overlap_pct=1.0)
    saved = client.post(f"/api/experiments/{exp_id}/plans", json=plan).json()
    pid = saved["id"]
    assert len(saved["result"]["threshold_checks"]) == 2

    got = client.get(f"/api/plans/{pid}").json()
    assert got["plan"]["thresholds"] == {
        "min_union_yield_pct": 50.0,
        "max_overlap_pct": 1.0,
        "max_in_range_gap_pct": None,
    }
    assert len(got["result"]["threshold_checks"]) == 2

    md = client.get(f"/api/plans/{pid}/export?format=markdown").text
    assert "阈值核对" in md and "教学判读" in md
    assert "✅ 通过" in md and "❌ 未通过" in md

    js = client.get(f"/api/plans/{pid}/export?format=json").json()
    assert js["plan"]["thresholds"]["max_overlap_pct"] == 1.0
    keys = {c["key"] for c in js["result"]["threshold_checks"]}
    assert keys == {"min_union_yield_pct", "max_overlap_pct"}
