const { parseTileName, tileName, assertSafeSize, formatPixels } = require("../../utils/core");
const {
  chooseOriginalImage,
  getImageInfo,
  loadImage,
  canvasToPath,
  saveToAlbum,
  createOffscreen,
} = require("../../utils/wximage");

Page({
  data: {
    tiles: [],
    resultPath: "",
    busy: false,
    cols: 3,
    rows: 3,
    status: "还没有切块。九宫格请按 r00_c00、r00_c01、r00_c02… 的顺序连选。",
    statusLevel: "",
  },

  onCols(event) {
    this.setData({ cols: Number(event.detail.value || 1) });
  },

  onRows(event) {
    this.setData({ rows: Number(event.detail.value || 1) });
  },

  async pickTiles() {
    try {
      const maxCount = Math.min(20, Math.max(1, this.data.cols * this.data.rows));
      const chosen = await chooseOriginalImage(maxCount);
      const named = [];
      for (const [index, file] of chosen.tempFiles.entries()) {
        const info = await getImageInfo(file.tempFilePath);
        const parsed =
          parseTileName(file.tempFilePath) ||
          parseTileName(file.originalFilePath || "") ||
          parseTileName((file.tempFilePath || "").split("/").pop());
        named.push({ file, info, parsed, index });
      }
      const useNames = named.every((item) => item.parsed);
      const tiles = named.map((item) => {
        const cols = Number(this.data.cols) || 3;
        const row = useNames ? item.parsed.row : Math.floor(item.index / cols);
        const col = useNames ? item.parsed.col : item.index % cols;
        return {
          path: item.file.tempFilePath,
          width: item.info.width,
          height: item.info.height,
          row,
          col,
          label: `${tileName(row, col)} · ${item.info.width}×${item.info.height}`,
        };
      });
      this.setData({
        tiles,
        resultPath: "",
        status: useNames
          ? `已按文件名识别 ${tiles.length} 个切块。`
          : `相册没有保留文件名，已按选择顺序排成 ${this.data.cols} 列。可改行列后重新选择。`,
        statusLevel: useNames ? "" : "hint-warn",
      });
    } catch (error) {
      if (error && error.errMsg && String(error.errMsg).includes("cancel")) return;
      wx.showToast({ title: error.message || "选图失败", icon: "none" });
    }
  },

  async run() {
    this.setData({ busy: true, statusLevel: "" });
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
      let used = 0;
      let top = 0;
      for (let row = 0; row < rows; row += 1) {
        let left = 0;
        for (let col = 0; col < cols; col += 1) {
          const cell = grid.get(`${row}:${col}`);
          if (!cell) throw new Error(`缺少 ${tileName(row, col)}`);
          const image = await loadImage(canvas, cell.path);
          ctx.drawImage(image, left, top);
          used += cell.width * cell.height;
          left += colWidths[col];
        }
        top += rowHeights[row];
      }
      const path = await canvasToPath(canvas);
      const discarded = width * height - used;
      this.setData({
        resultPath: path,
        status:
          discarded === 0
            ? `已拼回 ${width}×${height}，${formatPixels(used)} 像素全部回到画布。可保存到相册。`
            : `拼接完成，但还有 ${discarded} 像素空隙。请检查是否缺块或顺序不对。`,
        statusLevel: discarded === 0 ? "" : "hint-warn",
      });
    } catch (error) {
      this.setData({ status: error.message || "拼接失败", statusLevel: "hint-danger" });
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
