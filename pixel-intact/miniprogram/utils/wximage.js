const { assertSafeSize, applyClarityAndSharpen, MAX_PIXELS } = require("./core");

function chooseOriginalImage(count = 1) {
  return new Promise((resolve, reject) => {
    wx.chooseMedia({
      count,
      mediaType: ["image"],
      sourceType: ["album", "camera"],
      sizeType: ["original"],
      success: resolve,
      fail: reject,
    });
  });
}

function getImageInfo(src) {
  return new Promise((resolve, reject) => {
    wx.getImageInfo({
      src,
      success: resolve,
      fail: reject,
    });
  });
}

function getCanvas(selector, component) {
  return new Promise((resolve, reject) => {
    const query = component
      ? wx.createSelectorQuery().in(component)
      : wx.createSelectorQuery();
    query
      .select(selector)
      .fields({ node: true, size: true })
      .exec((res) => {
        if (!res || !res[0] || !res[0].node) {
          reject(new Error("画布还没准备好，请稍后再试"));
          return;
        }
        resolve(res[0].node);
      });
  });
}

function loadImage(canvas, src) {
  return new Promise((resolve, reject) => {
    const image = canvas.createImage();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("图片读取失败"));
    image.src = src;
  });
}

function createOffscreen(width, height) {
  assertSafeSize(width, height);
  const canvas = wx.createOffscreenCanvas({ type: "2d", width, height });
  canvas.width = width;
  canvas.height = height;
  return canvas;
}

function canvasToPath(canvas, fileType = "png") {
  return new Promise((resolve, reject) => {
    wx.canvasToTempFilePath({
      canvas,
      fileType,
      quality: 1,
      destWidth: canvas.width,
      destHeight: canvas.height,
      success: (res) => resolve(res.tempFilePath),
      fail: reject,
    });
  });
}

async function saveToAlbum(filePath) {
  try {
    await wx.authorize({ scope: "scope.writePhotosAlbum" });
  } catch (error) {
    await new Promise((resolve, reject) => {
      wx.openSetting({
        success: (res) => {
          if (res.authSetting["scope.writePhotosAlbum"]) resolve();
          else reject(new Error("需要相册权限才能保存"));
        },
        fail: reject,
      });
    });
  }
  return new Promise((resolve, reject) => {
    wx.saveImageToPhotosAlbum({
      filePath,
      success: resolve,
      fail: reject,
    });
  });
}

async function saveManyToAlbum(paths, onProgress) {
  for (let index = 0; index < paths.length; index += 1) {
    if (onProgress) onProgress(index + 1, paths.length);
    await saveToAlbum(paths[index]);
  }
}

function waitFrame() {
  return new Promise((resolve) => setTimeout(resolve, 30));
}

async function cropFromImage(sourceImage, tile) {
  const canvas = createOffscreen(tile.width, tile.height);
  const ctx = canvas.getContext("2d");
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(
    sourceImage,
    tile.left,
    tile.top,
    tile.width,
    tile.height,
    0,
    0,
    tile.width,
    tile.height,
  );
  return {
    canvas,
    path: await canvasToPath(canvas),
    width: tile.width,
    height: tile.height,
  };
}

async function enhanceRegion(sourceImage, tile, settings) {
  const scale = Number(settings.scale || 1);
  const outW = Math.max(1, Math.round(tile.width * scale));
  const outH = Math.max(1, Math.round(tile.height * scale));
  assertSafeSize(outW, outH);
  const canvas = createOffscreen(outW, outH);
  const ctx = canvas.getContext("2d");
  ctx.imageSmoothingEnabled = true;
  ctx.drawImage(
    sourceImage,
    tile.left,
    tile.top,
    tile.width,
    tile.height,
    0,
    0,
    outW,
    outH,
  );
  const clarity = Number(settings.clarity || 0);
  const sharpness = Number(settings.sharpness || 0);
  if ((clarity > 0 || sharpness > 0) && outW * outH <= 4_000_000) {
    const imageData = ctx.getImageData(0, 0, outW, outH);
    const refined = applyClarityAndSharpen(imageData, clarity, sharpness);
    imageData.data.set(refined.data);
    ctx.putImageData(imageData, 0, 0);
  }
  return {
    canvas,
    path: await canvasToPath(canvas),
    width: outW,
    height: outH,
  };
}

async function enhanceOnCanvas(canvas, sourceImage, width, height, settings) {
  const scale = Number(settings.scale || 2);
  const outW = Math.max(1, Math.round(width * scale));
  const outH = Math.max(1, Math.round(height * scale));
  assertSafeSize(outW, outH);
  canvas.width = outW;
  canvas.height = outH;
  const ctx = canvas.getContext("2d");
  ctx.imageSmoothingEnabled = true;
  ctx.drawImage(sourceImage, 0, 0, outW, outH);
  const clarity = Number(settings.clarity || 0);
  const sharpness = Number(settings.sharpness || 0);
  if ((clarity > 0 || sharpness > 0) && outW * outH <= 4_000_000) {
    const imageData = ctx.getImageData(0, 0, outW, outH);
    const refined = applyClarityAndSharpen(imageData, clarity, sharpness);
    imageData.data.set(refined.data);
    ctx.putImageData(imageData, 0, 0);
  }
  return canvasToPath(canvas);
}

module.exports = {
  MAX_PIXELS,
  chooseOriginalImage,
  getImageInfo,
  getCanvas,
  loadImage,
  createOffscreen,
  canvasToPath,
  saveToAlbum,
  saveManyToAlbum,
  waitFrame,
  cropFromImage,
  enhanceRegion,
  enhanceOnCanvas,
};
