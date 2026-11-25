import type { Prediction, RankingRun } from "../api.ts";
import { formatNumber } from "../format.ts";

interface Props {
  run?: RankingRun;
  predictions: Prediction[];
  selectedId?: string;
  onSelect: (clip: Prediction) => void;
}

export function RankingPanel({ run, predictions, selectedId, onSelect }: Props) {
  const note = !run
    ? ""
    : run.method === "baseline"
      ? "This game uses a baseline. Scores show relative position within the selected pool."
      : "Scores are relative to the selected pool. Clips with insufficient data stay unranked.";
  return (
    <section
      className="min-w-0 rounded-xl border border-hairline bg-surface-1"
      aria-labelledby="ranking-title"
    >
      <div className="flex min-h-[58px] items-center justify-between gap-2.5 border-b border-hairline px-[17px] py-[13px]">
        <h2 id="ranking-title" className="m-0 text-[1.06rem] font-semibold tracking-[-0.025em]">
          Clip ranking
        </h2>
        <span className="text-right text-[0.75rem] text-ink-subtle">Score / 100</span>
      </div>
      <ul className="m-0 list-none space-y-[3px] p-[7px]" aria-label="Clips ranked by score">
        {predictions.map((clip) => {
          const missing = clip.score === null;
          const pressed = clip.clip_id === selectedId;
          return (
            <li key={clip.clip_id}>
              <button
                type="button"
                aria-pressed={pressed}
                aria-controls="details"
                onClick={() => onSelect(clip)}
                className={[
                  "grid min-h-[69px] w-full cursor-pointer items-center gap-3 rounded-lg border p-2 text-left text-ink max-md:gap-1.5 max-sm:min-h-[57px]",
                  clip.scene === undefined
                    ? "grid-cols-[25px_minmax(0,1fr)_auto]"
                    : "grid-cols-[25px_70px_minmax(0,1fr)_auto] max-md:grid-cols-[18px_45px_minmax(0,1fr)_auto] max-sm:grid-cols-[21px_58px_minmax(0,1fr)_auto]",
                  pressed
                    ? "border-hairline-accent bg-surface-3"
                    : "border-transparent bg-transparent hover:bg-surface-2",
                ].join(" ")}
              >
                <span className="text-center text-[0.89rem] font-bold text-[#d4dec7] tabular-nums">
                  {clip.rank ?? "—"}
                </span>
                {clip.scene !== undefined && (
                  <span
                    className={`artwork thumb scene-${clip.scene} h-[42px] rounded-[5px] max-md:h-8`}
                    aria-hidden="true"
                  />
                )}
                <span className="overflow-hidden">
                  <span className="block truncate text-[0.9rem] font-semibold">{clip.title || clip.clip_id}</span>
                  {clip.channel && (
                    <span className="mt-[3px] block truncate text-[0.77rem] text-ink-subtle">
                      @{clip.channel}
                    </span>
                  )}
                </span>
                <span
                  className={`min-w-[39px] text-center text-[0.89rem] font-bold tabular-nums ${
                    missing ? "text-ink-subtle" : "text-accent"
                  }`}
                >
                  {clip.score === null ? "—" : formatNumber(clip.score)}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
      {run && predictions.length === 0 && (
        <p className="px-4 text-ink-subtle">No clips received a score in this pool.</p>
      )}
      {note && (
        <p className="m-0 border-t border-hairline px-4 py-3 text-[0.78rem] leading-[1.45] text-ink-subtle">
          {note}
        </p>
      )}
    </section>
  );
}
