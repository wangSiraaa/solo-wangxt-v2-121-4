"""API 冒烟测试：使用 conftest 配置的临时 SQLite。"""
from __future__ import annotations


def test_seed_and_evaluate_and_export(client):
    r = client.post("/api/seed")
    assert r.status_code == 200, r.text
    assert r.json()["loaded_experiments"] == 3

    # 重复导入应被拒绝
    assert client.post("/api/seed").status_code == 409

    exps = client.get("/api/experiments").json()
    assert len(exps) == 3

    # 示例C：曲线下降 => 曲线采样带硬错误
    cs = client.get(f"/api/experiments/{exps[2]['id']}/curve/sample").json()
    assert cs["has_blocking_errors"]
    assert any(i["code"] == "curve_decreases" for i in cs["issues"])

    # 示例A：缺端点 + 越界切点
    plan = {
        "name": "t",
        "basis": "volume",
        "loss_pct": 1.5,
        "cuts": [
            {"name": "f1", "start_temp_c": 55, "end_temp_c": 185},
            {"name": "f2", "start_temp_c": 185, "end_temp_c": 370},
        ],
    }
    res = client.post(f"/api/experiments/{exps[0]['id']}/evaluate", json=plan).json()
    assert res["applicable_range"]["extrapolation"] == "none"
    assert any(i["code"] == "missing_high_endpoint" for i in res["issues"])
    assert any(i["code"] == "out_of_range" for i in res["issues"])
    assert res["totals"]["identity_ok"]

    # 保存后导出 Markdown / JSON
    saved = client.post(f"/api/experiments/{exps[0]['id']}/plans", json=plan).json()
    pid = saved["id"]
    md = client.get(f"/api/plans/{pid}/export?format=markdown")
    assert md.status_code == 200 and "PCHIP" in md.text and "适用" in md.text
    js = client.get(f"/api/plans/{pid}/export?format=json")
    assert js.status_code == 200
    assert js.json()["result"]["method"]["interpolation"]


def test_create_experiment_rejects_decreasing_curve(client):
    payload = {
        "name": "bad",
        "feed_density_g_cm3": 0.8,
        "points": [
            {"temp_c": 10, "recovered_pct": 0},
            {"temp_c": 50, "recovered_pct": 30},
            {"temp_c": 90, "recovered_pct": 20},
        ],
    }
    r = client.post("/api/experiments", json=payload)
    assert r.status_code == 422
    assert any(i["code"] == "curve_decreases" for i in r.json()["detail"]["issues"])


def test_example_b_mass_basis_zero_width_and_mass_identity(client):
    exps = client.get("/api/experiments").json()
    bid = exps[1]["id"]
    plan = {
        "name": "b-live",
        "basis": "mass",
        "loss_pct": 0,
        "cuts": [
            {"name": "轻", "start_temp_c": 30, "end_temp_c": 185},
            {"name": "零宽", "start_temp_c": 185, "end_temp_c": 185},
            {"name": "重", "start_temp_c": 185, "end_temp_c": 600},
        ],
    }
    r = client.post(f"/api/experiments/{bid}/evaluate", json=plan).json()
    # 零宽馏分产率 0，不产生重叠/缺口
    assert r["cuts"][1]["volume_yield_pct"] == 0
    assert r["cuts"][1]["mass_yield_pct"] == 0
    assert "zero_width" in r["cuts"][1]["flags"]
    assert r["overlaps"] == []
    assert [g for g in r["gaps"] if g["volume_pct"]] == []
    # 质量与体积产率不同（密度随馏分变化），但两者各自闭合
    assert r["cuts"][0]["mass_yield_pct"] != r["cuts"][0]["volume_yield_pct"]
    assert r["totals"]["identity_ok"]
    assert r["totals"]["mass"]["identity_ok"]


def test_export_json_declares_scope_and_range(client):
    exps = client.get("/api/experiments").json()
    plan = {
        "name": "a-live", "basis": "volume", "loss_pct": 1.5,
        "cuts": [{"name": "f", "start_temp_c": 55, "end_temp_c": 370}],
    }
    saved = client.post(f"/api/experiments/{exps[0]['id']}/plans", json=plan).json()
    js = client.get(f"/api/plans/{saved['id']}/export?format=json").json()
    assert "不外推" in js["scope_notice"]
    assert js["result"]["applicable_range"]["extrapolation"] == "none"
    assert "PCHIP" in js["result"]["method"]["interpolation"]


# ---------- 课程核对阈值 ----------
def test_thresholds_evaluate_and_save_return_actuals_status_interval(client):
    exps = client.get("/api/experiments").json()
    aid = exps[0]["id"]
    plan = {
        "name": "th", "basis": "volume", "loss_pct": 0,
        "cuts": [
            {"name": "f1", "start_temp_c": 55, "end_temp_c": 185},
            {"name": "f2", "start_temp_c": 185, "end_temp_c": 340},
        ],
        "thresholds": {"min_union_yield_pct": 1, "max_overlap_pct": 5,
                       "max_in_range_gap_pct": 5},
    }
    res = client.post(f"/api/experiments/{aid}/evaluate", json=plan).json()
    chk = res["threshold_checks"]
    assert set(chk["configured_keys"]) == {
        "min_union_yield_pct", "max_overlap_pct", "max_in_range_gap_pct"}
    by = {i["key"]: i for i in chk["items"]}
    # 每项都带实际值、区间与布尔状态
    for key in chk["configured_keys"]:
        assert isinstance(by[key]["actual_pct"], (int, float))
        assert by[key]["interval_pct"] and by[key]["passed"] in (True, False)
    union = res["totals"]["union_yield_pct"]
    assert by["min_union_yield_pct"]["actual_pct"] == union
    assert by["max_overlap_pct"]["actual_pct"] == res["totals"]["overlap_pct"]
    assert chk["all_passed"] in (True, False)

    # 收紧重叠阈值重新评估：状态翻转、实际值不变
    plan_tight = dict(plan, thresholds={"max_overlap_pct": 0.0})
    res2 = client.post(f"/api/experiments/{aid}/evaluate", json=plan_tight).json()
    a1 = by["max_overlap_pct"]["actual_pct"]
    a2 = next(i for i in res2["threshold_checks"]["items"]
              if i["key"] == "max_overlap_pct")
    assert a2["actual_pct"] == a1
    assert res2["totals"]["overlap_pct"] == res["totals"]["overlap_pct"]
    # 原方案阈值 5（无重叠 => 通过），收紧到 0 仍通过；改为放宽-收紧翻转用并集演示
    plan_loose = dict(plan, thresholds={"min_union_yield_pct": union})
    plan_strict = dict(plan, thresholds={"min_union_yield_pct": union + 1})
    rl = client.post(f"/api/experiments/{aid}/evaluate", json=plan_loose).json()
    rs = client.post(f"/api/experiments/{aid}/evaluate", json=plan_strict).json()
    il = next(i for i in rl["threshold_checks"]["items"]
              if i["key"] == "min_union_yield_pct")
    is_ = next(i for i in rs["threshold_checks"]["items"]
               if i["key"] == "min_union_yield_pct")
    assert il["passed"] is True and is_["passed"] is False
    assert il["actual_pct"] == is_["actual_pct"] == union

    # 保存：阈值与方案一同落库，返回结果含核对块
    saved = client.post(f"/api/experiments/{aid}/plans", json=plan).json()
    pid = saved["id"]
    assert saved["result"]["threshold_checks"]["configured_keys"]
    got = client.get(f"/api/plans/{pid}").json()
    assert got["plan"]["thresholds"]["min_union_yield_pct"] == 1
    assert got["result"]["threshold_checks"]["configured_keys"]


def test_old_plan_without_thresholds_still_displays_neutral(client):
    """验收②：旧请求不带 thresholds（且旧库行无该列）时正常展示、不评状态。"""
    exps = client.get("/api/experiments").json()
    plan = {
        "name": "legacy", "basis": "volume", "loss_pct": 0,
        "cuts": [{"name": "f", "start_temp_c": 55, "end_temp_c": 185}],
    }
    res = client.post(f"/api/experiments/{exps[0]['id']}/evaluate", json=plan).json()
    chk = res["threshold_checks"]
    assert chk["configured_keys"] == [] and chk["all_passed"] is None
    assert all(i["passed"] is None and i["configured"] is False for i in chk["items"])
    assert all(i["actual_pct"] is not None for i in chk["items"])

    saved = client.post(f"/api/experiments/{exps[0]['id']}/plans", json=plan).json()
    got = client.get(f"/api/plans/{saved['id']}").json()
    assert got["plan"]["thresholds"] == {}
    assert got["result"]["threshold_checks"]["all_passed"] is None

    # 试验详情中的旧方案摘要也带空阈值，前端可正常回填
    detail = client.get(f"/api/experiments/{exps[0]['id']}").json()
    legacy_summary = next(p for p in detail["plans"] if p["name"] == "legacy")
    assert legacy_summary["thresholds"] == {}


def test_thresholds_coexist_with_out_of_range_warnings_and_export(client):
    """验收③：含越界切点时，阈值结果与原有越界提示同时可见，并进入导出。"""
    exps = client.get("/api/experiments").json()
    plan = {
        "name": "oor", "basis": "volume", "loss_pct": 1.5,
        "cuts": [
            {"name": "f1", "start_temp_c": 55, "end_temp_c": 185},
            {"name": "f2", "start_temp_c": 185, "end_temp_c": 370},  # >340 越界
        ],
        "thresholds": {"min_union_yield_pct": 99},  # 必然不通过
    }
    res = client.post(f"/api/experiments/{exps[0]['id']}/evaluate", json=plan).json()
    # 原有越界提示仍在
    assert any(i["code"] == "out_of_range" for i in res["issues"])
    assert any("out_of_range" in c["flags"] for c in res["cuts"])
    # 阈值核对同时给出且判定为不通过
    chk = res["threshold_checks"]
    item = next(i for i in chk["items"] if i["key"] == "min_union_yield_pct")
    assert item["configured"] and item["passed"] is False
    assert chk["all_passed"] is False

    saved = client.post(f"/api/experiments/{exps[0]['id']}/plans", json=plan).json()
    pid = saved["id"]
    md = client.get(f"/api/plans/{pid}/export?format=markdown").text
    assert "课程核对阈值" in md and "❌ 不通过" in md
    assert "最低切出体积产率" in md
    # 越界提示章节仍保留（章节号顺延为 5）
    assert "out_of_range" in md and "数据与切点提示" in md

    js = client.get(f"/api/plans/{pid}/export?format=json").json()
    assert js["plan"]["thresholds"] == {"min_union_yield_pct": 99.0}
    jchk = js["result"]["threshold_checks"]
    assert jchk["all_passed"] is False
    assert any(i["code"] == "out_of_range" for i in js["result"]["issues"])
