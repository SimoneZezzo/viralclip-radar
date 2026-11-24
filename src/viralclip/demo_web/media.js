const DEMO_DURATION_MS = 2400;
const FILE_DURATION_MS = 4000;
let artwork;

function loadArtwork() {
  artwork ??= new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => {
      artwork = undefined;
      reject(new Error("Anteprima sintetica indisponibile."));
    };
    image.src = "/gameplay.jpg";
  });
  return artwork;
}

async function loadVideo(file, signal) {
  const url = URL.createObjectURL(file);
  const video = document.createElement("video");
  video.muted = true;
  video.playsInline = true;
  try {
    await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error("Apertura del video scaduta.")), 8000);
      const settle = (callback) => (value) => {
        clearTimeout(timeout);
        signal.removeEventListener("abort", abort);
        callback(value);
      };
      const abort = () => settle(reject)(signal.reason);
      signal.addEventListener("abort", abort, { once: true });
      video.onloadeddata = settle(resolve);
      video.onerror = () => settle(reject)(new Error("Il browser non riesce a leggere questo video."));
      if (signal.aborted) abort();
      else video.src = url;
    });
    await video.play();
  } catch (error) {
    video.removeAttribute("src");
    video.load();
    URL.revokeObjectURL(url);
    throw error;
  }
  return {
    source: video,
    duration: Number.isFinite(video.duration)
      ? Math.min(video.duration * 1000, FILE_DURATION_MS)
      : FILE_DURATION_MS,
    release() {
      video.pause();
      video.removeAttribute("src");
      video.load();
      URL.revokeObjectURL(url);
    },
  };
}

function drawFrame(ctx, source, clip, vertical, elapsed, isLocalFile) {
  const { width, height } = ctx.canvas;
  const sourceWidth = source.videoWidth || source.width;
  const sourceHeight = source.videoHeight || source.height;
  const scale = Math.max(width / sourceWidth, height / sourceHeight) * (1 + elapsed / 50_000);
  const wide = sourceWidth * scale;
  const tall = sourceHeight * scale;
  const bias = [0.50, 0.33, 0.65, 0.23, 0.72, 0.43][clip.scene] ?? 0.50;
  ctx.drawImage(source, (width - wide) * bias, (height - tall) / 2, wide, tall);
  ctx.fillStyle = "#111510dc";
  ctx.fillRect(0, height - (vertical ? 98 : 49), width, vertical ? 98 : 49);
  ctx.textAlign = "center";
  ctx.fillStyle = "#d1f95b";
  ctx.font = "bold 13px system-ui";
  ctx.fillText(vertical ? "SOTTOTITOLI DIMOSTRATIVI" : "VIRALCLIP RADAR · VIDEO SINTETICO",
    width / 2, height - (vertical ? 66 : 30));
  ctx.fillStyle = "#ffffff";
  ctx.font = "bold 20px system-ui";
  ctx.fillText(isLocalFile ? "Anteprima del montaggio" : clip.title, width / 2,
    height - (vertical ? 35 : 8), width - 24);
}

function record(canvas, draw, duration, signal) {
  return new Promise((resolve, reject) => {
    const format = ["video/webm;codecs=vp8", "video/webm", "video/mp4"].find(
      (type) => MediaRecorder.isTypeSupported(type)
    );
    const stream = canvas.captureStream(24);
    let recorder;
    let timer;
    const chunks = [];
    function cleanup() {
      clearInterval(timer);
      stream.getTracks().forEach((track) => track.stop());
      signal.removeEventListener("abort", abort);
    }
    function abort() {
      if (recorder?.state === "recording") recorder.stop();
      cleanup();
      reject(signal.reason);
    }
    try {
      signal.throwIfAborted();
      recorder = new MediaRecorder(stream, format ? { mimeType: format } : {});
      recorder.ondataavailable = (event) => {
        if (event.data.size) chunks.push(event.data);
      };
      recorder.onstop = () => {
        cleanup();
        if (!chunks.length) {
          reject(new Error("Nessun fotogramma registrato."));
          return;
        }
        const mime = recorder.mimeType || format || "video/webm";
        resolve({ blob: new Blob(chunks, { type: mime }), extension: mime.includes("mp4") ? "mp4" : "webm" });
      };
      recorder.onerror = () => {
        cleanup();
        reject(new Error("Registrazione dell'anteprima non riuscita."));
      };
      signal.addEventListener("abort", abort, { once: true });
      draw(0);
      recorder.start();
      const start = performance.now();
      timer = setInterval(() => {
        const elapsed = performance.now() - start;
        try {
          draw(elapsed);
          if (elapsed >= duration && recorder.state === "recording") {
            clearInterval(timer);
            recorder.stop();
          }
        } catch (error) {
          reject(error);
          if (recorder.state === "recording") recorder.stop();
          cleanup();
        }
      }, 42);
    } catch (error) {
      cleanup();
      reject(error);
    }
  });
}

export async function makeVideo(clip, { vertical = false, file, signal }) {
  if (!window.MediaRecorder || !HTMLCanvasElement.prototype.captureStream) {
    throw new Error("Questo browser non supporta la creazione dell'anteprima.");
  }
  const media = file
    ? await loadVideo(file, signal)
    : { source: await loadArtwork(), duration: DEMO_DURATION_MS };
  try {
    signal.throwIfAborted();
    if (!Number.isFinite(media.duration) || media.duration <= 0) {
      throw new Error("Durata del video non disponibile.");
    }
    const canvas = document.createElement("canvas");
    canvas.width = vertical ? 360 : 640;
    canvas.height = vertical ? 640 : 360;
    const ctx = canvas.getContext("2d");
    return await record(
      canvas, (elapsed) => drawFrame(ctx, media.source, clip, vertical, elapsed, Boolean(file)),
      media.duration, signal,
    );
  } finally {
    media.release?.();
  }
}
