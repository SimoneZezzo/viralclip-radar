import { makeVideo } from "/media.js";

const byId = (id) => document.getElementById(id);
const game = byId("game");
const list = byId("ranking");
const details = byId("details");
const edit = byId("edit");
const download = byId("download");
const play = byId("play");
const fileInput = byId("file");
const allowed = byId("allowed");
const preview = byId("preview");
const video = byId("video");
const exportLink = byId("export");
const job = byId("job");
const number = new Intl.NumberFormat("en-US");
const date = new Intl.DateTimeFormat("en-GB", {
  day: "numeric", month: "short", year: "numeric", timeZone: "UTC",
});
const clock = new Intl.DateTimeFormat("en-GB", {
  hour: "2-digit", minute: "2-digit", timeZone: "UTC", hourCycle: "h23",
});
let run;
let selected;
let active;
let resultUrl;
const renderFailures = new Set();

function showJob(message, isError = false) {
  byId("job-section").hidden = !message;
  job.textContent = message;
  job.classList.toggle("error", isError);
}

function clearPreview() {
  video.pause();
  video.removeAttribute("src");
  video.load();
  video.hidden = true;
  play.hidden = false;
  preview.classList.remove("has-video");
  exportLink.hidden = true;
  exportLink.removeAttribute("href");
  if (resultUrl) URL.revokeObjectURL(resultUrl);
  resultUrl = undefined;
}

function fileSource() {
  return selected?.media.accept_file && allowed.checked ? fileInput.files[0] : undefined;
}

function updateActions() {
  if (!selected) return;
  edit.disabled = Boolean(active) || !(selected.media.edit_original || fileSource());
  download.disabled = Boolean(active) || !selected.media.download;
  play.disabled = Boolean(active) || !(selected.media.edit_original || fileSource());
  let message = "Download and editing are simulated in this demo.";
  if (selected.scenario === "file") {
    message = "Twitch download is unavailable for this clip. You can edit a copy you have permission to use.";
  } else if (selected.scenario === "blocked") {
    message = "Download and editing are unavailable because creator permission is missing.";
  }
  byId("availability").textContent = message;
}

function selectClip(clip, button) {
  active?.abort();
  active = undefined;
  clearPreview();
  showJob("");
  selected = clip;
  for (const candidate of list.querySelectorAll("button")) {
    candidate.setAttribute("aria-pressed", String(candidate === button));
  }
  fileInput.value = "";
  allowed.checked = false;
  byId("file-panel").open = false;
  byId("file-panel").hidden = !clip.media.accept_file;
  preview.className = "preview scene-" + clip.scene;
  byId("selected-rank").textContent = clip.rank === null ? "Unranked" : "Rank " + clip.rank;
  byId("clip-title").textContent = clip.title;
  byId("clip-channel").textContent = "@" + clip.channel;
  byId("duration").textContent = clip.duration + " s";
  byId("version").textContent = run.score_version;
  byId("clip-score").textContent = clip.score === null ? "Unavailable" : clip.score + " / 100";
  byId("prediction").textContent = clock.format(new Date(clip.prediction_at)) + " UTC";
  details.hidden = false;
  updateActions();
}

function span(className, content) {
  const node = document.createElement("span");
  node.className = className;
  node.textContent = content;
  return node;
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
  list.replaceChildren();
  for (const clip of data.predictions) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = clip.score === null ? "rank-row is-missing" : "rank-row";
    button.setAttribute("aria-pressed", "false");
    button.setAttribute("aria-controls", "details");
    const copy = span("rank-copy", "");
    copy.append(span("rank-title", clip.title), span("rank-channel", "@" + clip.channel));
    const thumb = span("thumb scene-" + clip.scene, "");
    thumb.setAttribute("aria-hidden", "true");
    button.append(
      span("rank-number", clip.rank ?? "—"), thumb, copy,
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
  active?.abort();
  active = undefined;
  selected = undefined;
  clearPreview();
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

function downloadFile(result, name) {
  const url = URL.createObjectURL(result.blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name + "." + result.extension;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function runMedia(action) {
  if (!selected || active) return;
  const clip = selected;
  const file = action !== "download" ? fileSource() : undefined;
  if (action === "download" && !clip.media.download) return;
  if (action !== "download" && !clip.media.edit_original && !file) return;
  const controller = new AbortController();
  active = controller;
  clearPreview();
  updateActions();
  showJob(action === "edit" ? "Creating the sample edit…" : "Preparing the video…");
  try {
    const result = await makeVideo(clip, {
      vertical: action === "edit", file, signal: controller.signal,
    });
    if (active !== controller) return;
    if (action === "edit" && clip.scenario === "render_error" && !renderFailures.has(clip.clip_id)) {
      renderFailures.add(clip.clip_id);
      throw new Error("The sample render failed. Start the edit again to retry.");
    }
    if (action === "download") {
      downloadFile(result, clip.clip_id + "-synthetic-original");
      showJob("Sample download ready.");
    } else {
      resultUrl = URL.createObjectURL(result.blob);
      video.src = resultUrl;
      play.hidden = true;
      video.hidden = false;
      preview.classList.add("has-video");
      if (action === "edit") {
        exportLink.href = resultUrl;
        exportLink.download = clip.clip_id + "-sample-short." + result.extension;
        exportLink.hidden = false;
        showJob("Sample export ready · 9:16 · sample captions");
      } else {
        showJob("");
        video.play().catch(() => {});
      }
    }
  } catch (error) {
    if (active === controller) showJob(error.message || "Video unavailable.", true);
  } finally {
    if (active === controller) {
      active = undefined;
      updateActions();
    }
  }
}

game.addEventListener("change", () => loadRanking(game.value));
edit.addEventListener("click", () => runMedia("edit"));
download.addEventListener("click", () => runMedia("download"));
play.addEventListener("click", () => runMedia("preview"));
fileInput.addEventListener("change", () => {
  allowed.checked = false;
  updateActions();
});
allowed.addEventListener("change", updateActions);
loadRanking();
