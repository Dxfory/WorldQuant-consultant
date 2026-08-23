# Pixel Intact 微信小程序

把「原图完整、无损切图、提高清晰度」做到微信里。选图时强制用原图，不走微信压缩。

手机上没有 Python / FSRCNN。超分是本地画布放大 + 清晰/锐化。更大画质请继续用 Mac 上的 `pixel-intact studio`。

## 用微信开发者工具打开

1. 安装 [微信开发者工具](https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html)
2. 选择「导入项目」
3. 目录选本文件夹：`pixel-intact/miniprogram`
4. AppID 可先用「测试号」，或填自己的小程序 AppID
5. 不使用云服务，直接编译

本仓库默认 `appid` 是 `touristappid`，只能在模拟器里看。要在手机预览，换成你的 AppID 或测试号。

## 使用

1. 点「选一张原图」，相册里选图（会尽量读原图像素）
2. **切图**：九宫格 / 四宫格 / 自己填行列。可勾选先提高清晰度再切
3. **清晰**：放大 1×–3×，再调清晰度和锐化
4. 点「处理」，再把当前图或某一块保存到相册
5. 首页「拼回切块」可把 `r00_c00.png` 这类图拼回去

## 上线前你要做的

- 在微信公众平台注册小程序，拿到 AppID
- 把 `project.config.json` 里的 `appid` 改成你的
- 类目建议选「工具 > 图片处理」
- 隐私协议里说明：图片只在手机本地处理，不上传服务器
