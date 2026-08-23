const MAX_EDGE = 4096;
const MAX_PIXELS = 12_000_000;

function tileName(row, col) {
  return `r${String(row).padStart(2, "0")}_c${String(col).padStart(2, "0")}.png`;
}

function spanSizes(length, count) {
  if (count < 1) throw new Error("count must be at least 1");
  if (length < count) throw new Error(`无法把 ${length}px 分成 ${count} 份`);
  const base = Math.floor(length / count);
  const extra = length % count;
  return Array.from({ length: count }, (_, index) => base + (index < extra ? 1 : 0));
}

function planSlice(width, height, options) {
  const { cols, rows, tileWidth, tileHeight } = options;
  let colSizes;
  let rowSizes;
  let remainderDistributed = false;

  if (cols && rows) {
    colSizes = spanSizes(width, cols);
    rowSizes = spanSizes(height, rows);
    remainderDistributed = width % cols !== 0 || height % rows !== 0;
  } else if (tileWidth && tileHeight) {
    if (tileWidth < 1 || tileHeight < 1) throw new Error("块尺寸至少 1px");
    colSizes = [];
    for (let left = 0; left < width; left += tileWidth) {
      colSizes.push(Math.min(tileWidth, width - left));
    }
    rowSizes = [];
    for (let top = 0; top < height; top += tileHeight) {
      rowSizes.push(Math.min(tileHeight, height - top));
    }
  } else {
    throw new Error("请选择行列或像素尺寸");
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
        name: tileName(row, col),
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
    colSizes,
    rowSizes,
  };
}

function describePlan(plan) {
  return `${plan.cols}×${plan.rows} 块，总像素 ${plan.exportedPixels}，丢弃 ${plan.discardedPixels}`;
}

function parseTileName(name) {
  const match = String(name || "").match(/r(\d+)_c(\d+)\.(png|jpg|jpeg|webp)$/i);
  if (!match) return null;
  return { row: Number(match[1]), col: Number(match[2]) };
}

function assertSafeSize(width, height) {
  if (width > MAX_EDGE || height > MAX_EDGE || width * height > MAX_PIXELS) {
    throw new Error(`输出 ${width}×${height} 太大，手机画布容易崩溃。请把放大改小，或先切再提高单块清晰度。`);
  }
}

function clampByte(value) {
  return value < 0 ? 0 : value > 255 ? 255 : value;
}

function boxBlur(source, width, height, radius) {
  const dest = new Uint8ClampedArray(source.length);
  const windowSize = radius * 2 + 1;
  const temp = new Uint8ClampedArray(source.length);
  for (let y = 0; y < height; y += 1) {
    for (let channel = 0; channel < 3; channel += 1) {
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
    for (let channel = 0; channel < 3; channel += 1) {
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
  for (let i = 3; i < source.length; i += 4) dest[i] = source[i];
  return dest;
}

function applyClarityAndSharpen(imageData, clarity, sharpness) {
  const { data, width, height } = imageData;
  const blur = clarity > 0 ? boxBlur(data, width, height, 4) : null;
  const fine = sharpness > 0 ? boxBlur(data, width, height, 1) : null;
  const out = new Uint8ClampedArray(data.length);
  for (let i = 0; i < data.length; i += 4) {
    for (let channel = 0; channel < 3; channel += 1) {
      let value = data[i + channel];
      if (blur) value += (data[i + channel] - blur[i + channel]) * clarity;
      if (fine) value += (data[i + channel] - fine[i + channel]) * sharpness;
      out[i + channel] = clampByte(value);
    }
    out[i + 3] = data[i + 3];
  }
  return { data: out, width, height };
}

module.exports = {
  MAX_EDGE,
  MAX_PIXELS,
  tileName,
  spanSizes,
  planSlice,
  describePlan,
  parseTileName,
  assertSafeSize,
  applyClarityAndSharpen,
};
