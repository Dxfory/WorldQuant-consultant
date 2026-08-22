import JSZip from "https://cdn.jsdelivr.net/npm/jszip@3.10.1/+esm";
import {
  canvasToBlob,
  cropTile,
  downloadBlob,
  enhanceCanvas,
  formatPixels,
  joinCanvases,
  loadFileToCanvas,
  parseTileName,
  planSlice,
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
};

const state = {
  mode: "slice",
  source: null,
  resultCanvas: null,
  tiles: [],
  joinFiles: [],
  downloadKind: null,
};

function setStatus(text) {
  els.status.textContent = text;
}

function showCanvas(canvas) {
  els.viewport.replaceChildren(canvas);
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

async function setSource(file) {
  if (!file) return;
  state.source = await loadFileToCanvas(file);
  els.size.textContent = `${state.source.width} × ${state.source.height}`;
  els.pixels.textContent = formatPixels(state.source.width * state.source.height);
  els.fileMeta.textContent = `${file.name} · ${Math.round(file.size / 1024)} KB`;
  els.badge.textContent = "原图完整读入 · 0 像素被丢弃";
  els.badge.className = "badge is-good";
  showCanvas(state.source.canvas);
  els.sheet.hidden = true;
  els.sheet.replaceChildren();
  state.resultCanvas = state.source.canvas;
  state.tiles = [];
  state.downloadKind = "source";
  els.download.disabled = false;
  setStatus("原图已按完整像素载入。切图不会重采样；清晰模式才会增加像素数。");
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
  };
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
      card.append(tile.canvas);
      const caption = document.createElement("span");
      caption.textContent = `${tile.name} · ${tile.width}×${tile.height}`;
      card.append(caption);
      return card;
    }),
  );
}

async function runSlice() {
  if (!state.source) throw new Error("先放入一张原图");
  let working = state.source.canvas;
  if (els.enhanceFirst.checked) {
    setStatus("正在提高清晰度，然后按完整画布切块…");
    working = enhanceCanvas(working, enhanceSettings());
    showCanvas(working);
    state.resultCanvas = working;
  }
  const plan = planSlice(working.width, working.height, currentSliceOptions());
  renderTiles(plan, working);
  els.title.textContent = `切成 ${plan.rows} × ${plan.cols}`;
  els.note.textContent = plan.complete
    ? `导出 ${formatPixels(plan.exportedPixels)} 像素，丢弃 0。余数已并入前排图块。`
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

function runEnhance() {
  if (!state.source) throw new Error("先放入一张原图");
  const settings = enhanceSettings();
  const canvas = enhanceCanvas(state.source.canvas, settings);
  showCanvas(canvas);
  els.sheet.hidden = true;
  state.resultCanvas = canvas;
  state.tiles = [];
  state.downloadKind = "enhanced";
  els.download.disabled = false;
  const before = state.source.width * state.source.height;
  const after = canvas.width * canvas.height;
  els.title.textContent = `${settings.scale}× 清晰输出`;
  els.note.textContent = `从 ${formatPixels(before)} 提升到 ${formatPixels(after)} 像素。构图不变，只增加采样密度和边缘对比。`;
  els.badge.textContent = `清晰度已提高 · ${canvas.width}×${canvas.height}`;
  els.badge.className = "badge is-good";
  setStatus("已用高质量缩放 + 局部对比 + 锐化。需要切图时，可勾选「先提高清晰度再切」。");
}

async function collectJoinFiles(fileList) {
  state.joinFiles = [...fileList];
  els.joinCount.textContent = `${state.joinFiles.length} 个切块待拼接`;
}

async function runJoin() {
  if (!state.joinFiles.length) throw new Error("先放入切块");
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
    downloadBlob(await zip.generateAsync({ type: "blob" }), "pixel-intact-tiles.zip");
    return;
  }
  if (!state.resultCanvas) return;
  const blob = await canvasToBlob(state.resultCanvas);
  const name =
    state.downloadKind === "enhanced"
      ? "pixel-intact-enhanced.png"
      : state.downloadKind === "joined"
        ? "pixel-intact-joined.png"
        : "pixel-intact-original.png";
  downloadBlob(blob, name);
}

function syncEnhanceVisibility() {
  const showEnhance =
    state.mode === "enhance" || (state.mode === "slice" && els.enhanceFirst.checked);
  els.enhanceForm.classList.toggle("is-hidden", !showEnhance);
}

function setMode(mode) {
  state.mode = mode;
  els.tabs.forEach((tab) => tab.classList.toggle("is-active", tab.dataset.mode === mode));
  els.sliceForm.classList.toggle("is-hidden", mode !== "slice");
  els.joinForm.classList.toggle("is-hidden", mode !== "join");
  syncEnhanceVisibility();
}

els.tabs.forEach((tab) => tab.addEventListener("click", () => setMode(tab.dataset.mode)));
els.enhanceFirst.addEventListener("change", syncEnhanceVisibility);

["input", "change"].forEach((eventName) => {
  els.scale.addEventListener(eventName, () => {
    els.scaleOut.textContent = `${els.scale.value}×`;
  });
  els.clarity.addEventListener(eventName, () => {
    els.clarityOut.textContent = Number(els.clarity.value).toFixed(2);
  });
  els.sharpness.addEventListener(eventName, () => {
    els.sharpOut.textContent = Number(els.sharpness.value).toFixed(2);
  });
});

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
    else if (state.mode === "enhance") runEnhance();
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
