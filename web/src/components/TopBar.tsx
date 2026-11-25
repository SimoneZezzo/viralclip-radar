export function TopBar({ synthetic }: { synthetic: boolean }) {
  return (
    <header className="border-b border-hairline bg-chrome">
      <div className="mx-auto flex min-h-16 max-w-[1264px] items-center justify-between gap-3 px-[clamp(16px,4vw,48px)]">
        <a
          className="inline-flex items-center gap-[11px] text-[1.06rem] font-bold tracking-[-0.03em] text-ink no-underline max-xs:gap-1.5 max-xs:text-[0.88rem]"
          href={import.meta.env.BASE_URL}
          aria-label="ViralClip Radar"
        >
          <span
            className="relative grid size-[25px] place-items-center rounded-full border border-accent-line before:absolute before:inset-[5px] before:rounded-full before:border before:border-accent-line"
            aria-hidden="true"
          >
            <i className="size-[5px] rounded-full bg-accent shadow-[7px_-6px_0_-1px_var(--color-accent)]" />
          </span>
          <span>
            ViralClip<span className="text-accent"> Radar</span>
          </span>
        </a>
        {synthetic && (
          <span className="inline-flex items-center gap-2 rounded-[20px] border border-hairline-strong px-2.5 py-1.5 text-[0.76rem] text-ink-muted max-xs:gap-[5px] max-xs:px-1.5 max-xs:text-[0.64rem]">
            <i className="size-1.5 rounded-full bg-accent" />
            {import.meta.env.VITE_STATIC_DATA === "1" ? "Synthetic data" : "Local demo · Synthetic data"}
          </span>
        )}
      </div>
    </header>
  );
}
