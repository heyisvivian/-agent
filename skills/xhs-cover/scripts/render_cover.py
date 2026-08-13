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

    # 改完 cover.html 后重新渲染
    python render_cover.py --from-html cover.html --out cover.png

标题里的 `|` 是手动换行，`[xxx]` 是锚色强调。
"""

from __future__ import annotations

import argparse
import base64
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
        "anchor": True, "anchor_w": 132, "anchor_h": 132,
        "anchor_clip": "polygon(0% 2%, 97% 0%, 100% 96%, 3% 100%)",
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
        "anchor": True, "anchor_w": 86, "anchor_h": 86,
        "anchor_clip": "polygon(0% 4%, 96% 0%, 100% 95%, 5% 100%)",
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
        "anchor": False, "anchor_w": 0, "anchor_h": 0, "anchor_clip": "none",
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
        "anchor": False, "anchor_w": 0, "anchor_h": 0, "anchor_clip": "none",
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
        "anchor": False, "anchor_w": 0, "anchor_h": 0, "anchor_clip": "none",
        "photo": False, "bgfull": True,
        "scrim": ("linear-gradient(to top, rgba(0,0,0,.74) 0%,"
                  " rgba(0,0,0,.40) 42%, rgba(0,0,0,.12) 100%)"),
        "shadow": "text-shadow: 0 3px 24px rgba(0,0,0,.45);",
        "dots": False, "dots_pos": "",
        "inset": 0,
    },
}

DEFAULT_SCRIM = "none"


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
            f"--screenshot={out}",
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

        "__ANCHOR_DISPLAY__": show(cfg["anchor"] and not has_photo),
        "__ANCHOR_W__": str(cfg["anchor_w"]),
        "__ANCHOR_H__": str(cfg["anchor_h"]),
        "__ANCHOR_CLIP__": cfg["anchor_clip"],

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
    ap.add_argument("--style", default="zine", choices=list(STYLES), help="默认 zine")
    ap.add_argument("--tone", help=f"纸色：{', '.join(PAPER_TONES)}，或直接给 CSS 颜色")
    ap.add_argument("--accent", help=f"锚色：{', '.join(ACCENTS)}，或直接给 CSS 颜色")
    ap.add_argument("--accent2", help="套印偏移的第二色，必须次要")
    ap.add_argument("--ink", help="正文墨色")
    ap.add_argument("--pos", choices=list(POSITIONS), help="内容簇位置")
    ap.add_argument("--safe-x", type=int, dest="safe_x", help="左右留白像素")
    ap.add_argument("--title-size", type=int, help="标题字号，默认按字数自动算")
    ap.add_argument("--title-track", type=float, help="标题字距（em）")
    ap.add_argument("--no-grain", action="store_true", help="关掉纸纹颗粒")
    ap.add_argument("--no-marks", action="store_true", help="关掉套准标记和点群")
    ap.add_argument("--no-halftone", action="store_true", help="关掉照片网点")

    ap.add_argument("--out", default="cover.png", help="输出 PNG，默认 cover.png")
    ap.add_argument("--from-html", help="跳过模板，直接渲染这个 HTML")
    args = ap.parse_args()

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
    print(f"✅ {out}  ({kb:.0f} KB)  style={args.style}")
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
