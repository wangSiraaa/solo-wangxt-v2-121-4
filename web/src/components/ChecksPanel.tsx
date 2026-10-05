import type { EvalResult } from "../types";
import { g } from "../format";

function fmt(v: number | null | undefined, d = 2) {
  return v === null || v === undefined || Number.isNaN(v) ? "—" : v.toFixed(d);
}

/**
 * 课程核对阈值结果：每项实际值 + 通过状态 + 合格区间。
 * 与 IssuesPanel 相互独立——越界切点等原始提示照常同时展示。
 */
export default function ChecksPanel({ result }: { result: EvalResult }) {
  const checks = result.threshold_checks;
  if (!checks) return null;
  const hasConfig = checks.configured_keys.length > 0;

  return (
    <section className="checks">
      <h3>② 课程核对阈值</h3>
      {!hasConfig ? (
        <p className="ok-line">未设置核对阈值，不做通过判定（阈值仅教学判读，不影响产率计算）。</p>
      ) : (
        <>
          <table className="check-table">
            <thead>
              <tr><th>核对项</th><th>合格区间</th><th>实际体积产率 %</th><th>状态</th></tr>
            </thead>
            <tbody>
              {checks.items.map((it) => {
                if (!it.configured) {
                  return (
                    <tr key={it.key} className="muted">
                      <td>{it.label}</td><td>未设置</td><td>{fmt(it.actual_pct)}</td>
                      <td>不评</td>
                    </tr>
                  );
                }
                return (
                  <tr key={it.key} className={it.passed ? "pass" : "fail"}>
                    <td title={it.note}>{it.label}</td>
                    <td className="interval">{it.interval_pct}</td>
                    <td className="actual">{fmt(it.actual_pct)}</td>
                    <td>
                      <span className={`badge ${it.passed ? "pass" : "fail"}`}>
                        {it.passed ? "✅ 通过" : "❌ 不通过"}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className={`check-summary ${checks.all_passed ? "pass" : "fail"}`}>
            总体判定：{checks.all_passed ? "✅ 全部通过" : "❌ 存在不通过项（按课程标准需讨论调整）"}
          </p>
          <p className="hint">
            {checks.notice} 实际范围：{g(result.applicable_range.temp_c[0])}~
            {g(result.applicable_range.temp_c[1])} ℃；范围内缺口只计实测范围内有数据的缺口段。
          </p>
        </>
      )}
    </section>
  );
}
