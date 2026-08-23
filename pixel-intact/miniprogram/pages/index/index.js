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
      app.globalData.name = file.tempFilePath.split("/").pop() || "image";
      wx.navigateTo({ url: "/pages/studio/studio" });
    } catch (error) {
      if (error && error.errMsg && error.errMsg.includes("cancel")) return;
      wx.showToast({ title: error.message || "选图失败", icon: "none" });
    }
  },

  goJoin() {
    wx.navigateTo({ url: "/pages/join/join" });
  },
});
