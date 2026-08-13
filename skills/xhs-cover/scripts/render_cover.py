#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小红书封面渲染器 —— HTML/CSS → 1080×1440 PNG。

为什么不直接让 image_gen 把标题画上去：
    AI 出图对中文字形的还原一直不可靠（缺笔画、错字、字距乱）。
    封面标题是要被人读的，不能赌。
    所以分工：image_gen 负责背景和氛围，中文标题走本地渲染，像素级可控。

风格：zine 系列参考 gc-minimal-zine-poster 的 style-system ——
纸纹负空间 + 单一高彩度锚色 + 安静的衬线/打字机字 + 印刷缺陷（网点、颗粒、套印偏移）。
差别在于那套是 3:5 海报、留白 70–90%、字很小；小红书封面是 3:4，而且要在信息流
缩略图里读得清。所以 zine 把留白降到约 55–70%、标题字号提到可读区间；
zine-pure 才是忠实照搬比例的版本。

依赖：系统里有 Edge 或 Chrome。Windows 自带 Edge，零安装。
只用标准库。不联网。

用法：
    # 默认 zine 风格
    python render_cover.py --title "京都下雨那天|我什么都没干" \
        --label "travel [03]" --caption "一个人旅行 · 第 3 天" \
        --micro "kyoto 2026.08" --sig "@vivian" --out cover.png

    # 忠实 zine（留白拉满，字很小）
    python render_cover.py --title "京都下雨那天|我什么都没干" --style zine-pure --out cover.png

    # 照片窗口版（照片不出血，压网点去饱和）
    python render_cover.py --title "京都下雨那天|我什么都没干" \
        --bg cover-bg.png --style zine-photo --out cover.png

    # 换纸色和锚色
    python render_cover.py --title "..." --tone kraft --accent tomato --out cover.png

    # 锚按主题换（26 个形状，--anchor 看清单；none 关掉）
    python render_cover.py --title "..." --anchor stars --out cover.png
    python render_cover.py --title "..." --anchor timeline --out cover.png

    # 库里没有就自己画（viewBox 0 0 100 100，颜色用 currentColor）
    python render_cover.py --title "..." \
        --anchor-svg '<circle cx="50" cy="50" r="30" fill="currentColor"/>' --out cover.png

    # 改完 cover.html 后重新渲染
    python render_cover.py --from-html cover.html --out cover.png

标题里的 `|` 是手动换行，`[xxx]` 是锚色强调。
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "cover-template.html"
W, H = 1080, 1440

# ---------------------------------------------------------------- 调色板
# 纸色 —— 对应 style-system 的 paper tones
PAPER_TONES = {
    "warm-white": "#F7F3EC",
    "ivory": "#F2EADB",
    "light-gray": "#EBE9E3",
    "old-yellow": "#EFE3C4",
    "khaki": "#E3DBC2",
    "kraft": "#DDCEB1",
}

# 高彩度锚色 —— 对应 style-system 的 color anchor 列表
ACCENTS = {
    "cobalt": "#1B45C8",
    "ultramarine": "#2A2BA8",
    "cyan": "#0093D0",
    "violet": "#6A3CC0",
    "magenta": "#E5006D",
    "pink": "#FF4FA3",
    "lemon": "#E4BE00",
    "pear": "#7FA82B",
    "orange": "#F06A1E",
    "tomato": "#D63A22",
}

# ---------------------------------------------------------------- 锚形状库
# style-system 里锚的形态是「剪影 / 实心油墨块 / 印刷插图 / 标本 / 不规则剪裁 /
# 环绕标记 / 抽象材质窗口」—— 不是永远一个方块。
# 所以这里备一批 SVG，每篇按主题挑；挑不到就用 --anchor-svg 现画一个。
#
# 约定：viewBox 0 0 100 100，颜色一律用 currentColor（由 CSS 的 --accent 注入），
# 这样套印偏移那层自动变成第二色。


def _star_ring(n: int = 12, r: float = 38, sr: float = 9) -> str:
    """欧盟式的星环。n 颗五角星均匀排在半径 r 的圆上。"""
    import math

    out = []
    for i in range(n):
        a = -math.pi / 2 + i * 2 * math.pi / n
        cx, cy = 50 + r * math.cos(a), 50 + r * math.sin(a)
        pts = []
        for k in range(10):
            ang = -math.pi / 2 + k * math.pi / 5
            rad = sr if k % 2 == 0 else sr * 0.42
            pts.append(f"{cx + rad * math.cos(ang):.2f},{cy + rad * math.sin(ang):.2f}")
        out.append(f'<polygon points="{" ".join(pts)}"/>')
    return f'<g fill="currentColor">{"".join(out)}</g>'


def _dot_grid(cols: int = 4, rows: int = 4, r: float = 7.5) -> str:
    step = 100 / cols
    dots = [
        f'<circle cx="{step * (c + .5):.1f}" cy="{step * (rw + .5):.1f}" r="{r}"/>'
        for c in range(cols) for rw in range(rows)
    ]
    return f'<g fill="currentColor">{"".join(dots)}</g>'


ANCHORS: dict[str, str] = {
    # ---- 几何 / 通用 ----
    "block": '<polygon points="2,4 97,0 100,95 5,100" fill="currentColor"/>',
    "disc": '<circle cx="50" cy="50" r="48" fill="currentColor"/>',
    "ring": '<circle cx="50" cy="50" r="43" fill="none" stroke="currentColor" stroke-width="8"/>',
    "arc": '<path d="M50 2 A48 48 0 0 1 50 98 Z" fill="currentColor"/>',
    "triangle": '<polygon points="50,3 98,95 2,95" fill="currentColor"/>',
    "cross": ('<g fill="currentColor"><rect x="41" y="2" width="18" height="96"/>'
              '<rect x="2" y="41" width="96" height="18"/></g>'),
    "slash": ('<g stroke="currentColor" stroke-width="9">'
              '<line x1="4" y1="72" x2="72" y2="4"/><line x1="28" y1="96" x2="96" y2="28"/></g>'),
    "bracket": ('<g fill="none" stroke="currentColor" stroke-width="9">'
                '<path d="M30 4 H4 V38"/><path d="M70 96 H96 V62"/></g>'),

    # ---- 数据 / 时间 ----
    "bars": ('<g fill="currentColor"><rect x="4" y="48" width="17" height="52"/>'
             '<rect x="29" y="22" width="17" height="78"/>'
             '<rect x="54" y="62" width="17" height="38"/>'
             '<rect x="79" y="6" width="17" height="94"/></g>'),
    # 大圆点标"当前进行到这一步"，刻度一高两低做出方向感
    "timeline": ('<g stroke="currentColor" stroke-width="6">'
                 '<line x1="2" y1="50" x2="98" y2="50"/>'
                 '<line x1="14" y1="24" x2="14" y2="76"/>'
                 '<line x1="36" y1="33" x2="36" y2="67"/>'
                 '<line x1="88" y1="33" x2="88" y2="67"/></g>'
                 '<circle cx="62" cy="50" r="16" fill="currentColor"/>'),
    "steps": ('<g fill="currentColor"><rect x="2" y="74" width="30" height="26"/>'
              '<rect x="35" y="48" width="30" height="52"/>'
              '<rect x="68" y="14" width="30" height="86"/></g>'),
    "dots-grid": _dot_grid(),
    "arrow": ('<g stroke="currentColor" stroke-width="8" fill="none">'
              '<line x1="4" y1="50" x2="84" y2="50"/><path d="M62 24 L94 50 L62 76"/></g>'),

    # ---- 制度 / 法规 / 官方 ----
    "stars": _star_ring(),
    "stamp": ('<g fill="none" stroke="currentColor"><rect x="4" y="4" width="92" height="92"'
              ' rx="14" stroke-width="8"/><rect x="21" y="21" width="58" height="58"'
              ' rx="6" stroke-width="4"/></g>'),
    # 天平：立柱 + 底座 + 横梁 + 两根吊绳 + 两个浅碗形托盘
    "scale": ('<g stroke="currentColor" stroke-width="7" fill="none" stroke-linecap="round">'
              '<line x1="50" y1="20" x2="50" y2="86"/>'
              '<line x1="28" y1="92" x2="72" y2="92"/>'
              '<line x1="8" y1="24" x2="92" y2="24"/>'
              '<line x1="18" y1="24" x2="18" y2="40"/>'
              '<line x1="82" y1="24" x2="82" y2="40"/>'
              '<path d="M2 40 Q18 58 34 40"/><path d="M66 40 Q82 58 98 40"/></g>'),
    "shield": ('<path d="M50 3 L94 18 V52 C94 76 74 91 50 98 C26 91 6 76 6 52 V18 Z"'
               ' fill="currentColor"/>'),
    "ban": ('<g fill="none" stroke="currentColor" stroke-width="10">'
            '<circle cx="50" cy="50" r="43"/><line x1="20" y1="80" x2="80" y2="20"/></g>'),

    # ---- 自然 / 生活 ----
    "moon": ('<path d="M62 4 A48 48 0 1 0 62 96 A38 38 0 1 1 62 4 Z" fill="currentColor"/>'),
    "waves": ('<g fill="none" stroke="currentColor" stroke-width="8">'
              '<path d="M2 30 Q26 12 50 30 T98 30"/><path d="M2 58 Q26 40 50 58 T98 58"/>'
              '<path d="M2 86 Q26 68 50 86 T98 86"/></g>'),
    "rain": ('<g stroke="currentColor" stroke-width="8" stroke-linecap="round">'
             '<line x1="16" y1="8" x2="4" y2="44"/><line x1="42" y1="8" x2="30" y2="44"/>'
             '<line x1="68" y1="8" x2="56" y2="44"/><line x1="30" y1="56" x2="18" y2="92"/>'
             '<line x1="56" y1="56" x2="44" y2="92"/><line x1="82" y1="56" x2="70" y2="92"/></g>'),
    "sun": ('<circle cx="50" cy="50" r="24" fill="currentColor"/>'
            '<g stroke="currentColor" stroke-width="7" stroke-linecap="round">'
            '<line x1="50" y1="2" x2="50" y2="18"/><line x1="50" y1="82" x2="50" y2="98"/>'
            '<line x1="2" y1="50" x2="18" y2="50"/><line x1="82" y1="50" x2="98" y2="50"/>'
            '<line x1="16" y1="16" x2="27" y2="27"/><line x1="73" y1="73" x2="84" y2="84"/>'
            '<line x1="16" y1="84" x2="27" y2="73"/><line x1="73" y1="27" x2="84" y2="16"/></g>'),
    "window-frame": ('<g fill="none" stroke="currentColor" stroke-width="8">'
                     '<rect x="5" y="5" width="90" height="90"/></g>'
                     '<g stroke="currentColor" stroke-width="6">'
                     '<line x1="50" y1="5" x2="50" y2="95"/>'
                     '<line x1="5" y1="50" x2="95" y2="50"/></g>'),
    "cup": ('<g fill="none" stroke="currentColor" stroke-width="8">'
            '<path d="M14 26 H72 V60 A29 29 0 0 1 14 60 Z"/>'
            '<path d="M72 34 H90 A12 12 0 0 1 90 58 H72"/>'
            '<line x1="10" y1="94" x2="80" y2="94"/></g>'),

    # ---- 抽象材质窗口 ----
    # 用了 <pattern> 的形状必须把 id 写成 xxx__UID__ —— 锚会渲染两层（套印偏移），
    # id 重复的话两层都会引用到第一个 pattern，第二层的颜色就错了。
    "halftone": ('<defs><pattern id="ht__UID__" width="11" height="11"'
                 ' patternUnits="userSpaceOnUse">'
                 '<circle cx="5.5" cy="5.5" r="3.6" fill="currentColor"/></pattern></defs>'
                 '<circle cx="50" cy="50" r="48" fill="url(#ht__UID__)"/>'),
    "grain-square": ('<defs><pattern id="gs__UID__" width="9" height="9"'
                     ' patternUnits="userSpaceOnUse">'
                     '<rect width="4.4" height="4.4" fill="currentColor"/></pattern></defs>'
                     '<rect x="2" y="2" width="96" height="96" fill="url(#gs__UID__)"/>'),
}


# 有些形状天生是横向的。给它们一个扁的 viewBox，容器的长宽比再从 viewBox 推出来 ——
# 两边必须一致，否则 SVG 的 preserveAspectRatio 会把图形缩到只占容器的一小块。
DEFAULT_VIEWBOX = "0 0 100 100"
ANCHOR_VIEWBOX: dict[str, str] = {
    "timeline": "0 18 100 64",
    "arrow": "0 20 100 60",
    "waves": "0 4 100 92",
}


def anchor_viewbox(name: str) -> str:
    return ANCHOR_VIEWBOX.get(name, DEFAULT_VIEWBOX)


def anchor_box(name: str, size: int) -> tuple[int, int]:
    """容器尺寸：高度用基准边长，宽度按 viewBox 的长宽比算出来。"""
    _, _, w, h = (float(x) for x in anchor_viewbox(name).split())
    return round(size * w / h), size


def anchor_svg(name: str | None, custom: str | None) -> str:
    """
    返回 viewBox 100×100 的 SVG 内容。custom 优先（文件路径或直接的 SVG 字符串）。
    形状里的 __UID__ 由调用方按层替换成不同后缀。
    """
    if custom:
        p = Path(custom)
        raw = p.read_text(encoding="utf-8") if p.is_file() else custom
        # 已经是完整 <svg> 就原样用，否则包一层
        if "<svg" in raw:
            return raw
        return f'<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">{raw}</svg>'

    if name not in ANCHORS:
        sys.exit(f"[错误] 没有叫 {name} 的锚形状。可选：{', '.join(sorted(ANCHORS))}\n"
                 f"  想要别的形状就用 --anchor-svg 给一个 SVG（viewBox 0 0 100 100，"
                 f"颜色用 currentColor）")
    return (f'<svg viewBox="{anchor_viewbox(name)}" xmlns="http://www.w3.org/2000/svg">'
            f'{ANCHORS[name]}</svg>')


# 内容簇位置 —— 对应 style-system 的 cluster positioning options
POSITIONS = {
    "lower-left": ("flex-end", "flex-start", "left"),
    "upper-right": ("flex-start", "flex-end", "right"),
    "center-low": ("flex-end", "center", "center"),
    "center-high": ("flex-start", "center", "center"),
    "left-middle": ("center", "flex-start", "left"),
    "right-middle": ("center", "flex-end", "right"),
}

# ---------------------------------------------------------------- 风格预设
STYLES = {
    # ============ zine 系列 ============
    "zine": {
        # 主推。留白约 60%，标题仍能在信息流缩略图里读清。
        "tone": "ivory", "accent": "cobalt",
        "ink": "#241F1A", "ink_soft": "#7C7466", "accent2": "#8A8172",
        "safe_x": 130, "safe_y": "11%",
        "title_font": "var(--serif)", "title_weight": 400,
        "title_cap": 100, "title_track": 0.05, "title_leading": 1.52,
        "caption_size": 27,
        "pos": "lower-left",
        "grain": 0.20, "scan": 0.0, "marks": 0.45,
        "rule": True, "dash": False,
        "anchor": True, "anchor_shape": "block", "anchor_w": 132, "anchor_h": 132,
        "photo": False, "bgfull": False,
        "dots": True, "dots_pos": "right: 132px; top: 17%;",
        "inset": 0,
    },
    "zine-pure": {
        # 忠实版：留白 75%+，字很小，单一小锚。
        # 好看，但在信息流缩略图里标题会偏小 —— 适合已有粉丝基础、不靠封面抓陌生人时用。
        "tone": "warm-white", "accent": "tomato",
        "ink": "#2A2520", "ink_soft": "#8A8378", "accent2": "#9A9184",
        "safe_x": 196, "safe_y": "16%",
        "title_font": "var(--serif)", "title_weight": 400,
        "title_cap": 62, "title_track": 0.14, "title_leading": 1.85,
        "caption_size": 21,
        "pos": "center-low",
        "grain": 0.26, "scan": 0.0, "marks": 0.5,
        "rule": False, "dash": False,
        "anchor": True, "anchor_shape": "block", "anchor_w": 92, "anchor_h": 92,
        "photo": False, "bgfull": False,
        # 点群要躲开内容簇。zine-pure 的簇在 center-low，所以点群放右上。
        "dots": True, "dots_pos": "right: 196px; top: 14%;",
        "inset": 0,
    },
    "zine-photo": {
        # 照片不出血，装在窗口里，去饱和 + 压网点 + 轻微单色油墨叠加。
        "tone": "warm-white", "accent": "cobalt",
        "ink": "#241F1A", "ink_soft": "#7C7466", "accent2": "#8A8172",
        "safe_x": 122, "safe_y": "9%",
        "title_font": "var(--serif)", "title_weight": 400,
        "title_cap": 88, "title_track": 0.05, "title_leading": 1.5,
        "caption_size": 25,
        "pos": "center-low",
        "grain": 0.22, "scan": 0.10, "marks": 0.45,
        "rule": False, "dash": True,
        "anchor": False, "anchor_shape": "block", "anchor_w": 0, "anchor_h": 0,
        "photo": True, "photo_h": 690, "photo_rot": -0.7,
        "photo_gray": 0.88, "halftone": 0.45, "photo_ink": 0.14,
        "bgfull": False,
        "dots": False, "dots_pos": "",
        "inset": 0,
    },

    # ============ 传统大字封面（想要冲击力时用） ============
    "plain": {
        "tone": "#F4EFE7", "accent": "tomato",
        "ink": "#1F1B16", "ink_soft": "#6E675C", "accent2": "#8A8172",
        "safe_x": 84, "safe_y": "8%",
        "title_font": "var(--sans)", "title_weight": 900,
        "title_cap": 168, "title_track": 0.01, "title_leading": 1.24,
        "caption_size": 40,
        "pos": "center-low",
        "grain": 0.0, "scan": 0.0, "marks": 0.0,
        "rule": False, "dash": False,
        "anchor": False, "anchor_shape": "block", "anchor_w": 0, "anchor_h": 0,
        "photo": False, "bgfull": False,
        "dots": False, "dots_pos": "",
        "inset": 0,
    },
    "photo": {
        "tone": "#2A2A2A", "accent": "lemon",
        "ink": "#FFFFFF", "ink_soft": "#E8E4DC", "accent2": "#8A8172",
        "safe_x": 84, "safe_y": "8%",
        "title_font": "var(--sans)", "title_weight": 900,
        "title_cap": 168, "title_track": 0.01, "title_leading": 1.24,
        "caption_size": 40,
        "pos": "center-low",
        "grain": 0.0, "scan": 0.0, "marks": 0.0,
        "rule": False, "dash": False,
        "anchor": False, "anchor_shape": "block", "anchor_w": 0, "anchor_h": 0,
        "photo": False, "bgfull": True,
        "scrim": ("linear-gradient(to top, rgba(0,0,0,.74) 0%,"
                  " rgba(0,0,0,.40) 42%, rgba(0,0,0,.12) 100%)"),
        "shadow": "text-shadow: 0 3px 24px rgba(0,0,0,.45);",
        "dots": False, "dots_pos": "",
        "inset": 0,
    },
}

DEFAULT_SCRIM = "none"

# 账号级预设。锚每篇按主题换，但纸色/锚色/署名应该固定 —— 主页九宫格才有辨识度。
# 放在 profile/cover.json，脚本会从当前目录往上找。CLI 参数优先级更高。
PRESET_FILE = "profile/cover.json"
PRESET_KEYS = ("style", "tone", "accent", "accent2", "ink", "sig", "pos",
               "safe_x", "title_track")


def load_preset(explicit: str | None) -> tuple[dict, str | None]:
    """返回 (预设内容, 来源路径)。找不到就返回空字典。"""
    if explicit:
        p = Path(explicit)
        if not p.is_file():
            sys.exit(f"[错误] 找不到预设文件：{p}")
        candidates = [p]
    else:
        # 从当前目录往上找，再退到脚本所在仓库的根
        here = Path.cwd().resolve()
        candidates = [d / PRESET_FILE for d in [here, *here.parents]]
        repo = Path(__file__).resolve().parents[3]
        candidates.append(repo / PRESET_FILE)

    for c in candidates:
        if c.is_file():
            try:
                data = json.loads(c.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                sys.exit(f"[错误] 预设不是合法 JSON：{c}\n  {exc}")
            unknown = set(data) - set(PRESET_KEYS)
            if unknown:
                print(f"[提示] 预设里有不认识的字段，已忽略：{', '.join(sorted(unknown))}",
                      file=sys.stderr)
            return {k: v for k, v in data.items() if k in PRESET_KEYS}, str(c)
    return {}, None


# ---------------------------------------------------------------- 浏览器
def find_browser() -> str:
    if os.environ.get("BROWSER_PATH") and Path(os.environ["BROWSER_PATH"]).is_file():
        return os.environ["BROWSER_PATH"]

    for c in (
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ):
        if Path(c).is_file():
            return c

    for name in ("msedge", "microsoft-edge", "microsoft-edge-stable", "google-chrome",
                 "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        found = shutil.which(name)
        if found:
            return found

    sys.exit(
        "[错误] 找不到 Edge 或 Chrome。\n"
        "  Windows 应该自带 Edge，装在非默认位置就用环境变量指定：\n"
        "    $env:BROWSER_PATH = 'C:\\path\\to\\msedge.exe'"
    )


def png_size(path: Path) -> tuple[int, int] | None:
    try:
        data = path.read_bytes()[:24]
        if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        return struct.unpack(">II", data[16:24])
    except OSError:
        return None


def shoot(browser: str, html: Path, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    # --screenshot 必须给绝对路径：无头浏览器按它自己的工作目录解析相对路径，
    # 会写到临时 profile 目录里去（然后报 Access is denied）。
    shot = out.resolve()

    last = ""
    # 临时 profile：避免和已经开着的 Edge/Chrome 抢用户目录
    with tempfile.TemporaryDirectory(prefix="xhs-cover-") as profile:
        tail = [
            "--disable-gpu",
            "--hide-scrollbars",
            "--force-device-scale-factor=1",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
            "--no-sandbox",
            f"--user-data-dir={profile}",
            f"--window-size={W},{H}",
            f"--screenshot={shot}",
            html.resolve().as_uri(),
        ]
        # 不同版本的 headless 开关行为不一样，两种都试
        for flag in ("--headless", "--headless=old"):
            try:
                proc = subprocess.run([browser, flag, *tail], capture_output=True, timeout=90)
            except subprocess.TimeoutExpired:
                continue
            if out.is_file() and out.stat().st_size > 0:
                return
            last = (proc.stderr or b"").decode("utf-8", "replace")[-600:]

    sys.exit(f"[错误] 截图失败。浏览器输出：\n{last}")


# ---------------------------------------------------------------- 组装
def resolve_color(value: str, table: dict[str, str]) -> str:
    """接受调色板名字或直接的 CSS 颜色值。"""
    return table.get(value.strip().lower(), value)


def bg_css(bg: Path | None, html_out: Path) -> str:
    if not bg:
        return "none"
    if not bg.is_file():
        sys.exit(f"[错误] 背景图不存在：{bg}")
    # 同目录就用相对路径，cover.html 更好改；否则内嵌 data URI 保证自包含
    if bg.resolve().parent == html_out.resolve().parent:
        return f'url("{bg.name}")'
    mime = mimetypes.guess_type(bg.name)[0] or "image/png"
    b64 = base64.b64encode(bg.read_bytes()).decode("ascii")
    return f'url("data:{mime};base64,{b64}")'


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def accent_markup(text: str, tag: str) -> str:
    """把 [xxx] 换成上锚色的标签。"""
    parts, pos = [], 0
    for m in re.finditer(r"\[([^\]]+)\]", text):
        parts.append(esc(text[pos:m.start()]))
        parts.append(f"<{tag}>{esc(m.group(1))}</{tag}>")
        pos = m.end()
    parts.append(esc(text[pos:]))
    return "".join(parts)


def char_width(s: str) -> float:
    """CJK 算 1，其余算 0.55。用来反推字号。"""
    s = re.sub(r"[\[\]]", "", s)
    return sum(0.55 if ord(c) < 0x2E80 else 1.0 for c in s)


def title_html(title: str, cap: int, track: float, usable: float) -> tuple[str, int]:
    """
    `|` 换行，`[xxx]` 上锚色。
    字号按最长那行反推，扣掉字距，保证塞得进可用宽度而不意外折行。
    """
    lines = [ln.strip() for ln in title.split("|") if ln.strip()]
    if not lines:
        sys.exit("[错误] 标题是空的。")

    widest = max(char_width(ln) for ln in lines)
    # 每个字实际占 size*(1+track)
    size = min(cap, int(usable / max(widest * (1 + track), 1) * 0.98))
    body = "<br>".join(accent_markup(ln, "em") for ln in lines)
    return body, size


def build_html(args, cfg: dict, html_out: Path) -> str:
    tpl = TEMPLATE.read_text(encoding="utf-8")

    paper = resolve_color(args.tone or cfg["tone"], PAPER_TONES)
    accent = resolve_color(args.accent or cfg["accent"], ACCENTS)
    accent2 = resolve_color(args.accent2 or cfg["accent2"], ACCENTS)

    safe_x = args.safe_x or cfg["safe_x"]
    usable = W - safe_x * 2 - cfg.get("inset", 0)
    track = cfg["title_track"] if args.title_track is None else args.title_track

    t_html, auto_size = title_html(args.title, cfg["title_cap"], track, usable)
    size = args.title_size or auto_size

    pos = args.pos or cfg["pos"]
    justify, items, align = POSITIONS[pos]

    has_photo = bool(cfg.get("photo") and args.bg)
    has_bgfull = bool(cfg.get("bgfull") and args.bg)

    def show(flag: bool) -> str:
        return "block" if flag else "none"

    # 锚：形状每篇按主题换。--anchor none 关掉，--anchor-svg 用自己画的。
    shape = args.anchor or cfg.get("anchor_shape", "block")
    want_anchor = cfg["anchor"] and not has_photo and shape != "none" and not args.no_anchor
    svg = anchor_svg(shape, args.anchor_svg) if want_anchor else ""
    # 两层用不同 id 后缀，避免 <pattern> id 撞车
    svg_ghost = svg.replace("__UID__", "a")
    svg_main = svg.replace("__UID__", "b")
    # 横向形状按 ANCHOR_BOX 拉宽压扁，不要硬塞进正方形
    a_w, a_h = anchor_box(shape, args.anchor_size or cfg["anchor_w"])

    label_html = accent_markup(args.label, "b") if args.label else ""
    caption_html = "<br>".join(esc(x.strip()) for x in args.caption.split("|")) if args.caption else ""

    repl = {
        "__PAPER__": paper,
        "__INK__": args.ink or cfg["ink"],
        "__INK_SOFT__": cfg["ink_soft"],
        "__ACCENT__": accent,
        "__ACCENT2__": accent2,

        "__TITLE_SIZE__": str(size),
        "__TITLE_TRACK__": str(track),
        "__TITLE_LEADING__": str(cfg["title_leading"]),
        "__CAPTION_SIZE__": str(cfg["caption_size"]),
        # 带单位一起传 —— safe_y 是百分比，模板里不能再补 px
        "__SAFE_X__": f"{safe_x}px",
        "__SAFE_Y__": cfg["safe_y"],

        "__GRAIN__": str(0.0 if args.no_grain else cfg["grain"]),
        "__SCAN__": str(cfg.get("scan", 0.0)),
        "__MARKS__": str(0.0 if args.no_marks else cfg["marks"]),

        "__JUSTIFY__": justify,
        "__ITEMS__": items,
        "__ALIGN__": align,

        "__LABEL_DISPLAY__": show(bool(label_html)),
        "__RULE_DISPLAY__": show(cfg["rule"]),
        "__DASH_DISPLAY__": show(cfg["dash"]),

        "__ANCHOR_DISPLAY__": show(want_anchor),
        "__ANCHOR_W__": str(a_w),
        "__ANCHOR_H__": str(a_h),
        "__ANCHOR_SVG_GHOST__": svg_ghost,
        "__ANCHOR_SVG_MAIN__": svg_main,

        "__PHOTO_DISPLAY__": show(has_photo),
        "__PHOTO_H__": str(cfg.get("photo_h", 0)),
        "__PHOTO_ROT__": str(cfg.get("photo_rot", 0)),
        "__PHOTO_GRAY__": str(cfg.get("photo_gray", 0)),
        "__HALFTONE__": str(0.0 if args.no_halftone else cfg.get("halftone", 0)),
        "__PHOTO_INK__": str(cfg.get("photo_ink", 0)),

        "__BGFULL_DISPLAY__": show(has_bgfull),
        "__SCRIM__": cfg.get("scrim", DEFAULT_SCRIM),
        "__BG_URL__": bg_css(Path(args.bg) if args.bg else None, html_out),

        "__TITLE_FONT__": cfg["title_font"],
        "__TITLE_WEIGHT__": str(cfg["title_weight"]),
        "__TITLE_SHADOW__": cfg.get("shadow", "") if has_bgfull else "",

        "__CAPTION_DISPLAY__": show(bool(caption_html)),
        "__MICRO_DISPLAY__": show(bool(args.micro)),
        "__SIG_DISPLAY__": show(bool(args.sig)),
        "__DOTS_DISPLAY__": show(cfg["dots"] and not args.no_marks),
        "__DOTS_POS__": cfg["dots_pos"],

        "__STYLE__": args.style,
        "__EXTRA_CLASS__": "",
        "__LABEL_HTML__": label_html,
        "__TITLE_HTML__": t_html,
        "__CAPTION_HTML__": caption_html,
        "__MICRO_HTML__": esc(args.micro) if args.micro else "",
        "__SIG_HTML__": esc(args.sig) if args.sig else "",
    }

    for k, v in repl.items():
        tpl = tpl.replace(k, v)

    leftover = re.findall(r"__[A-Z0-9_]+__", tpl)
    if leftover:
        sys.exit(f"[错误] 模板里有没填的占位符：{sorted(set(leftover))}")
    return tpl


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(
        description="把小红书封面渲染成 1080×1440 PNG",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "标题里 `|` 是换行，`[xxx]` 上锚色。\n"
            f"纸色：{', '.join(PAPER_TONES)}\n"
            f"锚色：{', '.join(ACCENTS)}\n"
            f"位置：{', '.join(POSITIONS)}"
        ),
    )
    ap.add_argument("--title", help="主标题。`|` 换行，`[xxx]` 上锚色")
    ap.add_argument("--label", help="顶部打字机小标签，如 'travel [03]'")
    ap.add_argument("--caption", help="标题下的说明，可用 `|` 换行")
    ap.add_argument("--micro", help="右侧竖排微文字，如 'kyoto 2026.08'")
    ap.add_argument("--sig", help="底部署名，如 '@vivian'")
    ap.add_argument("--sub", dest="caption", help="--caption 的别名")
    ap.add_argument("--tag", dest="label", help="--label 的别名")

    ap.add_argument("--bg", help="背景图（image_gen 出的，或你的实拍）")
    ap.add_argument("--style", choices=list(STYLES), help="默认 zine（或 profile/cover.json 里的值）")
    ap.add_argument("--preset", help=f"账号预设 JSON，默认自动找 {PRESET_FILE}")
    ap.add_argument("--no-preset", dest="no_preset", action="store_true", help="忽略预设文件")
    ap.add_argument("--tone", help=f"纸色：{', '.join(PAPER_TONES)}，或直接给 CSS 颜色")
    ap.add_argument("--accent", help=f"锚色：{', '.join(ACCENTS)}，或直接给 CSS 颜色")
    ap.add_argument("--accent2", help="套印偏移的第二色，必须次要")
    ap.add_argument("--ink", help="正文墨色")
    ap.add_argument("--pos", choices=list(POSITIONS), help="内容簇位置")
    ap.add_argument("--anchor", metavar="SHAPE",
                    help="锚形状，按主题挑一个；none 关掉。可选：" + ", ".join(sorted(ANCHORS)))
    ap.add_argument("--anchor-svg", dest="anchor_svg", metavar="SVG",
                    help="自己画的锚：SVG 文件路径，或直接给 SVG 字符串"
                         "（viewBox 0 0 100 100，颜色用 currentColor）")
    ap.add_argument("--anchor-size", dest="anchor_size", type=int, help="锚的边长像素")
    ap.add_argument("--no-anchor", dest="no_anchor", action="store_true", help="不要锚")
    ap.add_argument("--safe-x", type=int, dest="safe_x", help="左右留白像素")
    ap.add_argument("--title-size", type=int, help="标题字号，默认按字数自动算")
    ap.add_argument("--title-track", type=float, help="标题字距（em）")
    ap.add_argument("--no-grain", action="store_true", help="关掉纸纹颗粒")
    ap.add_argument("--no-marks", action="store_true", help="关掉套准标记和点群")
    ap.add_argument("--no-halftone", action="store_true", help="关掉照片网点")

    ap.add_argument("--out", default="cover.png", help="输出 PNG，默认 cover.png")
    ap.add_argument("--from-html", help="跳过模板，直接渲染这个 HTML")
    args = ap.parse_args()

    # 账号预设填空白，CLI 显式给的值优先
    preset, preset_src = ({}, None) if args.no_preset else load_preset(args.preset)
    applied = {}
    for k, v in preset.items():
        if getattr(args, k, None) is None:
            setattr(args, k, v)
            applied[k] = v          # 只记真正生效的，被 CLI 覆盖的不算
    if args.style is None:
        args.style = "zine"

    out = Path(args.out)
    browser = find_browser()

    if args.from_html:
        html = Path(args.from_html)
        if not html.is_file():
            sys.exit(f"[错误] 找不到 HTML：{html}")
    else:
        if not args.title:
            ap.error("要么给 --title，要么给 --from-html")
        html = out.with_suffix(".html")
        html.parent.mkdir(parents=True, exist_ok=True)
        html.write_text(build_html(args, STYLES[args.style], html), encoding="utf-8")

    shoot(browser, html, out)

    size = png_size(out)
    kb = out.stat().st_size / 1024
    anchor_note = f"  anchor={args.anchor}" if args.anchor else ""
    print(f"✅ {out}  ({kb:.0f} KB)  style={args.style}{anchor_note}")
    if preset_src:
        used = ", ".join(f"{k}={v}" for k, v in applied.items()) or "（全部被命令行覆盖）"
        print(f"   预设：{preset_src}")
        print(f"   生效：{used}")
    if not args.from_html:
        print(f"   排版源文件：{html}  ← 想微调就改这个，然后：")
        print(f"   python {Path(__file__).name} --from-html {html} --out {out}")

    if size:
        ok = size == (W, H)
        print(f"   尺寸：{size[0]}×{size[1]}"
              + ("  ✅ 3:4，符合小红书封面规范" if ok else f"  ⚠️ 期望 {W}×{H}，请检查"))
        if not ok:
            return 1
    else:
        print("   ⚠️ 读不出 PNG 尺寸，文件可能有问题")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
