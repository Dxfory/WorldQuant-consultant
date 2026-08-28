#!/usr/bin/env python3
"""Generate a shareable Mac tutorial PDF for Pixel Intact."""

from pathlib import Path

from reportlab.lib.colors import Color, HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

FONT = "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"
pdfmetrics.registerFont(TTFont("Hei", FONT, subfontIndex=0))

INK = HexColor("#1a120c")
MUTE = HexColor("#5c5248")
AMBER = HexColor("#b56a24")
PAPER = HexColor("#f6efe4")
PANEL = HexColor("#efe4d4")
LINE = HexColor("#d4c4ae")
CODE_BG = HexColor("#211910")
CODE_FG = HexColor("#f3e6d2")
GOOD = HexColor("#3d6b32")

PAGE = A4
W, H = PAGE
MARGIN = 18 * mm
OUT = Path(__file__).with_name("Pixel-Intact-Mac-Guide.pdf")


def wrap(text: str, font: str, size: float, width: float) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in text:
        trial = current + char
        if pdfmetrics.stringWidth(trial, font, size) <= width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = char
    if current:
        lines.append(current)
    return lines or [""]


class Guide:
    def __init__(self) -> None:
        self.c = canvas.Canvas(str(OUT), pagesize=PAGE)
        self.c.setTitle("Pixel Intact 使用教程（Mac）")
        self.c.setAuthor("Zheng Xing")
        self.c.setSubject("把 Pixel Intact 拉到 Mac 并启动的中文教程")
        self.page = 0

    def new_page(self, title: str | None = None) -> None:
        if self.page:
            if getattr(self, "numbered", True):
                self.footer()
            self.c.showPage()
        self.page += 1
        self.c.setFillColor(PAPER)
        self.c.rect(0, 0, W, H, fill=1, stroke=0)
        if title:
            self.numbered = True
            self.c.setFillColor(AMBER)
            self.c.rect(MARGIN, H - 22 * mm, 8, 8, fill=1, stroke=0)
            self.c.setFillColor(INK)
            self.c.setFont("Hei", 16)
            self.c.drawString(MARGIN + 14, H - 21 * mm, title)
            self.y = H - 32 * mm
        else:
            self.y = H - MARGIN

    def footer(self) -> None:
        self.c.setStrokeColor(LINE)
        self.c.setLineWidth(0.4)
        self.c.line(MARGIN, 14 * mm, W - MARGIN, 14 * mm)
        self.c.setFillColor(MUTE)
        self.c.setFont("Hei", 8)
        self.c.drawString(MARGIN, 9 * mm, "Pixel Intact · 原图完整 · 无损切图 · 清晰度拉高")
        self.c.drawRightString(W - MARGIN, 9 * mm, f"{self.page}")

    def gap(self, amount: float = 8) -> None:
        self.y -= amount

    def need(self, height: float) -> None:
        if self.y - height < 22 * mm:
            self.new_page(self.current_title)

    def heading(self, text: str) -> None:
        self.need(16)
        self.c.setFillColor(INK)
        self.c.setFont("Hei", 13)
        self.c.drawString(MARGIN, self.y, text)
        self.y -= 7 * mm

    def para(self, text: str, color: Color = MUTE, size: float = 10) -> None:
        width = W - 2 * MARGIN
        lines = wrap(text, "Hei", size, width)
        self.need(len(lines) * 5.2 + 4)
        self.c.setFillColor(color)
        self.c.setFont("Hei", size)
        for line in lines:
            self.c.drawString(MARGIN, self.y, line)
            self.y -= 5.1 * mm
        self.y -= 1.5 * mm

    def bullets(self, items: list[str]) -> None:
        for item in items:
            width = W - 2 * MARGIN - 8
            lines = wrap(item, "Hei", 10, width)
            self.need(len(lines) * 5.1 + 3)
            self.c.setFillColor(AMBER)
            self.c.circle(MARGIN + 2, self.y + 1.6, 1.5, fill=1, stroke=0)
            self.c.setFillColor(MUTE)
            self.c.setFont("Hei", 10)
            for index, line in enumerate(lines):
                self.c.drawString(MARGIN + 8, self.y, line)
                self.y -= 5.1 * mm
            self.y -= 1.2 * mm

    def code(self, lines: list[str]) -> None:
        height = 8 + len(lines) * 5.4
        self.need(height + 6)
        self.c.setFillColor(CODE_BG)
        self.c.roundRect(MARGIN, self.y - height + 4, W - 2 * MARGIN, height, 3, fill=1, stroke=0)
        self.c.setFillColor(CODE_FG)
        self.c.setFont("Hei", 8.5)
        text_y = self.y - 4
        for line in lines:
            self.c.drawString(MARGIN + 6, text_y - 2, line)
            text_y -= 5.4
        self.y -= height + 5

    def step(self, number: str, title: str, body: str) -> None:
        self.need(22)
        self.c.setFillColor(AMBER)
        self.c.circle(MARGIN + 5, self.y + 1, 6, fill=1, stroke=0)
        self.c.setFillColor(white)
        self.c.setFont("Hei", 8)
        self.c.drawCentredString(MARGIN + 5, self.y - 1.2, number)
        self.c.setFillColor(INK)
        self.c.setFont("Hei", 11)
        self.c.drawString(MARGIN + 15, self.y - 1, title)
        self.y -= 7 * mm
        self.para(body)

    def cover(self) -> None:
        self.numbered = False
        self.new_page()
        self.numbered = True
        self.c.setFillColor(CODE_BG)
        self.c.rect(0, 0, W, H, fill=1, stroke=0)
        self.c.setFillColor(AMBER)
        self.c.rect(0, H - 8 * mm, W, 8 * mm, fill=1, stroke=0)
        self.c.rect(0, 0, W, 8 * mm, fill=1, stroke=0)
        self.c.setFillColor(HexColor("#e0a45a"))
        self.c.setFont("Hei", 12)
        self.c.drawString(MARGIN, H - 42 * mm, "PIXEL INTACT")
        self.c.setFillColor(HexColor("#f6efe4"))
        self.c.setFont("Hei", 28)
        self.c.drawString(MARGIN, H - 60 * mm, "使用教程")
        self.c.setFont("Hei", 16)
        self.c.drawString(MARGIN, H - 72 * mm, "Mac 电脑：下载、安装、启动、切图与提高清晰度")
        self.c.setStrokeColor(AMBER)
        self.c.setLineWidth(1)
        self.c.line(MARGIN, H - 80 * mm, MARGIN + 46 * mm, H - 80 * mm)
        notes = [
            "适合发给同事或朋友，按步骤就能在自己的 Mac 上跑起来。",
            "处理都在本地完成，原图不会上传到做好图这类网站。",
            "目标：原图完整、切图不丢像素、清晰度比普通在线切图更高。",
        ]
        y = H - 100 * mm
        self.c.setFillColor(HexColor("#d7cbb8"))
        self.c.setFont("Hei", 11)
        for note in notes:
            self.c.drawString(MARGIN, y, note)
            y -= 9 * mm
        self.c.setFillColor(HexColor("#b7aa94"))
        self.c.setFont("Hei", 9)
        self.c.drawString(MARGIN, 28 * mm, "仓库  github.com/Dxfory/WorldQuant-consultant")
        self.c.drawString(MARGIN, 22 * mm, "分支  cursor/pixel-intact-studio-fe20")
        self.c.drawString(MARGIN, 16 * mm, "打开  http://127.0.0.1:8765/")

    def build(self) -> Path:
        self.cover()

        self.current_title = "1. 这是什么"
        self.new_page(self.current_title)
        self.para(
            "Pixel Intact 是本地图像工作室。对照做好图（zuohaotu.com/cut-image.aspx）这类在线切图站，它不先压像素、不丢边，切完还可以拼回原图。",
            INK,
            11,
        )
        self.heading("它解决什么问题")
        self.bullets(
            [
                "原图完整：按原始宽高读入，不上传压缩。",
                "无损切图：按九宫格、行列或像素块切开。除不尽的余数会留下来，丢弃像素为 0。",
                "提高清晰度：本地 Lanczos，或 FSRCNN 超分，可放大 2×–4×。",
                "拼回原图：切块文件名是 r00_c00.png 这类，可以还原。",
            ]
        )
        self.heading("和做好图的差别")
        self.bullets(
            [
                "做好图常常把图压小，边缘余数也可能丢掉。",
                "这里切图只裁切、不重采样；清晰模式才会增加像素。",
                "这不是 AI 重绘。构图不变，只提高采样密度和边缘清晰度。",
            ]
        )

        self.current_title = "2. 开始前准备"
        self.new_page(self.current_title)
        self.para("用 Mac 自带的「终端」App。需要 Git 和 Python 3.10 或更高。", INK, 11)
        self.heading("第一次请先装开发者工具")
        self.code(["xcode-select --install"])
        self.para("弹出窗口就点「安装」。装好后检查：")
        self.code(["git --version", "python3 --version"])
        self.para("如果没有 Python，先安装 Homebrew（https://brew.sh），再执行：")
        self.code(["brew install python"])
        self.heading("建议放在个人目录")
        self.para("下面命令默认把项目放到用户主目录，也就是访达里的「个人」文件夹。")

        self.current_title = "3. 拉到这台 Mac"
        self.new_page(self.current_title)
        self.step("1", "下载仓库", "打开终端，复制下面整段，回车。")
        self.code(
            [
                "cd ~",
                "git clone https://github.com/Dxfory/WorldQuant-consultant.git",
                "cd WorldQuant-consultant",
                "git checkout cursor/pixel-intact-studio-fe20",
                "cd pixel-intact",
            ]
        )
        self.step("2", "安装依赖", "这一步会装 Pillow，以及可选的超分库。需要几分钟，等它跑完。")
        self.code(['python3 -m pip install -e ".[dev,sr]"'])
        self.para("如果提示权限不够，改用：")
        self.code(['python3 -m pip install --user -e ".[dev,sr]"'])
        self.heading("电脑上已经有这个仓库时")
        self.code(
            [
                "cd ~/WorldQuant-consultant",
                "git fetch origin",
                "git checkout cursor/pixel-intact-studio-fe20",
                "git pull origin cursor/pixel-intact-studio-fe20",
                "cd pixel-intact",
                'python3 -m pip install -e ".[dev,sr]"',
            ]
        )

        self.current_title = "4. 启动工作室"
        self.new_page(self.current_title)
        self.step("1", "启动本地服务", "用下面这条最稳，不必管命令有没有进 PATH。")
        self.code(
            [
                "cd ~/WorldQuant-consultant/pixel-intact",
                "python3 -m pixel_intact.cli studio",
            ]
        )
        self.step("2", "打开页面", "终端出现地址后，用 Safari 或 Chrome 打开：")
        self.code(["http://127.0.0.1:8765/"])
        self.step("3", "停掉", "回到那个终端窗口，按 Control + C。")
        self.heading("以后再开，只需要两行")
        self.code(
            [
                "cd ~/WorldQuant-consultant/pixel-intact",
                "python3 -m pixel_intact.cli studio",
            ]
        )
        self.para("不要关掉这个终端。关掉就等于关掉工作室。")

        self.current_title = "5. 页面上怎么用"
        self.new_page(self.current_title)
        self.heading("放入原图")
        self.bullets(
            [
                "把图片拖到左侧，或点击选择，也可以 Command + V 粘贴。",
                "看尺寸和总像素。这里按完整像素读入。",
                "如果是 JPEG，界面会提醒：相机或网站可能已经压过，无法找回丢失细节。",
            ]
        )
        self.heading("切图")
        self.bullets(
            [
                "点「切图」。可用九宫格、四宫格、16 宫，或自己填行列。",
                "也可以按像素块切，例如 512×512。余块会单独留下。",
                "放入原图后，右侧会画切割线，并预估每块像素。",
                "勾选「先提高清晰度再切」，每块像素会更多。",
                "点「处理」，再点「下载」得到 zip。点击小图可单独存一块。",
            ]
        )
        self.heading("清晰")
        self.bullets(
            [
                "勾选「用本地引擎（画质更高）」。",
                "超分选「FSRCNN 超分」，放大选 2× 或 4×。",
                "点「处理」。拖底部滑杆对比原图。鼠标移到图上可 1:1 看像素。",
                "导出可选 PNG 无损、JPEG 98、WebP 无损。",
            ]
        )
        self.heading("拼回")
        self.bullets(
            [
                "把 r00_c00.png 这类切块一起放进去。",
                "点「处理」，应得到和原图一样完整的图。",
            ]
        )

        self.current_title = "6. 命令行（可选）"
        self.new_page(self.current_title)
        self.para("不会用页面时，也可以在终端处理。先进入项目目录：", INK, 11)
        self.code(["cd ~/WorldQuant-consultant/pixel-intact"])
        self.heading("看原图信息")
        self.code(["python3 -m pixel_intact.cli inspect 你的图片.png"])
        self.heading("切成九宫格")
        self.code(
            [
                "python3 -m pixel_intact.cli slice 你的图片.png --cols 3 --rows 3 --out tiles"
            ]
        )
        self.heading("提高清晰度（推荐 FSRCNN）")
        self.code(
            [
                "python3 -m pixel_intact.cli enhance 你的图片.png --scale 2 --engine fsr --out photo-fsr.png"
            ]
        )
        self.heading("先超分再切")
        self.code(
            [
                "python3 -m pixel_intact.cli slice 你的图片.png --cols 3 --rows 3 --scale 2 --engine fsr --out tiles"
            ]
        )
        self.heading("整夹批量")
        self.code(
            [
                "python3 -m pixel_intact.cli batch 图片文件夹 --scale 2 --engine fsr --out enhanced"
            ]
        )
        self.heading("拼回")
        self.code(
            [
                "python3 -m pixel_intact.cli join tiles --out restored.png --original 你的图片.png"
            ]
        )

        self.current_title = "7. 常见问题"
        self.new_page(self.current_title)
        self.heading("打不开 127.0.0.1:8765")
        self.para("确认启动工作室的终端还开着，并且没有报错。换 Chrome 再试。不要用 https。")
        self.heading("提示找不到 pixel-intact 命令")
        self.para("不要用 pixel-intact studio，改用：")
        self.code(["python3 -m pixel_intact.cli studio"])
        self.heading("pip 报错或权限不够")
        self.code(['python3 -m pip install --user -e ".[dev,sr]"'])
        self.heading("FSRCNN 超分是灰的")
        self.para("回到 pixel-intact 目录重新安装超分依赖：")
        self.code(['python3 -m pip install -e ".[sr]"'])
        self.para("然后必须用 python3 -m pixel_intact.cli studio 启动，不要只用 python3 -m http.server。")
        self.heading("图很大、提示输出太大")
        self.para("把放大改成 2×，或先切图，再单独提高某一块的清晰度。")
        self.heading("发给别人时请一起说清这两点")
        self.bullets(
            [
                "必须拉分支 cursor/pixel-intact-studio-fe20，主分支还没有这个工具。",
                "处理在自己电脑上完成，请对方用自己的原图。",
            ]
        )
        self.gap(6)
        self.c.setFillColor(GOOD)
        self.c.setFont("Hei", 10)
        self.c.drawString(MARGIN, self.y, "教程到这里就可以转发给别人了。")
        self.y -= 7 * mm
        self.para("拉取请求：https://github.com/Dxfory/WorldQuant-consultant/pull/4")

        self.footer()
        self.c.save()
        return OUT


if __name__ == "__main__":
    path = Guide().build()
    print(path)
