"""请求/响应 Pydantic 模型。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ---- 试验 ----
class CurvePointIn(BaseModel):
    temp_c: float = Field(..., description="馏出温度 ℃（换算到常压）")
    recovered_pct: float = Field(..., ge=0, le=100, description="累积回收体积百分比")


class DensityRowIn(BaseModel):
    temp_c: float = Field(..., description="馏出段代表温度/段中点 ℃")
    density_g_cm3: float = Field(..., gt=0, le=2.5)


class ExperimentIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    sample_id: str | None = Field(default=None, max_length=100)
    feed_density_g_cm3: float = Field(..., gt=0, le=2.5)
    residue_density_g_cm3: float | None = Field(default=None, gt=0, le=2.5)
    conditions: dict = Field(default_factory=dict)
    points: list[CurvePointIn] = Field(min_length=2)
    density_rows: list[DensityRowIn] = Field(default_factory=list)
    notes: str | None = None

    @field_validator("points")
    @classmethod
    def _points_not_empty(cls, v: list[CurvePointIn]) -> list[CurvePointIn]:
        if len(v) < 2:
            raise ValueError("蒸馏曲线至少需要 2 个点")
        return v


class ExperimentOut(BaseModel):
    id: int
    name: str
    sample_id: str | None
    feed_density_g_cm3: float
    residue_density_g_cm3: float | None = None
    conditions: dict
    points: list[dict]
    density_rows: list[dict]
    notes: str | None

    model_config = {"from_attributes": True}


# ---- 方案 ----
class CutIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    start_temp_c: float
    end_temp_c: float


class ThresholdsIn(BaseModel):
    """课程统一核对阈值（最多三项，均为体积产率 %）；整体或单项可缺省。

    仅用于教学判读，不改变曲线与产率计算。
    """

    min_union_yield_pct: float | None = Field(default=None, ge=0, le=100)
    max_overlap_pct: float | None = Field(default=None, ge=0, le=100)
    max_in_range_gap_pct: float | None = Field(default=None, ge=0, le=100)

    def as_dict(self) -> dict[str, float]:
        """丢弃未设置项；旧方案（无 thresholds 字段）得到空 dict。"""
        return {
            k: v for k, v in (
                ("min_union_yield_pct", self.min_union_yield_pct),
                ("max_overlap_pct", self.max_overlap_pct),
                ("max_in_range_gap_pct", self.max_in_range_gap_pct),
            ) if v is not None
        }


class PlanIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    basis: Literal["volume", "mass"] = "volume"
    cuts: list[CutIn] = Field(min_length=1)
    loss_pct: float = Field(default=0.0, ge=0, le=100)
    thresholds: ThresholdsIn | None = None


class PlanOut(BaseModel):
    id: int
    experiment_id: int
    name: str
    basis: str
    cuts: list[dict]
    loss_pct: float
    # 旧库行该列可能为 NULL：读取时按“未设置阈值”（{}）处理
    thresholds: dict = Field(default_factory=dict)
    result_snapshot: dict | None = None

    model_config = {"from_attributes": True}

    @field_validator("thresholds", mode="before")
    @classmethod
    def _none_thresholds_as_empty(cls, v):
        return {} if v is None else v
