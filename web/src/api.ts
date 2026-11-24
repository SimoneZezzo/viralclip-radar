// Response contract of GET /api/ranking, served by src/viralclip/demo.py.

export interface Game {
  id: string;
  name: string;
}

export interface Editor {
  name: string;
  url: string;
}

export interface RankingRun {
  run_id: string;
  game_id: string;
  pool_day: string;
  cutoff_minutes: number;
  scored_at: string;
  source_watermark: string;
  score_version: string;
  model_status: string;
  pool_size: number;
  method: "baseline" | "simulated_model";
}

export interface Prediction {
  prediction_id: number;
  clip_id: string;
  prediction_at: string;
  scored_at: string;
  feature_status: string;
  score: number | null;
  rank: number | null;
  latest_observed_at: string | null;
  observation_ids: number[];
  title: string;
  channel: string;
  duration: number;
  scene: number;
  url: string;
  twitch_url: string | null;
}

export interface Ranking {
  synthetic: boolean;
  games: Game[];
  editors: Editor[];
  run: RankingRun;
  predictions: Prediction[];
}

export async function fetchRanking(gameId?: string): Promise<Ranking> {
  const query = gameId ? "?" + new URLSearchParams({ game_id: gameId }).toString() : "";
  const response = await fetch("/api/ranking" + query);
  if (!response.ok) throw new Error("Ranking unavailable.");
  return (await response.json()) as Ranking;
}
