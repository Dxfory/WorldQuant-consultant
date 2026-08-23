const { assertSafeSize, applyClarityAndSharpen } = require("./core");

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

async function drawSource(canvas, src, width, height) {
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  ctx.imageSmoothingEnabled = false;
  const image = await loadImage(canvas, src);
  ctx.clearRect(0, 0, width, height);
  ctx.drawImage(image, 0, 0, width, height);
  return { canvas, ctx, image };
}

async function cropTile(offscreenFactory, source, tile) {
  const canvas = offscreenFactory(tile.width, tile.height);
  const ctx = canvas.getContext("2d");
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(source, tile.left, tile.top, tile.width, tile.height, 0, 0, tile.width, tile.height);
  return canvasToPath(canvas);
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
  chooseOriginalImage,
  getImageInfo,
  getCanvas,
  loadImage,
  canvasToPath,
  saveToAlbum,
  drawSource,
  cropTile,
  enhanceOnCanvas,
};
