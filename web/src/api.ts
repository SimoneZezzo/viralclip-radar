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

class NotFound extends Error {}

async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = init ? await fetch(path, init) : await fetch(path);
  if (response.status === 404) throw new NotFound("Ranking unavailable.");
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

export async function fetchRanking(gameId?: string, retried = false): Promise<Ranking> {
  if (import.meta.env.VITE_STATIC_DATA === "1") {
    const base = import.meta.env.BASE_URL + "rankings/";
    // The retry revalidates the index, so a browser cache cannot hand back the stale one.
    const index = await getJson<{ games: (Game & { file: string })[] }>(
      base + "index.json",
      retried ? { cache: "no-cache" } : undefined,
    );
    const id = gameId ?? index.games[0]?.id;
    const entry = index.games.find((game) => game.id === id);
    // Game files carry immutable, content-hashed names listed in the index.
    if (!id || !entry || !/^[0-9]+-[0-9a-f]{16}\.json$/.test(entry.file)) {
      throw new Error("Game unavailable.");
    }
    const games = index.games.map(({ id, name }) => ({ id, name }));
    let published: PublishedGame;
    try {
      published = await getJson<PublishedGame>(base + entry.file);
    } catch (error) {
      // A newer publication may have pruned the file of a stale index: reload it once.
      if (error instanceof NotFound && !retried) return fetchRanking(gameId, true);
      throw error;
    }
    const { clips, synthetic, ...run } = published;
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
