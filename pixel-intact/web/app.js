import JSZip from "https://cdn.jsdelivr.net/npm/jszip@3.10.1/+esm";
import {
  canvasToBlob,
  cropCenter,
  cropTile,
  describePlan,
  downloadBlob,
  drawPreviewWithGrid,
  enhanceCanvas,
  formatPixels,
  joinCanvases,
  loadFileToCanvas,
  outputName,
  parseTileName,
  planSlice,
  thumbnail,
} from "./processor.js";

const els = {
  drop: document.getElementById("dropzone"),
  file: document.getElementById("file-input"),
  size: document.getElementById("meta-size"),
  pixels: document.getElementById("meta-pixels"),
  fileMeta: document.getElementById("meta-file"),
  badge: document.getElementById("complete-badge"),
  tabs: [...document.querySelectorAll(".tab")],
  sliceForm: document.getElementById("slice-form"),
  enhanceForm: document.getElementById("enhance-form"),
  joinForm: document.getElementById("join-form"),
  scale: document.getElementById("scale"),
  scaleOut: document.getElementById("scale-out"),
  clarity: document.getElementById("clarity"),
  clarityOut: document.getElementById("clarity-out"),
  sharpness: document.getElementById("sharpness"),
  sharpOut: document.getElementById("sharp-out"),
  run: document.getElementById("run"),
  download: document.getElementById("download"),
  status: document.getElementById("status"),
  viewport: document.getElementById("viewport"),
  sheet: document.getElementById("tile-sheet"),
  title: document.getElementById("stage-title"),
  note: document.getElementById("stage-note"),
  joinDrop: document.getElementById("join-drop"),
  joinInput: document.getElementById("join-input"),
  joinCount: document.getElementById("join-count"),
  enhanceFirst: document.getElementById("enhance-first"),
  estimate: document.getElementById("plan-estimate"),
  presets: document.getElementById("presets"),
  useLocal: document.getElementById("use-local"),
  engine: document.getElementById("engine"),
  engineHint: document.getElementById("engine-hint"),
  exportFormat: document.getElementById("export-format"),
  livePreview: document.getElementById("live-preview"),
  loupe: document.getElementById("loupe"),
};

const state = {
  mode: "slice",
  file: null,
  source: null,
  resultCanvas: null,
  tiles: [],
  joinFiles: [],
  downloadKind: null,
  health: { lanczos: false, fsr: false },
};

let liveTimer = 0;

function setStatus(text) {
  els.status.textContent = text;
}

function showCanvas(canvas) {
  els.viewport.replaceChildren(canvas);
}

function sourceName() {
  return state.source?.name || "image.png";
}

function bindDrop(zone, input, onFiles) {
  zone.addEventListener("click", () => input.click());
  zone.addEventListener("dragover", (event) => {
    event.preventDefault();
    zone.classList.add("is-over");
  });
  zone.addEventListener("dragleave", () => zone.classList.remove("is-over"));
  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    zone.classList.remove("is-over");
    onFiles(event.dataTransfer.files);
  });
  input.addEventListener("change", () => onFiles(input.files));
}

function currentSliceOptions() {
  const mode = document.querySelector("input[name='slice-mode']:checked").value;
  if (mode === "grid") {
    return {
      cols: Number(document.getElementById("cols").value),
      rows: Number(document.getElementById("rows").value),
    };
  }
  return {
    tileWidth: Number(document.getElementById("tile-w").value),
    tileHeight: Number(document.getElementById("tile-h").value),
  };
}

function enhanceSettings() {
  return {
    scale: Number(els.scale.value),
    clarity: Number(els.clarity.value),
    sharpness: Number(els.sharpness.value),
    engine: els.engine.value,
  };
}

function canUseLocal() {
  return els.useLocal.checked && state.health.lanczos && state.file;
}

async function probeHealth() {
  try {
    const response = await fetch("/api/health");
    if (!response.ok) throw new Error("no api");
    const payload = await response.json();
    state.health = payload.engine || {};
    els.useLocal.disabled = false;
    els.useLocal.checked = true;
    if (!state.health.fsr) {
      els.engine.querySelector("option[value='fsr']").disabled = true;
      els.engine.value = "lanczos";
    }
    els.engineHint.textContent = state.health.fsr
      ? "本地引擎已连接。FSRCNN 超分可用，适合把糊图拉清楚。"
      : "本地引擎已连接。当前只有 Lanczos；装上 opencv 和 models 后可开 FSRCNN。";
  } catch {
    state.health = { lanczos: false, fsr: false };
    els.useLocal.checked = false;
    els.useLocal.disabled = true;
    els.engine.disabled = true;
    els.engineHint.textContent = "未检测到本地工作室接口，将使用浏览器引擎。请用 pixel-intact studio 启动。";
  }
}

async function enhanceViaApi(file, settings) {
  const form = new FormData();
  form.append("image", file);
  form.append("scale", String(settings.scale));
  form.append("clarity", String(settings.clarity));
  form.append("sharpness", String(settings.sharpness));
  form.append("engine", settings.engine);
  const response = await fetch("/api/enhance", { method: "POST", body: form });
  if (!response.ok) throw new Error(await response.text());
  const blob = await response.blob();
  return loadFileToCanvas(new File([blob], "enhanced.png", { type: "image/png" }));
}

async function enhanceCurrent(settings) {
  if (canUseLocal()) {
    const loaded = await enhanceViaApi(state.file, settings);
    return loaded.canvas;
  }
  return enhanceCanvas(state.source.canvas, settings);
}

async function updateLivePreview() {
  if (!state.source || !els.livePreview) return;
  const crop = cropCenter(state.source.canvas, 160);
  const preview = await enhanceCanvas(crop, {
    scale: Math.min(2, Number(els.scale.value)),
    clarity: Number(els.clarity.value),
    sharpness: Number(els.sharpness.value),
  });
  els.livePreview.replaceChildren(preview);
}

function scheduleLivePreview() {
  window.clearTimeout(liveTimer);
  liveTimer = window.setTimeout(() => {
    updateLivePreview().catch(() => {});
  }, 160);
}

function bindLoupe() {
  const loupeCanvas = document.createElement("canvas");
  loupeCanvas.width = 180;
  loupeCanvas.height = 180;
  els.loupe.replaceChildren(loupeCanvas);
  const ctx = loupeCanvas.getContext("2d");
  els.viewport.addEventListener("mousemove", (event) => {
    const source = state.resultCanvas || state.source?.canvas;
    if (!source) return;
    const canvas = els.viewport.querySelector("canvas");
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) {
      els.loupe.hidden = true;
      return;
    }
    const x = ((event.clientX - rect.left) / rect.width) * source.width;
    const y = ((event.clientY - rect.top) / rect.height) * source.height;
    els.loupe.hidden = false;
    els.loupe.style.left = `${event.clientX + 16}px`;
    els.loupe.style.top = `${event.clientY + 16}px`;
    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, 180, 180);
    ctx.drawImage(source, x - 45, y - 45, 90, 90, 0, 0, 180, 180);
  });
  els.viewport.addEventListener("mouseleave", () => {
    els.loupe.hidden = true;
  });
}

function workingSize() {
  if (!state.source) return null;
  const scale = els.enhanceFirst.checked || state.mode === "enhance" ? Number(els.scale.value) : 1;
  return {
    width: Math.max(1, Math.round(state.source.width * scale)),
    height: Math.max(1, Math.round(state.source.height * scale)),
    scale,
  };
}

function updatePlanPreview() {
  if (!state.source || state.mode !== "slice") return;
  try {
    const size = workingSize();
    const plan = planSlice(size.width, size.height, currentSliceOptions());
    els.estimate.textContent = (size.scale !== 1 ? `${size.scale}× 后 ` : "") + describePlan(plan);
    showCanvas(drawPreviewWithGrid(state.source.canvas, planSlice(state.source.width, state.source.height, currentSliceOptions())));
    els.note.textContent = plan.complete
      ? "切割线只是预览。处理前不会改原图，余数像素会留下来。"
      : `预览发现会丢掉 ${plan.discardedPixels} 像素。`;
  } catch (error) {
    els.estimate.textContent = error.message;
  }
}

function showCompare(beforeCanvas, afterCanvas) {
  const wrap = document.createElement("div");
  wrap.className = "compare";
  afterCanvas.className = "compare-after";
  const clip = document.createElement("div");
  clip.className = "compare-before";
  const before = document.createElement("canvas");
  before.width = afterCanvas.width;
  before.height = afterCanvas.height;
  const ctx = before.getContext("2d");
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(beforeCanvas, 0, 0, afterCanvas.width, afterCanvas.height);
  clip.append(before);
  const range = document.createElement("input");
  range.className = "compare-range";
  range.type = "range";
  range.min = "0";
  range.max = "100";
  range.value = "50";
  const beforeTag = document.createElement("span");
  beforeTag.className = "compare-tag is-before";
  beforeTag.textContent = "原图";
  const afterTag = document.createElement("span");
  afterTag.className = "compare-tag is-after";
  afterTag.textContent = "清晰";
  const sync = () => {
    clip.style.width = `${range.value}%`;
    const width = afterCanvas.getBoundingClientRect().width;
    const height = afterCanvas.getBoundingClientRect().height;
    before.style.width = `${width}px`;
    before.style.height = `${height}px`;
  };
  range.addEventListener("input", sync);
  wrap.append(afterCanvas, clip, range, beforeTag, afterTag);
  els.viewport.replaceChildren(wrap);
  requestAnimationFrame(sync);
}

async function setSource(file) {
  if (!file) return;
  state.file = file;
  state.source = await loadFileToCanvas(file);
  els.size.textContent = `${state.source.width} × ${state.source.height}`;
  els.pixels.textContent = formatPixels(state.source.width * state.source.height);
  els.fileMeta.textContent = `${file.name} · ${Math.round(file.size / 1024)} KB`;
  els.badge.textContent = "原图完整读入 · 0 像素被丢弃";
  els.badge.className = "badge is-good";
  els.sheet.hidden = true;
  els.sheet.replaceChildren();
  state.resultCanvas = state.source.canvas;
  state.tiles = [];
  state.downloadKind = "source";
  els.download.disabled = false;
  const jpeg = /jpe?g/i.test(file.type) || /\.jpe?g$/i.test(file.name);
  setStatus(
    jpeg
      ? "这是 JPEG，相机或网站可能已经压过。本工具会按当前像素完整处理，但无法找回丢失的细节；可用清晰模式提高观感。"
      : "原图已按完整像素载入。切图不会重采样；清晰模式才会增加像素数。",
  );
  if (state.mode === "slice") updatePlanPreview();
  else showCanvas(state.source.canvas);
  scheduleLivePreview();
}

function renderTiles(plan, sourceCanvas) {
  state.tiles = plan.tiles.map((tile) => ({
    ...tile,
    canvas: cropTile(sourceCanvas, tile),
  }));
  els.sheet.hidden = false;
  els.sheet.replaceChildren(
    ...state.tiles.map((tile) => {
      const card = document.createElement("div");
      card.className = "tile-card";
      card.append(thumbnail(tile.canvas));
      const caption = document.createElement("span");
      caption.textContent = `${tile.name} · ${tile.width}×${tile.height}`;
      card.append(caption);
      card.addEventListener("click", async () => {
        downloadBlob(await canvasToBlob(tile.canvas), outputName(sourceName(), tile.name.replace(".png", "")));
      });
      return card;
    }),
  );
}

async function runSlice() {
  if (!state.source) throw new Error("先放入一张原图");
  let working = state.source.canvas;
  if (els.enhanceFirst.checked) {
    setStatus(canUseLocal() ? "本地引擎正在提高清晰度，然后切块…" : "正在提高清晰度，然后按完整画布切块…");
    working = await enhanceCurrent(enhanceSettings());
    state.resultCanvas = working;
  }
  const plan = planSlice(working.width, working.height, currentSliceOptions());
  renderTiles(plan, working);
  showCanvas(drawPreviewWithGrid(working, plan));
  els.title.textContent = `切成 ${plan.rows} × ${plan.cols}`;
  els.note.textContent = plan.complete
    ? `导出 ${formatPixels(plan.exportedPixels)} 像素，丢弃 0。点击小图可单独下载该块。`
    : `仍有 ${plan.discardedPixels} 像素未导出。`;
  els.badge.textContent = plan.complete ? "切图完整 · discarded pixels = 0" : "切图不完整";
  els.badge.className = plan.complete ? "badge is-good" : "badge is-wait";
  state.downloadKind = "tiles";
  els.download.disabled = false;
  setStatus(
    plan.remainderDistributed
      ? "原图像素无法整除，已把余数分给靠前的行/列，避免像低像素网站那样裁掉边缘。"
      : "画布被整齐切完，可以用「拼回」还原原图。",
  );
}

async function runEnhance() {
  if (!state.source) throw new Error("先放入一张原图");
  const settings = enhanceSettings();
  setStatus(canUseLocal() ? "本地引擎正在超分 / 放大…" : "正在分步放大并提高局部对比，请稍候…");
  const canvas = await enhanceCurrent(settings);
  showCompare(state.source.canvas, canvas);
  els.sheet.hidden = true;
  state.resultCanvas = canvas;
  state.tiles = [];
  state.downloadKind = "enhanced";
  els.download.disabled = false;
  const before = state.source.width * state.source.height;
  const after = canvas.width * canvas.height;
  els.title.textContent = `${settings.scale}× 清晰输出`;
  els.note.textContent = `从 ${formatPixels(before)} 提升到 ${formatPixels(after)} 像素。拖动底部滑杆对比原图。`;
  els.badge.textContent = `清晰度已提高 · ${canvas.width}×${canvas.height}`;
  els.badge.className = "badge is-good";
  const engineLabel = canUseLocal() && settings.engine === "fsr" ? "FSRCNN 超分" : "Lanczos";
  setStatus(`已用${engineLabel}提高像素密度，再做中频清晰和边缘锐化。构图不变。`);
}

async function collectJoinFiles(fileList) {
  state.joinFiles = [...fileList];
  els.joinCount.textContent = `${state.joinFiles.length} 个切块待拼接`;
}

async function runJoin() {
  if (!state.joinFiles.length) throw new Error("先放入切块");
  const named = state.joinFiles.map((file) => parseTileName(file.name)).filter(Boolean);
  if (named.length && named.length !== state.joinFiles.length) {
    throw new Error("切块文件名请统一成 r00_c00.png，或全部不要带行列名、按顺序多选。");
  }
  const pieces = [];
  for (const [index, file] of state.joinFiles.entries()) {
    const loaded = await loadFileToCanvas(file);
    const parsed = parseTileName(file.name);
    const colsGuess = Math.ceil(Math.sqrt(state.joinFiles.length));
    pieces.push({
      row: parsed ? parsed.row : Math.floor(index / colsGuess),
      col: parsed ? parsed.col : index % colsGuess,
      canvas: loaded.canvas,
    });
  }
  const joined = joinCanvases(pieces);
  showCanvas(joined.canvas);
  els.sheet.hidden = true;
  state.resultCanvas = joined.canvas;
  state.downloadKind = "joined";
  els.download.disabled = false;
  els.title.textContent = "已拼回完整图";
  els.note.textContent = joined.complete
    ? `${joined.canvas.width}×${joined.canvas.height}，切块像素全部回到画布。`
    : `拼接完成，但还有 ${joined.discardedPixels} 像素空隙。`;
  els.badge.textContent = joined.complete ? "拼回完整" : "拼回有空隙";
  els.badge.className = joined.complete ? "badge is-good" : "badge is-wait";
  setStatus("如果这些切块来自本工具，拼回结果应与原图一致。");
}

async function downloadResult() {
  if (state.downloadKind === "tiles" && state.tiles.length) {
    const zip = new JSZip();
    const folder = zip.folder("tiles");
    let sourcePixels = 0;
    for (const tile of state.tiles) {
      sourcePixels += tile.width * tile.height;
      folder.file(tile.name, await canvasToBlob(tile.canvas));
    }
    folder.file(
      "intact-manifest.txt",
      [
        `width=${state.tiles.reduce((max, tile) => Math.max(max, tile.left + tile.width), 0)}`,
        `height=${state.tiles.reduce((max, tile) => Math.max(max, tile.top + tile.height), 0)}`,
        `discarded_pixels=0`,
        `complete=true`,
        `source_pixels=${sourcePixels}`,
        "tiles=",
        ...state.tiles.map(
          (tile) =>
            `${tile.name}:${tile.row},${tile.col},${tile.left},${tile.top},${tile.width},${tile.height}`,
        ),
      ].join("\n"),
    );
    downloadBlob(await zip.generateAsync({ type: "blob" }), outputName(sourceName(), "tiles", "zip"));
    return;
  }
  if (!state.resultCanvas) return;
  const suffix =
    state.downloadKind === "enhanced" ? "enhanced" : state.downloadKind === "joined" ? "joined" : "original";
  const fmt = els.exportFormat.value;
  const mime = fmt === "jpeg" ? "image/jpeg" : fmt === "webp" ? "image/webp" : "image/png";
  downloadBlob(
    await canvasToBlob(state.resultCanvas, mime, fmt === "jpeg" ? 0.98 : 1),
    outputName(sourceName(), suffix, fmt === "jpeg" ? "jpg" : fmt),
  );
}

function syncEnhanceVisibility() {
  const showEnhance =
    state.mode === "enhance" || (state.mode === "slice" && els.enhanceFirst.checked);
  els.enhanceForm.classList.toggle("is-hidden", !showEnhance);
  if (state.mode === "slice") updatePlanPreview();
}

function setMode(mode) {
  state.mode = mode;
  els.tabs.forEach((tab) => tab.classList.toggle("is-active", tab.dataset.mode === mode));
  els.sliceForm.classList.toggle("is-hidden", mode !== "slice");
  els.joinForm.classList.toggle("is-hidden", mode !== "join");
  syncEnhanceVisibility();
  if (mode === "slice" && state.source) updatePlanPreview();
  if (mode === "enhance" && state.source && !state.tiles.length) showCanvas(state.source.canvas);
}

els.tabs.forEach((tab) => tab.addEventListener("click", () => setMode(tab.dataset.mode)));
els.enhanceFirst.addEventListener("change", syncEnhanceVisibility);

els.presets.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-cols]");
  if (!button) return;
  document.querySelector("input[name='slice-mode'][value='grid']").checked = true;
  document.getElementById("cols").value = button.dataset.cols;
  document.getElementById("rows").value = button.dataset.rows;
  updatePlanPreview();
});

["cols", "rows", "tile-w", "tile-h"].forEach((id) => {
  document.getElementById(id).addEventListener("input", updatePlanPreview);
});
document.querySelectorAll("input[name='slice-mode']").forEach((input) => {
  input.addEventListener("change", updatePlanPreview);
});

["input", "change"].forEach((eventName) => {
  els.scale.addEventListener(eventName, () => {
    els.scaleOut.textContent = `${els.scale.value}×`;
    if (state.mode === "slice") updatePlanPreview();
  });
  els.clarity.addEventListener(eventName, () => {
    els.clarityOut.textContent = Number(els.clarity.value).toFixed(2);
  });
  els.sharpness.addEventListener(eventName, () => {
    els.sharpOut.textContent = Number(els.sharpness.value).toFixed(2);
    scheduleLivePreview();
  });
});
els.scale.addEventListener("input", scheduleLivePreview);
els.clarity.addEventListener("input", scheduleLivePreview);
els.engine.addEventListener("change", scheduleLivePreview);

bindDrop(els.drop, els.file, (files) => {
  if (files[0]) setSource(files[0]).catch((error) => setStatus(error.message));
});
bindDrop(els.joinDrop, els.joinInput, (files) => {
  collectJoinFiles(files).catch((error) => setStatus(error.message));
});

document.addEventListener("paste", (event) => {
  const file = [...(event.clipboardData?.files || [])].find((item) => item.type.startsWith("image/"));
  if (file) setSource(file).catch((error) => setStatus(error.message));
});

els.run.addEventListener("click", async () => {
  els.run.disabled = true;
  try {
    if (state.mode === "slice") await runSlice();
    else if (state.mode === "enhance") await runEnhance();
    else await runJoin();
  } catch (error) {
    setStatus(error.message);
  } finally {
    els.run.disabled = false;
  }
});

els.download.addEventListener("click", () => {
  downloadResult().catch((error) => setStatus(error.message));
});

bindLoupe();
probeHealth();
