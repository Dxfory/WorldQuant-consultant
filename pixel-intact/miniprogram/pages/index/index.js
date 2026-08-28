const { chooseOriginalImage, getImageInfo } = require("../../utils/wximage");

Page({
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
      wx.switchTab({ url: "/pages/studio/studio" });
    } catch (error) {
      if (error && error.errMsg && String(error.errMsg).includes("cancel")) return;
      wx.showToast({ title: error.message || "选图失败", icon: "none" });
    }
  },

  goStudio() {
    wx.switchTab({ url: "/pages/studio/studio" });
  },

  goGuide() {
    wx.switchTab({ url: "/pages/guide/guide" });
  },

  goPrivacy() {
    wx.navigateTo({ url: "/pages/privacy/privacy" });
  },
});
