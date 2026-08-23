const { planSlice, describePlan, assertSafeSize } = require("../../utils/core");
const {
  getCanvas,
  loadImage,
  canvasToPath,
  saveToAlbum,
  enhanceOnCanvas,
} = require("../../utils/wximage");

function createOffscreen(width, height) {
  const canvas = wx.createOffscreenCanvas({ type: "2d", width, height });
  canvas.width = width;
  canvas.height = height;
  return canvas;
}

Page({
  data: {
    previewPath: "",
    width: 0,
    height: 0,
    pixels: "—",
    badge: "原图完整读入",
    complete: true,
    mode: "slice",
    cols: 3,
    rows: 3,
    enhanceFirst: false,
    scale: 2,
    clarity: 0.35,
    sharpness: 0.85,
    estimate: "",
    status: "选好参数后点处理。切图只裁切，不重采样。",
    busy: false,
    resultPath: "",
    tiles: [],
  },

  onLoad() {
    const app = getApp();
    if (!app.globalData.imagePath) {
      wx.reLaunch({ url: "/pages/index/index" });
      return;
    }
    this.sourcePath = app.globalData.imagePath;
    this.setData({
      previewPath: app.globalData.imagePath,
      width: app.globalData.width,
      height: app.globalData.height,
      pixels: String(app.globalData.width * app.globalData.height),
      resultPath: app.globalData.imagePath,
    });
    this.updateEstimate();
  },

  setMode(event) {
    this.setData({ mode: event.currentTarget.dataset.mode });
  },

  preset(event) {
    this.setData({
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

  workingSize() {
    const scale = this.data.mode === "enhance" || this.data.enhanceFirst ? this.data.scale : 1;
    return {
      width: Math.max(1, Math.round(this.data.width * scale)),
      height: Math.max(1, Math.round(this.data.height * scale)),
      scale,
    };
  },

  updateEstimate() {
    try {
      const size = this.workingSize();
      const plan = planSlice(size.width, size.height, {
        cols: this.data.cols,
        rows: this.data.rows,
      });
      this.setData({
        estimate: (size.scale !== 1 ? `${size.scale}× 后 ` : "") + describePlan(plan),
      });
    } catch (error) {
      this.setData({ estimate: error.message });
    }
  },

  async run() {
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

  async workCanvas() {
    return getCanvas("#work", this);
  },

  async runEnhance() {
    const canvas = await this.workCanvas();
    const image = await loadImage(canvas, this.sourcePath);
    const path = await enhanceOnCanvas(
      canvas,
      image,
      this.data.width,
      this.data.height,
      this.data,
    );
    this.setData({
      previewPath: path,
      resultPath: path,
      tiles: [],
      badge: `清晰度已提高 · 看预览`,
      complete: true,
      status: "已放大并提高清晰度。点「保存当前图」写入相册。",
    });
  },

  async runSlice() {
    let src = this.sourcePath;
    let width = this.data.width;
    let height = this.data.height;
    if (this.data.enhanceFirst) {
      this.setData({ status: "先提高清晰度，再按完整画布切块…" });
      const canvas = await this.workCanvas();
      const image = await loadImage(canvas, this.sourcePath);
      src = await enhanceOnCanvas(canvas, image, width, height, this.data);
      width = Math.max(1, Math.round(width * this.data.scale));
      height = Math.max(1, Math.round(height * this.data.scale));
    }
    const plan = planSlice(width, height, { cols: this.data.cols, rows: this.data.rows });
    if (!plan.complete) throw new Error("切图不完整");
    assertSafeSize(width, height);
    const board = createOffscreen(width, height);
    const ctx = board.getContext("2d");
    ctx.imageSmoothingEnabled = false;
    const image = await loadImage(board, src);
    ctx.drawImage(image, 0, 0, width, height);

    const tiles = [];
    for (const tile of plan.tiles) {
      const piece = createOffscreen(tile.width, tile.height);
      const pieceCtx = piece.getContext("2d");
      pieceCtx.imageSmoothingEnabled = false;
      pieceCtx.drawImage(board, tile.left, tile.top, tile.width, tile.height, 0, 0, tile.width, tile.height);
      const path = await canvasToPath(piece);
      tiles.push({ ...tile, path });
    }
    this.setData({
      tiles,
      resultPath: src,
      previewPath: src,
      badge: plan.complete ? "切图完整 · discarded pixels = 0" : "切图不完整",
      complete: plan.complete,
      status: plan.remainderDistributed
        ? "余数已分给前排图块。点小图可保存该块，或保存当前完整图。"
        : "已整齐切完。点小图保存单块。",
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
});
