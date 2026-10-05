import type { PlanThresholds, CheckKey } from "../types";

interface Props {
  thresholds: PlanThresholds;
  onChange: (next: PlanThresholds) => void;
}

const ROWS: { key: CheckKey; label: string; hint: string }[] = [
  {
    key: "min_union_yield_pct",
    label: "最低切出体积产率 %",
    hint: "馏分并集（去重叠、范围内）≥",
  },
  {
    key: "max_overlap_pct",
    label: "最大重叠体积产率 %",
    hint: "重叠体积产率 ≤",
  },
  {
    key: "max_in_range_gap_pct",
    label: "最大范围内缺口体积产率 %",
    hint: "范围内缺口（前+中+尾）≤",
  },
];

/** 空字符串表示“未设置”；最多三项，留空即不评。 */
export default function ThresholdEditor({ thresholds, onChange }: Props) {
  const update = (key: CheckKey, raw: string) => {
    const v = raw.trim() === "" ? null : Number(raw);
    onChange({ ...thresholds, [key]: v !== null && Number.isFinite(v) ? v : null });
  };

  const val = (key: CheckKey) => {
    const v = thresholds[key];
    return v === null || v === undefined || Number.isNaN(v) ? "" : String(v);
  };

  return (
    <div className="threshold-editor">
      <div className="th-title">
        课程核对阈值（最多三项，仅教学判读）
        <span className="th-sub">不改变曲线与产率；留空 = 不评该项</span>
      </div>
      <div className="th-grid">
        {ROWS.map((r) => (
          <label key={r.key} className="th-item" title={r.label}>
            <span className="th-label">{r.label}</span>
            <span className="th-input">
              <span className="th-hint">{r.hint}</span>
              <input
                type="number"
                min={0}
                max={100}
                step={0.1}
                placeholder="未设置"
                value={val(r.key)}
                onChange={(e) => update(r.key, e.target.value)}
              />
              <span className="th-unit">%</span>
            </span>
          </label>
        ))}
      </div>
    </div>
  );
}
