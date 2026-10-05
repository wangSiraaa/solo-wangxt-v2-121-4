import type { Thresholds } from "../types";

interface Props {
  value: Thresholds;
  onChange: (t: Thresholds) => void;
}

const FIELDS: { key: keyof Thresholds; label: string; hint: string }[] = [
  {
    key: "min_union_yield_pct",
    label: "最低切出体积产率 %",
    hint: "馏分并集产率 ≥ 该值",
  },
  {
    key: "max_overlap_pct",
    label: "最大重叠体积产率 %",
    hint: "重叠量 ≤ 该值",
  },
  {
    key: "max_in_range_gap_pct",
    label: "最大范围内缺口体积产率 %",
    hint: "前+中+尾缺口合计 ≤ 该值",
  },
];

/** 阈值核对编辑器：最多三项，留空即不设置；仅教学判读，不影响产率计算。 */
export default function ThresholdEditor({ value, onChange }: Props) {
  const set = (key: keyof Thresholds, raw: string) => {
    const parsed = raw === "" ? null : parseFloat(raw);
    onChange({ ...value, [key]: parsed !== null && Number.isFinite(parsed) ? parsed : null });
  };

  return (
    <div className="editor thresholds">
      <div className="row">
        {FIELDS.map((f) => (
          <label key={f.key}>
            {f.label}
            <input
              type="number"
              step="0.1"
              min="0"
              max="100"
              placeholder="不设置"
              value={value[f.key] ?? ""}
              onChange={(e) => set(f.key, e.target.value)}
            />
            <span className="thr-hint">{f.hint}</span>
          </label>
        ))}
      </div>
      <p className="hint">
        阈值核对为教学判读：实时评估与保存方案时逐项给出实际值、通过状态与判定区间；
        不改变曲线与产率计算。留空的项不参与核对。
      </p>
    </div>
  );
}
