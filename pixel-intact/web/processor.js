const TILE_NAME = (row, col) =>
  `r${String(row).padStart(2, "0")}_c${String(col).padStart(2, "0")}.png`;

export function spanSizes(length, count) {
  if (count < 1) throw new Error("count must be at least 1");
  if (length < count) throw new Error(`cannot split ${length}px into ${count} parts`);
  const base = Math.floor(length / count);
  const extra = length % count;
  return Array.from({ length: count }, (_, index) => base + (index < extra ? 1 : 0));
}

export function planSlice(width, height, options) {
  const { cols, rows, tileWidth, tileHeight } = options;
  let colSizes;
  let rowSizes;
  let remainderDistributed = false;

  if (cols && rows) {
    colSizes = spanSizes(width, cols);
    rowSizes = spanSizes(height, rows);
    remainderDistributed = width % cols !== 0 || height % rows !== 0;
  } else if (tileWidth && tileHeight) {
    if (tileWidth < 1 || tileHeight < 1) throw new Error("tile size must be at least 1px");
    colSizes = [];
    for (let left = 0; left < width; left += tileWidth) {
      colSizes.push(Math.min(tileWidth, width - left));
    }
    rowSizes = [];
    for (let top = 0; top < height; top += tileHeight) {
      rowSizes.push(Math.min(tileHeight, height - top));
    }
  } else {
    throw new Error("choose either a grid or a tile size");
  }

  const tiles = [];
  let top = 0;
  rowSizes.forEach((tileH, row) => {
    let left = 0;
    colSizes.forEach((tileW, col) => {
      tiles.push({
        row,
        col,
        left,
        top,
        width: tileW,
        height: tileH,
        name: TILE_NAME(row, col),
      });
      left += tileW;
    });
    top += tileH;
  });

  const exportedPixels = tiles.reduce((sum, tile) => sum + tile.width * tile.height, 0);
  return {
    sourceWidth: width,
    sourceHeight: height,
    rows: rowSizes.length,
    cols: colSizes.length,
    tiles,
    discardedPixels: width * height - exportedPixels,
    remainderDistributed,
    exportedPixels,
    complete: exportedPixels === width * height,
  };
}

export async function loadFileToCanvas(file) {
  const bitmap = await createImageBitmap(file);
  const width = bitmap.width;
  const height = bitmap.height;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d", { willReadFrequently: true, alpha: true });
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(bitmap, 0, 0);
  bitmap.close?.();
  return {
    canvas,
    ctx,
    width,
    height,
    name: file.name,
    type: file.type,
    bytes: file.size,
  };
}

export function cropTile(sourceCanvas, tile) {
  const canvas = document.createElement("canvas");
  canvas.width = tile.width;
  canvas.height = tile.height;
  const ctx = canvas.getContext("2d", { alpha: true });
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(
    sourceCanvas,
    tile.left,
    tile.top,
    tile.width,
    tile.height,
    0,
    0,
    tile.width,
    tile.height,
  );
  return canvas;
}

export function joinCanvases(pieces) {
  const maxRow = Math.max(...pieces.map((piece) => piece.row));
  const maxCol = Math.max(...pieces.map((piece) => piece.col));
  const rows = maxRow + 1;
  const cols = maxCol + 1;
  const grid = new Map(pieces.map((piece) => [`${piece.row}:${piece.col}`, piece]));

  const rowHeights = [];
  for (let row = 0; row < rows; row += 1) {
    const heights = [];
    for (let col = 0; col < cols; col += 1) {
      const cell = grid.get(`${row}:${col}`);
      if (cell) heights.push(cell.canvas.height);
    }
    if (!heights.length) throw new Error(`missing entire row ${row}`);
    rowHeights.push(Math.max(...heights));
  }

  const colWidths = [];
  for (let col = 0; col < cols; col += 1) {
    const widths = [];
    for (let row = 0; row < rows; row += 1) {
      const cell = grid.get(`${row}:${col}`);
      if (cell) widths.push(cell.canvas.width);
    }
    if (!widths.length) throw new Error(`missing entire column ${col}`);
    colWidths.push(Math.max(...widths));
  }

  const canvas = document.createElement("canvas");
  canvas.width = colWidths.reduce((sum, value) => sum + value, 0);
  canvas.height = rowHeights.reduce((sum, value) => sum + value, 0);
  const ctx = canvas.getContext("2d", { alpha: true });
  ctx.imageSmoothingEnabled = false;

  let usedPixels = 0;
  let top = 0;
  for (let row = 0; row < rows; row += 1) {
    let left = 0;
    for (let col = 0; col < cols; col += 1) {
      const cell = grid.get(`${row}:${col}`);
      if (!cell) throw new Error(`missing tile ${TILE_NAME(row, col)}`);
      ctx.drawImage(cell.canvas, left, top);
      usedPixels += cell.canvas.width * cell.canvas.height;
      left += colWidths[col];
    }
    top += rowHeights[row];
  }

  return {
    canvas,
    rows,
    cols,
    usedPixels,
    discardedPixels: canvas.width * canvas.height - usedPixels,
    complete: usedPixels === canvas.width * canvas.height,
  };
}

function clampByte(value) {
  return value < 0 ? 0 : value > 255 ? 255 : value;
}

function boxBlur(source, width, height, radius) {
  const dest = new Uint8ClampedArray(source.length);
  const windowSize = radius * 2 + 1;
  const temp = new Uint8ClampedArray(source.length);

  for (let y = 0; y < height; y += 1) {
    for (let channel = 0; channel < 4; channel += 1) {
      let sum = 0;
      for (let kx = -radius; kx <= radius; kx += 1) {
        const x = Math.min(width - 1, Math.max(0, kx));
        sum += source[(y * width + x) * 4 + channel];
      }
      for (let x = 0; x < width; x += 1) {
        temp[(y * width + x) * 4 + channel] = Math.round(sum / windowSize);
        const leave = Math.min(width - 1, Math.max(0, x - radius));
        const enter = Math.min(width - 1, Math.max(0, x + radius + 1));
        sum += source[(y * width + enter) * 4 + channel] - source[(y * width + leave) * 4 + channel];
      }
    }
  }

  for (let x = 0; x < width; x += 1) {
    for (let channel = 0; channel < 4; channel += 1) {
      let sum = 0;
      for (let ky = -radius; ky <= radius; ky += 1) {
        const y = Math.min(height - 1, Math.max(0, ky));
        sum += temp[(y * width + x) * 4 + channel];
      }
      for (let y = 0; y < height; y += 1) {
        dest[(y * width + x) * 4 + channel] = Math.round(sum / windowSize);
        const leave = Math.min(height - 1, Math.max(0, y - radius));
        const enter = Math.min(height - 1, Math.max(0, y + radius + 1));
        sum += temp[(enter * width + x) * 4 + channel] - temp[(leave * width + x) * 4 + channel];
      }
    }
  }
  return dest;
}

function applyClarityAndSharpen(imageData, clarity, sharpness) {
  const { data, width, height } = imageData;
  const blur = boxBlur(data, width, height, 5);
  const fine = boxBlur(data, width, height, 1);
  const out = new Uint8ClampedArray(data.length);

  for (let i = 0; i < data.length; i += 4) {
    for (let channel = 0; channel < 3; channel += 1) {
      const src = data[i + channel];
      const mid = src + (src - blur[i + channel]) * clarity;
      const sharp = mid + (src - fine[i + channel]) * sharpness;
      out[i + channel] = clampByte(sharp);
    }
    out[i + 3] = data[i + 3];
  }
  return new ImageData(out, width, height);
}

export function enhanceCanvas(sourceCanvas, { scale = 2, clarity = 0.35, sharpness = 0.85 } = {}) {
  const width = Math.max(1, Math.round(sourceCanvas.width * scale));
  const height = Math.max(1, Math.round(sourceCanvas.height * scale));
  const scaled = document.createElement("canvas");
  scaled.width = width;
  scaled.height = height;
  const ctx = scaled.getContext("2d", { willReadFrequently: true, alpha: true });
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(sourceCanvas, 0, 0, width, height);

  const refined = applyClarityAndSharpen(ctx.getImageData(0, 0, width, height), clarity, sharpness);
  ctx.putImageData(refined, 0, 0);
  return scaled;
}

export function canvasToBlob(canvas, type = "image/png", quality = 1) {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (!blob) reject(new Error("failed to encode image"));
      else resolve(blob);
    }, type, quality);
  });
}

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export function formatPixels(value) {
  return new Intl.NumberFormat("en-US").format(value);
}

export function parseTileName(name) {
  const match = name.match(/r(\d+)_c(\d+)\.(png|jpg|jpeg|webp)$/i);
  if (!match) return null;
  return { row: Number(match[1]), col: Number(match[2]) };
}
