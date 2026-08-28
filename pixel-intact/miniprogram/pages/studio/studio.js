const {
  planSlice,
  describePlan,
  formatPixels,
  overlayLines,
  sizeAfterScaleExceeds,
  tilesAfterScaleExceed,
  suggestSafeGrid,
  planWithScaledTiles,
  targetSize,
} = require("../../utils/core");
const {
  chooseOriginalImage,
  getImageInfo,
  getCanvas,
  loadImage,
  saveToAlbum,
  saveManyToAlbum,
  waitFrame,
  cropFromImage,
  enhanceRegion,
  enhanceOnCanvas,
} = require("../../utils/wximage");

Page({
  data: {
    previewPath: "",
    width: 0,
    height: 0,
    pixels: "—",
    fileMeta: "—",
    badge: "等待原图",
    complete: true,
    mode: "slice",
    sliceMode: "grid",
    cols: 3,
    rows: 3,
    tileW: 512,
    tileH: 512,
    enhanceFirst: false,
    scale: 2,
    clarity: 0.35,
    sharpness: 0.85,
    estimate: "",
    estimateLevel: "",
    status: "选好参数后点处理。切图只裁切，不重采样。",
    busy: false,
    resultPath: "",
    tiles: [],
    vLines: [],
    hLines: [],
  },

  onShow() {
    const app = getApp();
    if (!app.globalData.imagePath) return;
    if (this.sourcePath === app.globalData.imagePath) return;
    this.applySource(app.globalData);
  },

  applySource(source) {
    this.sourcePath = source.imagePath;
    const pixels = source.width * source.height;
    this.setData({
      previewPath: source.imagePath,
      width: source.width,
      height: source.height,
      pixels: formatPixels(pixels),
      fileMeta: `${source.name || "原图"}${source.fileSize ? ` · ${Math.round(source.fileSize / 1024)} KB` : ""}`,
      badge: "原图完整读入 · 0 像素被丢弃",
      complete: true,
      resultPath: source.imagePath,
      tiles: [],
      status:
        pixels > 40_000_000
          ? "这张图很大。手机不会一次画出整张放大画布；点处理会按块进行，请不要切到后台。"
          : "原图已按完整像素读入。切图不重采样；清晰模式才会增加像素。",
    });
    this.updateEstimate();
  },

  async pickImage() {
    try {
      const chosen = await chooseOriginalImage(1);
      const file = chosen.tempFiles[0];
      const info = await getImageInfo(file.tempFilePath);
      const app = getApp();
      app.globalData.imagePath = file.tempFilePath;
      app.globalData.width = info.width;
      app.globalData.height = info.height;
      app.globalData.name = (file.originalFilePath || file.tempFilePath).split("/").pop() || "image";
      app.globalData.fileSize = file.size || 0;
      this.applySource(app.globalData);
    } catch (error) {
      if (error && error.errMsg && String(error.errMsg).includes("cancel")) return;
      wx.showToast({ title: error.message || "选图失败", icon: "none" });
    }
  },

  sliceOptions() {
    if (this.data.sliceMode === "size") {
      return { tileWidth: Number(this.data.tileW), tileHeight: Number(this.data.tileH) };
    }
    return { cols: Number(this.data.cols) || 1, rows: Number(this.data.rows) || 1 };
  },

  workingScale() {
    return this.data.mode === "enhance" || this.data.enhanceFirst ? Number(this.data.scale) : 1;
  },

  updateEstimate() {
    if (!this.data.width) return;
    try {
      const scale = this.workingScale();
      const overlayPlan = planSlice(this.data.width, this.data.height, this.sliceOptions());
      const lines = overlayLines(overlayPlan);
      const fullExceeds =
        (this.data.mode === "enhance" || this.data.enhanceFirst) &&
        sizeAfterScaleExceeds(this.data.width, this.data.height, scale);
      let plan = planSlice(
        Math.max(1, Math.round(this.data.width * scale)),
        Math.max(1, Math.round(this.data.height * scale)),
        this.sliceOptions(),
      );
      let extra = "";
      let estimateLevel = "";
      if (tilesAfterScaleExceed(overlayPlan, scale)) {
        const suggested = suggestSafeGrid(this.data.width, this.data.height, scale);
        extra = ` 当前切块放大后仍超手机上限。请改成至少 ${suggested.cols}×${suggested.rows}，或把倍数改小。`;
        estimateLevel = "hint-danger";
      } else if (fullExceeds) {
        plan = planWithScaledTiles(overlayPlan, scale);
        extra = ` 整张会超限，点处理会先按原图切开，再对每一块做 ${scale}×。`;
        estimateLevel = "hint-warn";
      }
      this.setData({
        estimate: (scale !== 1 ? `${scale}× 后 ` : "") + describePlan(plan) + extra,
        estimateLevel,
        vLines: lines.vLines,
        hLines: lines.hLines,
      });
    } catch (error) {
      this.setData({ estimate: error.message, estimateLevel: "hint-danger" });
    }
  },

  setMode(event) {
    this.setData({ mode: event.currentTarget.dataset.mode });
    this.updateEstimate();
  },

  setSliceMode(event) {
    this.setData({ sliceMode: event.currentTarget.dataset.slice });
    this.updateEstimate();
  },

  preset(event) {
    this.setData({
      sliceMode: "grid",
      cols: Number(event.currentTarget.dataset.cols),
      rows: Number(event.currentTarget.dataset.rows),
    });
    this.updateEstimate();
  },

  onCols(event) {
    this.setData({ cols: Number(event.detail.value || 1) });
    this.updateEstimate();
  },

  onRows(event) {
    this.setData({ rows: Number(event.detail.value || 1) });
    this.updateEstimate();
  },

  onTileW(event) {
    this.setData({ tileW: Number(event.detail.value || 1) });
    this.updateEstimate();
  },

  onTileH(event) {
    this.setData({ tileH: Number(event.detail.value || 1) });
    this.updateEstimate();
  },

  onEnhanceFirst(event) {
    this.setData({ enhanceFirst: event.detail.value });
    this.updateEstimate();
  },

  onScale(event) {
    this.setData({ scale: Number(event.detail.value) });
    this.updateEstimate();
  },

  onClarity(event) {
    this.setData({ clarity: Number(Number(event.detail.value).toFixed(2)) });
  },

  onSharp(event) {
    this.setData({ sharpness: Number(Number(event.detail.value).toFixed(2)) });
  },

  async sourceImage() {
    const canvas = await getCanvas("#work", this);
    return loadImage(canvas, this.sourcePath);
  },

  async run() {
    if (!this.sourcePath) {
      wx.showToast({ title: "先选一张原图", icon: "none" });
      return;
    }
    this.setData({ busy: true });
    try {
      if (this.data.mode === "enhance") await this.runEnhance();
      else await this.runSlice();
    } catch (error) {
      this.setData({ status: error.message || "处理失败" });
      wx.showToast({ title: error.message || "处理失败", icon: "none" });
    } finally {
      this.setData({ busy: false });
    }
  },

  async enhanceTiles(sourcePlan, settings, image) {
    const tiles = [];
    const total = sourcePlan.tiles.length;
    for (let index = 0; index < total; index += 1) {
      const tile = sourcePlan.tiles[index];
      this.setData({
        status: `整张超限，已先切块。正在提高第 ${index + 1}/${total} 块（${tile.name}）…`,
      });
      await waitFrame();
      const enhanced = await enhanceRegion(image, tile, settings);
      tiles.push({
        ...tile,
        width: enhanced.width,
        height: enhanced.height,
        path: enhanced.path,
      });
    }
    return tiles;
  },

  presentTiles(tiles, sourcePlan, titleStatus, autoNote) {
    const exported = tiles.reduce((sum, tile) => sum + tile.width * tile.height, 0);
    this.setData({
      tiles,
      resultPath: tiles[0] ? tiles[0].path : this.sourcePath,
      previewPath: this.sourcePath,
      badge: "切图完整 · discarded pixels = 0",
      complete: true,
      status: autoNote || titleStatus,
      vLines: overlayLines(sourcePlan).vLines,
      hLines: overlayLines(sourcePlan).hLines,
    });
    wx.showToast({ title: `完成 ${tiles.length} 块`, icon: "none" });
    return exported;
  },

  async runSlice() {
    const settings = {
      scale: this.data.enhanceFirst ? this.data.scale : 1,
      clarity: this.data.enhanceFirst ? this.data.clarity : 0,
      sharpness: this.data.enhanceFirst ? this.data.sharpness : 0,
    };
    let options = this.sliceOptions();
    let sourcePlan = planSlice(this.data.width, this.data.height, options);
    const scale = this.data.enhanceFirst ? this.data.scale : 1;
    if (tilesAfterScaleExceed(sourcePlan, scale)) {
      const suggested = suggestSafeGrid(this.data.width, this.data.height, scale);
      sourcePlan = suggested.plan;
      options = { cols: suggested.cols, rows: suggested.rows };
      this.setData({
        sliceMode: "grid",
        cols: suggested.cols,
        rows: suggested.rows,
        status: `当前切块超限，已自动改成 ${suggested.cols}×${suggested.rows}，丢弃像素仍为 0。`,
      });
    }
    const image = await this.sourceImage();
    if (this.data.enhanceFirst && sizeAfterScaleExceeds(this.data.width, this.data.height, scale)) {
      const tiles = await this.enhanceTiles(sourcePlan, this.data, image);
      const full = targetSize(this.data.width, this.data.height, scale);
      this.presentTiles(
        tiles,
        sourcePlan,
        "",
        `整张 ${full.width}×${full.height} 会超限，已对 ${tiles.length} 块分别提高清晰度。丢弃 0。`,
      );
      return;
    }
    if (this.data.enhanceFirst && !sizeAfterScaleExceeds(this.data.width, this.data.height, scale)) {
      this.setData({ status: "正在提高清晰度，然后按完整画布切块…" });
      const canvas = await getCanvas("#work", this);
      const enhancedPath = await enhanceOnCanvas(
        canvas,
        image,
        this.data.width,
        this.data.height,
        this.data,
      );
      const out = targetSize(this.data.width, this.data.height, scale);
      const plan = planSlice(out.width, out.height, options);
      const enhancedImage = await loadImage(canvas, enhancedPath);
      const tiles = [];
      for (const tile of plan.tiles) {
        const crop = await cropFromImage(enhancedImage, tile);
        tiles.push({ ...tile, path: crop.path });
      }
      this.presentTiles(tiles, sourcePlan, "", `导出 ${formatPixels(plan.exportedPixels)} 像素，丢弃 0。`);
      this.setData({ resultPath: enhancedPath, previewPath: enhancedPath });
      return;
    }

    this.setData({ status: "正在按原图像素切块，不重采样…" });
    const tiles = [];
    for (const tile of sourcePlan.tiles) {
      const crop = await cropFromImage(image, tile);
      tiles.push({ ...tile, path: crop.path });
    }
    this.presentTiles(
      tiles,
      sourcePlan,
      "",
      sourcePlan.remainderDistributed
        ? "余数已分给前排图块，避免像低像素网站那样裁掉边缘。点小图可保存该块。"
        : "画布被整齐切完。点小图保存单块，或保存全部到相册。",
    );
  },

  async runEnhance() {
    const settings = this.data;
    if (sizeAfterScaleExceeds(this.data.width, this.data.height, settings.scale)) {
      const suggested = suggestSafeGrid(this.data.width, this.data.height, settings.scale);
      const image = await this.sourceImage();
      const tiles = await this.enhanceTiles(suggested.plan, settings, image);
      const full = targetSize(this.data.width, this.data.height, settings.scale);
      this.presentTiles(
        tiles,
        suggested.plan,
        "",
        `无法一次输出 ${full.width}×${full.height}。已按 ${suggested.cols}×${suggested.rows} 分块提高，丢弃 0。`,
      );
      return;
    }
    this.setData({ status: "正在本地放大并提高清晰度…" });
    const canvas = await getCanvas("#work", this);
    const image = await loadImage(canvas, this.sourcePath);
    const path = await enhanceOnCanvas(canvas, image, this.data.width, this.data.height, settings);
    const out = targetSize(this.data.width, this.data.height, settings.scale);
    this.setData({
      previewPath: path,
      resultPath: path,
      tiles: [],
      badge: `清晰度已提高 · ${out.width}×${out.height}`,
      complete: true,
      status: `从 ${formatPixels(this.data.width * this.data.height)} 提升到 ${formatPixels(out.width * out.height)} 像素。构图不变。点「保存当前」写入相册。`,
    });
  },

  async saveCurrent() {
    if (!this.data.resultPath) return;
    try {
      await saveToAlbum(this.data.resultPath);
      wx.showToast({ title: "已保存到相册", icon: "success" });
    } catch (error) {
      wx.showToast({ title: error.message || "保存失败", icon: "none" });
    }
  },

  async saveTile(event) {
    try {
      await saveToAlbum(event.currentTarget.dataset.path);
      wx.showToast({ title: "已保存该块", icon: "success" });
    } catch (error) {
      wx.showToast({ title: error.message || "保存失败", icon: "none" });
    }
  },

  async saveAllTiles() {
    if (!this.data.tiles.length) return;
    this.setData({ busy: true });
    try {
      await saveManyToAlbum(
        this.data.tiles.map((tile) => tile.path),
        (index, total) => this.setData({ status: `正在保存第 ${index}/${total} 块到相册…` }),
      );
      this.setData({ status: `已把 ${this.data.tiles.length} 块全部写入相册。相册可能不保留 r00_c00 文件名，拼回请按选择顺序。` });
      wx.showToast({ title: "已全部保存", icon: "success" });
    } catch (error) {
      this.setData({ status: error.message || "保存失败" });
      wx.showToast({ title: error.message || "保存失败", icon: "none" });
    } finally {
      this.setData({ busy: false });
    }
  },
});
