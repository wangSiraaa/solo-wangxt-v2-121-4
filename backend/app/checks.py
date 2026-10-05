"""教学核对阈值（不参与曲线与产率计算，只对既有结果做判读）。

课程可按统一标准为方案设置最多三项核对阈值：

* ``min_union_yield_pct`` —— 最低切出体积产率（馏分**并集**、去重叠后，
  只计实测温度范围内的部分）；
* ``max_overlap_pct``     —— 最大重叠体积产率；
* ``max_in_range_gap_pct``—— 最大**范围内**缺口体积产率（前/中/尾缺口中
  落在实测温度范围内、确有回收量的部分；完全越界的“无数据”缺口天然为
  None，不计入，以免与越界提示重复判罚）。

阈值只是教学判读：不改曲线、不改 PCHIP、不改任何产率数值。
收紧/放宽阈值只会改变 ``passed`` 状态，实际值保持不变。
"""
from __future__ import annotations

from typing import Literal

CheckKey = Literal[
    "min_union_yield_pct", "max_overlap_pct", "max_in_range_gap_pct"
]

# 阈值 -> (结果取值键, 判读方向, 中文名, 教学说明)
_SPECS: dict[CheckKey, tuple[str, str, str, str]] = {
    "min_union_yield_pct": (
        "union_yield_pct", "min", "最低切出体积产率（馏分并集，去重叠）",
        "各馏分在实测温度范围内的并集体积产率不应低于该值。",
    ),
    "max_overlap_pct": (
        "overlap_pct", "max", "最大重叠体积产率",
        "同一温度段被多个馏分重复计入的体积产率不应高于该值。",
    ),
    "max_in_range_gap_pct": (
        "in_range_gap_pct", "max", "最大范围内缺口体积产率",
        "实测范围内未被任何馏分覆盖（前/中/尾）的体积产率不应高于该值；"
        "完全越界的无数据段不计入。",
    ),
}

CHECK_LABELS: dict[str, str] = {k: v[2] for k, v in _SPECS.items()}
CHECK_NOTES: dict[str, str] = {k: v[3] for k, v in _SPECS.items()}


def normalize_thresholds(raw: dict | None) -> dict[str, float]:
    """只保留三项合法阈值（0..100 的有限数），忽略其余/异常键。"""
    out: dict[str, float] = {}
    if not raw:
        return out
    for key in _SPECS:
        if key not in raw or raw[key] is None:
            continue
        try:
            v = float(raw[key])
        except (TypeError, ValueError):
            continue
        if v == v and 0.0 <= v <= 100.0:  # NaN 自比较为 False
            out[key] = v
    return out


def _in_range_gap_volume(result: dict) -> float:
    """范围内缺口体积产率：只累加落在实测范围内（volume_pct 非 None）的缺口。"""
    total = 0.0
    for g in result.get("gaps", []):
        v = g.get("volume_pct")
        if v is not None and not g.get("fully_outside_range"):
            total += float(v)
    return total


def _interval_text(direction: str, limit: float) -> str:
    return f"[{limit:g}, 100] %" if direction == "min" else f"[0, {limit:g}] %"


def evaluate_checks(result: dict, thresholds: dict | None) -> dict:
    """依据 evaluate_plan 的结果做阈值核对。

    返回 ``{"items": [...], "configured": [...], "all_passed": bool}``；
    未设置任何阈值时 items 为空、``all_passed`` 为 None（表示不评）。
    """
    th = normalize_thresholds(thresholds)
    totals = result.get("totals", {})
    values = {
        "union_yield_pct": totals.get("union_yield_pct"),
        "overlap_pct": totals.get("overlap_pct"),
        "in_range_gap_pct": round(_in_range_gap_volume(result), 4),
    }

    items: list[dict] = []
    for key, (value_key, direction, label, note) in _SPECS.items():
        actual = values[value_key]
        if key not in th:
            items.append(
                {
                    "key": key,
                    "label": label,
                    "note": note,
                    "direction": direction,
                    "threshold_pct": None,
                    "interval_pct": None,
                    "actual_pct": actual,
                    "configured": False,
                    "passed": None,  # 未设置 => 不评，既非通过也非不通过
                }
            )
            continue
        limit = th[key]
        if direction == "min":
            passed = actual is not None and actual + 1e-9 >= limit
        else:
            passed = actual is not None and actual <= limit + 1e-9
        items.append(
            {
                "key": key,
                "label": label,
                "note": note,
                "direction": direction,
                "threshold_pct": limit,
                "interval_pct": _interval_text(direction, limit),
                "actual_pct": actual,
                "configured": True,
                "passed": bool(passed),
            }
        )

    configured_items = [i for i in items if i["configured"]]
    return {
        "items": items,
        "configured_keys": [i["key"] for i in configured_items],
        # 未设置任何阈值时不评（None）；只要有一项设置就给出总判定
        "all_passed": (
            all(i["passed"] for i in configured_items)
            if configured_items else None
        ),
        "notice": (
            "核对阈值仅用于课程教学判读：不改原始曲线、PCHIP 插值与产率计算；"
            "范围外切点仍按不外推处理并单独提示。"
        ),
    }
