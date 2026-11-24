import { forwardRef, useState } from "react";
import type { Editor, Prediction, RankingRun } from "../api.ts";
import { formatClock } from "../format.ts";

interface Props {
  clip: Prediction;
  run: RankingRun;
  editors: Editor[];
  synthetic: boolean;
}

function linkNote(clip: Prediction) {
  return clip.twitch_url
    ? "Copy the link, then paste it into your editor."
    : "Synthetic clip: there is no Twitch page to open. Real rankings link to the clip on Twitch.";
}

// Remount with key={clip.clip_id} so the status line resets for each clip.
export const ClipDetails = forwardRef<HTMLElement, Props>(function ClipDetails(
  { clip, run, editors, synthetic },
  ref,
) {
  const [status, setStatus] = useState(() => linkNote(clip));

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(clip.url);
      setStatus("Link copied. " + linkNote(clip));
    } catch {
      setStatus("Could not copy automatically. Select the clip link above and copy it.");
    }
  }

  const record: [string, string][] = [
    ["Version", run.score_version],
    ["Potential score", clip.score === null ? "Unavailable" : clip.score + " / 100"],
    ["Clip cutoff", formatClock(clip.prediction_at)],
    ["Clip link", clip.url],
  ];

  return (
    <section
      id="details"
      ref={ref}
      className="min-w-0 rounded-xl border border-hairline bg-surface-1"
      aria-labelledby="details-title"
    >
      <div className="flex min-h-[58px] items-center justify-between gap-2.5 border-b border-hairline px-[17px] py-[13px]">
        <h2 id="details-title" className="m-0 text-[1.06rem] font-semibold tracking-[-0.025em]">
          Selected clip
        </h2>
        <span className="text-right text-[0.75rem] text-ink-subtle">
          {clip.rank === null ? "Unranked" : "Rank " + clip.rank}
        </span>
      </div>
      <div className="p-[13px]">
        <div
          className={`artwork scene-${clip.scene} relative isolate aspect-video overflow-hidden rounded-lg before:absolute before:inset-0 before:-z-10 before:bg-[linear-gradient(transparent_50%,#101110bf)]`}
        >
          {synthetic && (
            <span className="absolute bottom-2 left-2 rounded bg-[#131612e8] px-2 py-1 text-[0.73rem] text-white">
              Synthetic preview
            </span>
          )}
        </div>
        <div className="flex items-start justify-between gap-[9px] px-px py-[13px]">
          <div>
            <h3 className="m-0 text-[1.14rem] font-semibold tracking-[-0.035em] [overflow-wrap:anywhere]">
              {clip.title}
            </h3>
            <p className="m-0 mt-1 text-[0.79rem] text-ink-subtle">@{clip.channel}</p>
          </div>
          <span className="whitespace-nowrap rounded-[5px] bg-[#242820] px-[7px] py-1 text-[0.77rem]">
            {clip.duration} s
          </span>
        </div>
        <dl className="m-0 mb-[13px] grid gap-[5px] rounded-[7px] border border-hairline p-2.5">
          {record.map(([label, value]) => (
            <div key={label} className="flex items-baseline justify-between gap-2.5">
              <dt className="shrink-0 text-[0.76rem] text-ink-subtle">{label}</dt>
              <dd className="m-0 text-right font-mono text-[0.74rem] [overflow-wrap:anywhere]">
                {value}
              </dd>
            </div>
          ))}
        </dl>
        <div className="flex flex-wrap items-stretch gap-[7px]">
          <button type="button" className="button-primary cursor-pointer" onClick={copyLink}>
            Copy clip link
          </button>
          {clip.twitch_url ? (
            <a
              className="button-secondary"
              href={clip.twitch_url}
              target="_blank"
              rel="noopener noreferrer"
            >
              Open on Twitch
            </a>
          ) : (
            // A disabled button, not a link without href: assistive technology announces it.
            <button type="button" className="button-secondary" disabled>
              Open on Twitch
            </button>
          )}
        </div>
        <p
          className="my-2 text-[0.76rem] leading-[1.4] text-ink-subtle"
          role="status"
          aria-live="polite"
        >
          {status}
        </p>
        <section className="border-t border-hairline pt-[11px]" aria-labelledby="editors-title">
          <h4 id="editors-title" className="m-0 text-[0.86rem] font-semibold tracking-[-0.02em]">
            Edit in your own editor
          </h4>
          <p className="m-0 mt-1.5 text-[0.76rem] leading-[1.4] text-ink-subtle">
            Paste the clip link into the editor you use. ViralClip Radar does not download, upload
            or edit video, and you choose and pay for the editor.
          </p>
          <ul className="m-0 mt-[9px] flex list-none flex-wrap gap-[7px] p-0" aria-label="External editors">
            {editors.map((editor) => (
              <li key={editor.name}>
                <a
                  className="button-secondary"
                  href={editor.url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {editor.name}
                </a>
              </li>
            ))}
          </ul>
          <p className="m-0 mt-1.5 text-[0.76rem] leading-[1.4] text-ink-subtle">
            Ask the creator before you publish an edit.
          </p>
        </section>
      </div>
    </section>
  );
});
