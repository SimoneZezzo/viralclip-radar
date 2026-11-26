import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Prediction, Ranking } from "./api.ts";
import App from "./App.tsx";

function clip(overrides: Partial<Prediction>): Prediction {
  return {
    clip_id: "demo-1",
    prediction_at: "2026-11-22T19:04:00.000000Z",
    score: 100,
    rank: 1,
    title: "Clip 1",
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
      { name: "CapCut", url: "https://www.capcut.com/" },
      { name: "Shotcut", url: "https://shotcut.org/" },
    ],
    run: {
      game_id: gameId,
      pool_day: "2026-11-22",
      cutoff_minutes: 60,
      scored_at: "2026-11-24T10:00:00.000000Z",
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
  clip({ clip_id: "demo-2", title: "One last lap", score: null, rank: null }),
]);
const gtaV = ranking("32982", "baseline", [
  clip({ clip_id: "v-1", title: "Rooftop landing", channel: "roof_runner" }),
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
    vi.unstubAllEnvs();
  });

  it("ranks clips, selects the top clip and shows missing scores as a dash", async () => {
    renderApp();
    const list = await screen.findByRole("list", { name: "Clips ranked by score" });
    const rows = await within(list).findAllByRole("button");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveAttribute("aria-pressed", "true");
    expect(within(rows[1]).getAllByText("—")).toHaveLength(2);
    expect(screen.getByText("Simulated model")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Clip 1" })).toBeInTheDocument();
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
    expect(links.map((link) => link.textContent)).toEqual(["CapCut", "Shotcut"]);
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

  it("uses the static index to select games and displays their published records", async () => {
    vi.stubEnv("VITE_STATIC_DATA", "1");
    vi.stubEnv("BASE_URL", "/portfolio/");
    const user = userEvent.setup();
    const base = "/portfolio/rankings/";
    const games = [
      { id: "42", name: "First game", file: "42-00000000000000aa.json" },
      { id: "43", name: "Second game", file: "43-00000000000000bb.json" },
    ];
    const method = "latest_views baseline · no validated model for this game";
    fetchMock.mockImplementation(async (path: string) => {
      if (path === base + "index.json") return Response.json({ games });
      const game = games.find(({ file }) => path === base + file);
      if (!game) return new Response("", { status: 404 });
      const url = game.id === "43" ? "https://clips.twitch.tv/StoredSlug" : null;
      return Response.json({
        ...gtaV.run, game_id: game.id, method_label: method, synthetic: false,
        published_at: "2026-11-25T09:00:00Z",
        clips: [{ rank: 1, score: 100, clip_id: "StoredSlug", title: null, url,
          prediction_at: "2026-11-24T10:00:00Z" }],
      });
    });
    renderApp();
    expect(await screen.findByText(method)).toBeVisible();
    expect(screen.getByText("25 Nov 2026 09:00 UTC")).toBeVisible();
    expect(screen.getByRole("heading", { name: "StoredSlug" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Copy clip link" })).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent("registry has no clip link");
    await user.selectOptions(screen.getByRole("combobox"), "43");
    expect(await screen.findByRole("link", { name: "Open on Twitch" })).toHaveAttribute(
      "href", "https://clips.twitch.tv/StoredSlug",
    );
    expect(fetchMock.mock.calls.map(([path]) => path)).toEqual([
      base + "index.json", base + games[0].file, base + "index.json", base + games[1].file,
    ]);
  });

  it("reloads the static index once when a newer publication pruned its game file", async () => {
    vi.stubEnv("VITE_STATIC_DATA", "1");
    vi.stubEnv("BASE_URL", "/");
    const indexes = [
      { games: [{ id: "42", name: "First game", file: "42-00000000000000aa.json" }] },
      { games: [{ id: "42", name: "First game", file: "42-00000000000000bb.json" }] },
    ];
    let reads = 0;
    fetchMock.mockImplementation(async (path: string) => {
      if (path === "/rankings/index.json") return Response.json(indexes[Math.min(reads++, 1)]);
      if (path !== "/rankings/42-00000000000000bb.json") return new Response("", { status: 404 });
      return Response.json({
        ...gtaV.run, game_id: "42", method_label: "Fresh method", synthetic: true,
        published_at: "2026-11-25T09:00:00Z", clips: [],
      });
    });
    renderApp();
    expect(await screen.findByText("Fresh method")).toBeVisible();
    expect(fetchMock.mock.calls.map(([path]) => path)).toEqual([
      "/rankings/index.json", "/rankings/42-00000000000000aa.json",
      "/rankings/index.json", "/rankings/42-00000000000000bb.json",
    ]);
    expect(fetchMock.mock.calls[2][1]).toEqual({ cache: "no-cache" });
  });
});
