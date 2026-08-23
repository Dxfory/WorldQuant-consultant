const { parseTileName, tileName, assertSafeSize } = require("../../utils/core");
const {
  chooseOriginalImage,
  getImageInfo,
  loadImage,
  canvasToPath,
  saveToAlbum,
} = require("../../utils/wximage");

function createOffscreen(width, height) {
  const canvas = wx.createOffscreenCanvas({ type: "2d", width, height });
  canvas.width = width;
  canvas.height = height;
  return canvas;
}

Page({
  data: {
    tiles: [],
    resultPath: "",
    busy: false,
    status: "还没有切块",
  },

  async pickTiles() {
    try {
      const chosen = await chooseOriginalImage(9);
      const tiles = [];
      for (const [index, file] of chosen.tempFiles.entries()) {
        const info = await getImageInfo(file.tempFilePath);
        const parsed = parseTileName(file.tempFilePath) || parseTileName(file.originalFilePath || "");
        const colsGuess = Math.ceil(Math.sqrt(chosen.tempFiles.length));
        const row = parsed ? parsed.row : Math.floor(index / colsGuess);
        const col = parsed ? parsed.col : index % colsGuess;
        tiles.push({
          path: file.tempFilePath,
          width: info.width,
          height: info.height,
          row,
          col,
          label: `${parsed ? tileName(row, col) : `顺序 ${index + 1}`} · ${info.width}×${info.height}`,
        });
      }
      this.setData({ tiles, status: `已选 ${tiles.length} 个切块` });
    } catch (error) {
      if (error && error.errMsg && error.errMsg.includes("cancel")) return;
      wx.showToast({ title: error.message || "选图失败", icon: "none" });
    }
  },

  async run() {
    this.setData({ busy: true });
    try {
      const pieces = this.data.tiles;
      if (!pieces.length) throw new Error("先选择切块");
      const rows = Math.max(...pieces.map((item) => item.row)) + 1;
      const cols = Math.max(...pieces.map((item) => item.col)) + 1;
      const grid = new Map(pieces.map((item) => [`${item.row}:${item.col}`, item]));
      const rowHeights = [];
      const colWidths = [];
      for (let row = 0; row < rows; row += 1) {
        const heights = pieces.filter((item) => item.row === row).map((item) => item.height);
        if (!heights.length) throw new Error(`缺少第 ${row + 1} 行`);
        rowHeights.push(Math.max(...heights));
      }
      for (let col = 0; col < cols; col += 1) {
        const widths = pieces.filter((item) => item.col === col).map((item) => item.width);
        if (!widths.length) throw new Error(`缺少第 ${col + 1} 列`);
        colWidths.push(Math.max(...widths));
      }
      const width = colWidths.reduce((sum, value) => sum + value, 0);
      const height = rowHeights.reduce((sum, value) => sum + value, 0);
      assertSafeSize(width, height);
      const canvas = createOffscreen(width, height);
      const ctx = canvas.getContext("2d");
      ctx.imageSmoothingEnabled = false;
      let top = 0;
      for (let row = 0; row < rows; row += 1) {
        let left = 0;
        for (let col = 0; col < cols; col += 1) {
          const cell = grid.get(`${row}:${col}`);
          if (!cell) throw new Error(`缺少 ${tileName(row, col)}`);
          const image = await loadImage(canvas, cell.path);
          ctx.drawImage(image, left, top);
          left += colWidths[col];
        }
        top += rowHeights[row];
      }
      const path = await canvasToPath(canvas);
      this.setData({
        resultPath: path,
        status: `已拼回 ${width}×${height}。可保存到相册。`,
      });
    } catch (error) {
      this.setData({ status: error.message || "拼接失败" });
      wx.showToast({ title: error.message || "拼接失败", icon: "none" });
    } finally {
      this.setData({ busy: false });
    }
  },

  async save() {
    try {
      await saveToAlbum(this.data.resultPath);
      wx.showToast({ title: "已保存到相册", icon: "success" });
    } catch (error) {
      wx.showToast({ title: error.message || "保存失败", icon: "none" });
    }
  },
});
