# Pixel Intact

High-fidelity image studio: keep the original complete, cut it without losing pixels, then raise clarity.

做好图 [在线切图](https://www.zuohaotu.com/cut-image.aspx) 的问题是像素偏低、余数容易被丢掉。这个库反过来做三件事：

1. **原图完整** — 按原始宽高读入，不先缩小，不上传压缩。
2. **无损切图** — 按行列或按像素块切开。除不尽的余数会分给前几列/行，或单独输出余块，所以 `discarded_pixels = 0`。
3. **提高清晰度** — 本地 Lanczos，或可选 FSRCNN 超分（比浏览器插值更清楚）。可以先增强再切。

浏览器里处理切图和预览；Python CLI 适合批量出图，并用像素级比对确认「切完再拼回 == 原图」。

## Studio

```bash
cd pixel-intact
python -m pip install -e .
pixel-intact studio
```

打开 `http://127.0.0.1:8765/`。也可以直接：

```bash
python -m http.server 8765 --directory web
```

流程：

- 放入原图，看尺寸和总像素。
- **切图**：九宫格 / 四宫格 / 任意行列，或按固定像素块。放入原图后立刻画切割线和每块像素预估。勾选「先提高清晰度再切」可先放大再切。
- **清晰**：`pixel-intact studio` 会接上本地引擎。可选 FSRCNN 超分、拖杆对比原图、1:1 看像素、中心预览调滑杆。默认不改整体颜色。
- **拼回**：把 `r00_c00.png` 这类切块还原成完整图。
- 大图会限制输出边长，避免浏览器画布崩溃；切块缩略图可点选单独下载。

全部在本地完成，原图不会被第三方网站压小。

## Python library

```python
from pixel_intact import enhance_image, join_tiles, slice_image

plan = slice_image("photo.png", "tiles", cols=3, rows=3)
assert plan.complete and plan.discarded_pixels == 0

result = join_tiles("tiles", "restored.png", original_path="photo.png")
assert result.matches_original

enhance_image("photo.png", "photo-2x.png")
```

## CLI

```bash
pixel-intact inspect photo.png
pixel-intact slice photo.png --cols 3 --rows 3 --out tiles
pixel-intact slice photo.png --cols 3 --rows 3 --scale 2 --out tiles
pixel-intact join tiles --out restored.png --original photo.png
pixel-intact enhance photo.png --scale 2 --clarity 0.3 --out photo-2x.png
pixel-intact enhance photo.png --scale 2 --engine fsr --out photo-fsr.png
pixel-intact batch photos --scale 2 --engine fsr --out enhanced
```

按尺寸切（余块会留下来）：

```bash
pixel-intact slice photo.png --tile-width 512 --tile-height 512 --out tiles
```

## Why this is not the same as zuohaotu

| | 做好图切图 | Pixel Intact |
| --- | --- | --- |
| 读入 | 网站侧处理，像素容易被压低 | 本地按原图像素读入 |
| 除不尽时 | 边缘像素常被丢掉 | 余数并入前排，或输出余块 |
| 切完能否还原 | 不保证 | `join` 后像素应完全一致 |
| 清晰度 | 低像素输出 | Lanczos + 清晰/锐化，可 2×–4× |

This is restoration of sample density and edge contrast, not generative outpainting. The composition stays the same.

## Tests

```bash
python -m pip install -e ".[dev]"
python -m pytest
node tests/test_processor_plan.mjs
```

## New GitHub repository

This folder is a standalone project. To publish it as its own GitHub repo:

```bash
gh repo create Dxfory/pixel-intact --public --source=pixel-intact --remote=origin --push
```

If you create an empty `Dxfory/pixel-intact` repository, this directory can be pushed there as-is.
