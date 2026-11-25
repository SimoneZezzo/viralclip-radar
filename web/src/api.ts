// Shared view of the FastAPI demo and the static ranking files.

export interface Game {
  id: string;
  name: string;
}

export interface Editor {
  name: string;
  url: string;
}

export interface RankingRun {
  game_id: string;
  pool_day: string;
  cutoff_minutes: number;
  scored_at: string;
  score_version: string;
  model_status: string;
  pool_size: number;
  method?: "baseline" | "simulated_model";
  method_label?: string;
  published_at?: string;
}

export interface Prediction {
  clip_id: string;
  prediction_at: string;
  score: number | null;
  rank: number | null;
  title: string | null;
  channel?: string;
  duration?: number;
  scene?: number;
  url: string | null;
  twitch_url: string | null;
}

export interface Ranking {
  synthetic: boolean;
  games: Game[];
  editors: Editor[];
  run: RankingRun;
  predictions: Prediction[];
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) throw new Error("Ranking unavailable.");
  return response.json();
}

interface PublishedGame extends RankingRun {
  published_at: string;
  method_label: string;
  synthetic: boolean;
  clips: Omit<Prediction, "twitch_url">[];
}

function twitchLink(stored: string | null): string | null {
  if (!stored) return null;
  try {
    const url = new URL(stored);
    const twitch = ["clips.twitch.tv", "www.twitch.tv", "twitch.tv"].includes(url.hostname);
    if (twitch && url.protocol === "https:" && !url.username && !url.password) return stored;
  } catch {
    // A malformed stored link cannot be opened.
  }
  return null;
}

export async function fetchRanking(gameId?: string): Promise<Ranking> {
  if (import.meta.env.VITE_STATIC_DATA === "1") {
    const base = import.meta.env.BASE_URL + "rankings/";
    const { games } = await getJson<{ games: Game[] }>(base + "index.json");
    const id = gameId ?? games[0]?.id;
    if (!id || !/^[0-9]+$/.test(id) || !games.some((game) => game.id === id)) {
      throw new Error("Game unavailable.");
    }
    const { clips, synthetic, ...run } = await getJson<PublishedGame>(base + id + ".json");
    if (run.game_id !== id) throw new Error("Wrong game in ranking.");
    return {
      games,
      synthetic,
      run,
      editors: [
        { name: "external editor", url: "https://example.invalid/editor/" },
        { name: "CapCut", url: "https://www.capcut.com/" },
        { name: "external editor", url: "https://example.invalid/editor/" },
        { name: "external editor", url: "https://example.invalid/editor/" },
      ],
      predictions: clips.map((clip) => ({
        ...clip,
        twitch_url: synthetic ? null : twitchLink(clip.url),
      })),
    };
  }
  const query = gameId ? "?" + new URLSearchParams({ game_id: gameId }).toString() : "";
  return getJson<Ranking>("/api/ranking" + query);
}
