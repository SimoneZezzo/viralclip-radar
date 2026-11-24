import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { fetchRanking, type Prediction } from "./api.ts";
import { ClipDetails } from "./components/ClipDetails.tsx";
import { Overview } from "./components/Overview.tsx";
import { RankingPanel } from "./components/RankingPanel.tsx";
import { TopBar } from "./components/TopBar.tsx";

export default function App() {
  const [gameId, setGameId] = useState<string>();
  const [selectedId, setSelectedId] = useState<string>();
  const details = useRef<HTMLElement>(null);
  const ranking = useQuery({
    queryKey: ["ranking", gameId ?? "default"],
    queryFn: () => fetchRanking(gameId),
  });
  const data = ranking.data;
  const predictions = data?.predictions ?? [];
  // A clip from another game is not in this pool, so selection falls back to the top row.
  const selected = predictions.find((clip) => clip.clip_id === selectedId) ?? predictions[0];

  function select(clip: Prediction) {
    setSelectedId(clip.clip_id);
    if (window.matchMedia("(max-width: 665px)").matches) {
      details.current?.scrollIntoView({ block: "start" });
    }
  }

  return (
    <>
      <TopBar synthetic={data?.synthetic ?? true} />
      <main className="mx-auto max-w-[1264px] px-[clamp(16px,4vw,48px)] pb-12">
        <section
          className="mt-[42px] mb-[26px] flex items-end justify-between gap-[18px] max-sm:mt-[25px] max-sm:mb-4 max-sm:flex-col max-sm:items-stretch"
          aria-labelledby="page-title"
        >
          <div>
            <h1
              id="page-title"
              className="m-0 text-[clamp(2.3rem,6vw,4rem)] leading-none font-bold tracking-[-0.075em]"
            >
              Twitch Shortlist
            </h1>
            <p className="m-0 mt-3 text-[0.98rem] text-ink-subtle">
              Rank clips by game, then edit the best ones in your own editor.
            </p>
          </div>
          <div className="w-[min(205px,100%)] flex-none max-sm:w-full">
            <label htmlFor="game" className="mb-1.5 ml-0.5 block text-[0.8rem] text-ink-subtle">
              Game
            </label>
            <select
              id="game"
              className="min-h-11 w-full cursor-pointer rounded-lg border border-[#46513a] bg-surface-1 p-2.5 text-ink"
              disabled={ranking.isFetching || !data}
              value={data?.run.game_id ?? ""}
              onChange={(event) => setGameId(event.target.value)}
            >
              {data ? (
                data.games.map((game) => (
                  <option key={game.id} value={game.id}>
                    {game.name}
                  </option>
                ))
              ) : (
                <option value="">Loading…</option>
              )}
            </select>
          </div>
        </section>
        {ranking.isError && (
          <p className="my-[7px] p-2.5 text-danger" role="alert">
            Could not load the ranking. Refresh the page to try again.
          </p>
        )}
        <Overview run={data?.run} />
        <div className="grid grid-cols-[1.36fr_1fr] items-start gap-[18px] max-md:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] max-md:gap-3 max-sm:grid-cols-[minmax(0,1fr)]">
          <RankingPanel
            run={data?.run}
            predictions={predictions}
            selectedId={selected?.clip_id}
            onSelect={select}
          />
          {data && selected && (
            <ClipDetails
              key={selected.clip_id}
              ref={details}
              clip={selected}
              run={data.run}
              editors={data.editors}
              synthetic={data.synthetic}
            />
          )}
        </div>
      </main>
    </>
  );
}
