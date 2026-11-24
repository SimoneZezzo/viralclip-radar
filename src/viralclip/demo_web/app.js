const byId = (id) => document.getElementById(id);
const game = byId("game");
const list = byId("ranking");
const details = byId("details");
const copy = byId("copy");
const open = byId("open");
const availability = byId("availability");
const number = new Intl.NumberFormat("en-US");
const date = new Intl.DateTimeFormat("en-GB", {
  day: "numeric", month: "short", year: "numeric", timeZone: "UTC",
});
const clock = new Intl.DateTimeFormat("en-GB", {
  hour: "2-digit", minute: "2-digit", timeZone: "UTC", hourCycle: "h23",
});
let run;
let selected;

function linkNote(clip) {
  return clip.twitch_url
    ? "Copy the link, then paste it into your editor."
    : "Synthetic clip: there is no Twitch page to open. Real rankings link to the clip on Twitch.";
}

function selectClip(clip, button) {
  selected = clip;
  for (const candidate of list.querySelectorAll("button")) {
    candidate.setAttribute("aria-pressed", String(candidate === button));
  }
  byId("preview").className = "preview scene-" + clip.scene;
  byId("selected-rank").textContent = clip.rank === null ? "Unranked" : "Rank " + clip.rank;
  byId("clip-title").textContent = clip.title;
  byId("clip-channel").textContent = "@" + clip.channel;
  byId("duration").textContent = clip.duration + " s";
  byId("version").textContent = run.score_version;
  byId("clip-score").textContent = clip.score === null ? "Unavailable" : clip.score + " / 100";
  byId("prediction").textContent = clock.format(new Date(clip.prediction_at)) + " UTC";
  byId("clip-link").textContent = clip.url;
  if (clip.twitch_url) {
    open.href = clip.twitch_url;
    open.removeAttribute("aria-disabled");
  } else {
    open.removeAttribute("href");
    open.setAttribute("aria-disabled", "true");
  }
  availability.textContent = linkNote(clip);
  details.hidden = false;
}

function span(className, content) {
  const node = document.createElement("span");
  node.className = className;
  node.textContent = content;
  return node;
}

function renderEditors(editors) {
  byId("editors").replaceChildren(...editors.map((editor) => {
    const item = document.createElement("li");
    const link = document.createElement("a");
    link.className = "secondary";
    link.href = editor.url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = editor.name;
    item.append(link);
    return item;
  }));
}

function renderRanking(data) {
  run = data.run;
  const baseline = run.method === "baseline";
  byId("cutoff").textContent = run.cutoff_minutes + " min";
  byId("method").textContent = baseline ? "Baseline" : "Simulated model";
  byId("pool").textContent = number.format(run.pool_size);
  byId("pool-day").textContent = date.format(new Date(run.pool_day + "T00:00:00Z")) + " (UTC)";
  byId("ranking-note").textContent = baseline
    ? "This game uses a baseline. Scores show relative position within the selected pool."
    : "Scores are relative to the selected pool. Clips with insufficient data stay unranked.";
  renderEditors(data.editors);
  list.replaceChildren();
  for (const clip of data.predictions) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = clip.score === null ? "rank-row is-missing" : "rank-row";
    button.setAttribute("aria-pressed", "false");
    button.setAttribute("aria-controls", "details");
    const text = span("rank-copy", "");
    text.append(span("rank-title", clip.title), span("rank-channel", "@" + clip.channel));
    const thumb = span("thumb scene-" + clip.scene, "");
    thumb.setAttribute("aria-hidden", "true");
    button.append(
      span("rank-number", clip.rank ?? "—"), thumb, text,
      span("rank-score", clip.score === null ? "—" : number.format(clip.score)),
    );
    button.addEventListener("click", () => {
      selectClip(clip, button);
      if (matchMedia("(max-width: 665px)").matches) details.scrollIntoView({ block: "start" });
    });
    item.append(button);
    list.append(item);
  }
  if (data.predictions.length) selectClip(data.predictions[0], list.querySelector("button"));
}

async function loadRanking(gameId) {
  game.disabled = true;
  byId("page-error").hidden = true;
  selected = undefined;
  details.hidden = true;
  try {
    const query = gameId ? "?" + new URLSearchParams({ game_id: gameId }) : "";
    const response = await fetch("/api/ranking" + query);
    if (!response.ok) throw new Error("Ranking unavailable.");
    const data = await response.json();
    game.replaceChildren(...data.games.map((option) => new Option(option.name, option.id)));
    game.value = data.run.game_id;
    renderRanking(data);
  } catch {
    list.replaceChildren();
    byId("page-error").textContent = "Could not load the ranking. Refresh the page to try again.";
    byId("page-error").hidden = false;
  } finally {
    game.disabled = false;
  }
}

async function copyLink() {
  if (!selected) return;
  try {
    await navigator.clipboard.writeText(selected.url);
    availability.textContent = "Link copied. " + linkNote(selected);
  } catch {
    availability.textContent = "Could not copy automatically. Select the clip link above and copy it.";
  }
}

game.addEventListener("change", () => loadRanking(game.value));
copy.addEventListener("click", copyLink);
open.addEventListener("click", (event) => {
  if (open.getAttribute("aria-disabled") === "true") event.preventDefault();
});
loadRanking();
