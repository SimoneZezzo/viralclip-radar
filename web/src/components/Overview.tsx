import type { RankingRun } from "../api.ts";
import { formatNumber, formatPoolDay } from "../format.ts";

export function Overview({ run }: { run?: RankingRun }) {
  const items: [string, string][] = [
    ["Cutoff", run ? run.cutoff_minutes + " min" : "—"],
    ["Method", run ? (run.method === "baseline" ? "Baseline" : "Simulated model") : "—"],
    ["Clips in pool", run ? formatNumber(run.pool_size) : "—"],
    ["Pool date", run ? formatPoolDay(run.pool_day) : "—"],
  ];
  return (
    <section
      className="mb-[18px] grid grid-cols-4 rounded-xl border border-hairline bg-surface-1 max-sm:mb-3 max-sm:grid-cols-2"
      aria-label="Ranking details"
    >
      {items.map(([label, value], index) => (
        <div
          key={label}
          className={[
            "min-w-0 px-[17px] py-3",
            index > 0 ? "border-l border-hairline" : "",
            index === 2 ? "max-sm:border-l-0" : "",
            index >= 2 ? "max-sm:border-t max-sm:border-hairline" : "",
          ].join(" ")}
        >
          <span className="mb-[3px] block text-[0.76rem] text-ink-subtle">{label}</span>
          <strong className="block text-[0.92rem] font-semibold tabular-nums">{value}</strong>
        </div>
      ))}
    </section>
  );
}
