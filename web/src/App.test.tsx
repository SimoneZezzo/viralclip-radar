import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Prediction, Ranking } from "./api.ts";
import App from "./App.tsx";

function clip(overrides: Partial<Prediction>): Prediction {
  return {
    prediction_id: 1,
    clip_id: "demo-1",
    prediction_at: "2026-11-22T19:04:00.000000Z",
    scored_at: "2026-11-24T10:00:00.000000Z",
    feature_status: "eligible",
    score: 100,
    rank: 1,
    latest_observed_at: "2026-11-22T18:56:00.000000Z",
    observation_ids: [1],
    title: "Overpass getaway",
    channel: "neon_driver",
    duration: 28,
    scene: 0,
    url: "https://example.invalid/synthetic-clips/demo-1",
    twitch_url: null,
    ...overrides,
  };
}

function ranking(gameId: string, method: "baseline" | "simulated_model", clips: Prediction[]) {
  return {
    synthetic: true,
    games: [
      { id: "1867279146", name: "GTA VI" },
      { id: "32982", name: "GTA V" },
    ],
    editors: [
      { name: "external editor", url: "https://example.invalid/editor/" },
      { name: "CapCut", url: "https://www.capcut.com/" },
    ],
    run: {
      run_id: "fixture:" + gameId,
      game_id: gameId,
      pool_day: "2026-11-22",
      cutoff_minutes: 60,
      scored_at: "2026-11-24T10:00:00.000000Z",
      source_watermark: "2026-11-22T19:28:00.000000Z",
      score_version: method === "baseline" ? "baseline:latest_views:v1" : "fixture:potential:v3",
      model_status: method === "baseline" ? "not_trained_yet" : "simulated",
      pool_size: clips.length,
      method,
    },
    predictions: clips,
  } satisfies Ranking;
}

const gtaVi = ranking("1867279146", "simulated_model", [
  clip({}),
  clip({ prediction_id: 2, clip_id: "demo-2", title: "One last lap", score: null, rank: null }),
]);
const gtaV = ranking("32982", "baseline", [
  clip({ prediction_id: 3, clip_id: "v-1", title: "Rooftop landing", channel: "roof_runner" }),
]);

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  );
}

describe("Twitch Shortlist", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const body = String(input).includes("game_id=32982") ? gtaV : gtaVi;
      return new Response(JSON.stringify(body), { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("matchMedia", () => ({ matches: false }));
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("ranks clips, selects the top clip and shows missing scores as a dash", async () => {
    renderApp();
    const list = await screen.findByRole("list", { name: "Clips ranked by score" });
    const rows = await within(list).findAllByRole("button");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveAttribute("aria-pressed", "true");
    expect(within(rows[1]).getAllByText("—")).toHaveLength(2);
    expect(screen.getByText("Simulated model")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Overpass getaway" })).toBeInTheDocument();
    expect(screen.getByText("Local demo · Synthetic data")).toBeInTheDocument();
  });

  it("disables Open on Twitch for synthetic clips and says why", async () => {
    renderApp();
    const open = await screen.findByRole("button", { name: "Open on Twitch" });
    expect(open).toBeDisabled();
    expect(screen.queryByRole("link", { name: "Open on Twitch" })).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent("Synthetic clip: there is no Twitch page");
  });

  it("copies the clip link and reports the result", async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
    renderApp();
    await user.click(await screen.findByRole("button", { name: "Copy clip link" }));
    expect(writeText).toHaveBeenCalledWith("https://example.invalid/synthetic-clips/demo-1");
    expect(screen.getByRole("status")).toHaveTextContent("Link copied.");
  });

  it("explains a failed copy instead of failing silently", async () => {
    const user = userEvent.setup();
    vi.spyOn(navigator.clipboard, "writeText").mockRejectedValue(new Error("denied"));
    renderApp();
    await user.click(await screen.findByRole("button", { name: "Copy clip link" }));
    expect(screen.getByRole("status")).toHaveTextContent("Could not copy automatically");
  });

  it("lists external editors as plain links that open safely", async () => {
    renderApp();
    const editors = await screen.findByRole("list", { name: "External editors" });
    const links = within(editors).getAllByRole("link");
    expect(links.map((link) => link.textContent)).toEqual(["external editor", "CapCut"]);
    for (const link of links) {
      expect(link).toHaveAttribute("target", "_blank");
      expect(link).toHaveAttribute("rel", "noopener noreferrer");
    }
  });

  it("loads another game and labels a baseline as a baseline", async () => {
    const user = userEvent.setup();
    renderApp();
    const picker = await screen.findByRole("combobox", { name: "Game" });
    await screen.findByText("Simulated model");
    await user.selectOptions(picker, "32982");
    expect(await screen.findByText("Baseline")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Rooftop landing" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenLastCalledWith("/api/ranking?game_id=32982");
  });

  it("shows an error when the ranking cannot load", async () => {
    fetchMock.mockResolvedValue(new Response("", { status: 500 }));
    renderApp();
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load the ranking");
  });
});
