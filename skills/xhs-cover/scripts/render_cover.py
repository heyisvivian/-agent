#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小红书封面渲染器 —— HTML/CSS → 1080×1440 PNG。

为什么不直接让 image_gen 把标题画上去：
    AI 出图对中文字形的还原一直不可靠（缺笔画、错字、字距乱）。
    封面标题是要被人读的，不能赌。
    所以分工：image_gen 负责背景和氛围，中文标题走本地渲染，像素级可控。

依赖：系统里有 Edge 或 Chrome。Windows 自带 Edge，零安装。
只用标准库。不联网。

用法：
    # 纯色背景（最稳，可读性最好）
    python render_cover.py --title "京都下雨那天|我什么都没干" --out cover.png

    # 用 image_gen 生成的背景图
    python render_cover.py --title "京都下雨那天|我什么都没干" \
        --bg cover-bg.png --style photo --out cover.png

    # 标题里用 [方括号] 强调
    python render_cover.py --title "三天京都|我只去了[四个]地方" --out cover.png

    # 改完 cover.html 后重新渲染
    python render_cover.py --from-html cover.html --out cover.png

标题里的 `|` 是手动换行，`[xxx]` 是强调色。
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
SAFE_X = 84                      # 与模板里的 --safe-x 保持一致
USABLE = W - SAFE_X * 2          # 912px 可用宽度
TITLE_SIZE_CAP = 170             # 再大就压迫了

# 每种风格的默认值。CLI 参数可覆盖任意一项。
STYLES = {
    "plain": {  # 纯色背景 + 深色字。没有背景图时的默认，可读性最好
        "bgcolor": "#f4efe7",
        "fg": "#1f1b16",
        "accent": "#c2452d",
        "scrim": "none",
        "shadow": "",
        "justify": "center",
        "band_bg": "transparent",
        "tag_fg": "#ffffff",
        "inset": 0,
    },
    "photo": {  # 照片背景 + 底部渐变遮罩 + 白字
        "bgcolor": "#2a2a2a",
        "fg": "#ffffff",
        "accent": "#ffd166",
        "scrim": "linear-gradient(to top, rgba(0,0,0,.72) 0%, rgba(0,0,0,.38) 42%, rgba(0,0,0,.12) 100%)",
        "shadow": "text-shadow: 0 3px 24px rgba(0,0,0,.45);",
        "justify": "flex-end",
        "band_bg": "transparent",
        "tag_fg": "#1f1b16",
        "inset": 0,
    },
    "band": {  # 照片背景 + 文字垫半透明色块。照片很花时用这个
        "bgcolor": "#2a2a2a",
        "fg": "#1f1b16",
        "accent": "#c2452d",
        "scrim": "rgba(0,0,0,.10)",
        "shadow": "",
        "justify": "center",
        "band_bg": "rgba(255,255,255,.92)",
        "tag_fg": "#ffffff",
        "inset": 48,   # 每行色块的左右 padding 22px×2，留点余量
    },
    "note": {  # 左侧竖线，像便签。适合文字型、心情型
        "bgcolor": "#faf7f2",
        "fg": "#22201d",
        "accent": "#4a7c59",
        "scrim": "none",
        "shadow": "",
        "justify": "center",
        "band_bg": "transparent",
        "tag_fg": "#ffffff",
        "inset": 46,   # 左侧 10px 竖线 + 32px padding
    },
}


# ------------------------------------------------------------------ 浏览器
def find_browser() -> str:
    """找一个 Chromium 系浏览器。Windows 自带 Edge。"""
    if os.environ.get("BROWSER_PATH"):
        p = os.environ["BROWSER_PATH"]
        if Path(p).is_file():
            return p

    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    for c in candidates:
        if Path(c).is_file():
            return c

    for name in ("msedge", "microsoft-edge", "microsoft-edge-stable",
                 "google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        found = shutil.which(name)
        if found:
            return found

    sys.exit(
        "[错误] 找不到 Edge 或 Chrome。\n"
        "  Windows 应该自带 Edge，如果装在非默认位置，用环境变量指定：\n"
        "    $env:BROWSER_PATH = 'C:\\path\\to\\msedge.exe'"
    )


def png_size(path: Path) -> tuple[int, int] | None:
    """直接读 PNG 头拿尺寸，不引 Pillow。"""
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

    # 临时 profile：避免和已经开着的 Edge/Chrome 抢用户目录
    with tempfile.TemporaryDirectory(prefix="xhs-cover-") as profile:
        base = [
            browser,
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
            cmd = base[:1] + [flag] + base[1:]
            try:
                proc = subprocess.run(cmd, capture_output=True, timeout=90)
            except subprocess.TimeoutExpired:
                continue
            if out.is_file() and out.stat().st_size > 0:
                return
            last = (proc.stderr or b"").decode("utf-8", "replace")[-600:]

    sys.exit(f"[错误] 截图失败。浏览器输出：\n{last}")


# ------------------------------------------------------------------ 组装 HTML
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


def title_html(title: str, style: str, inset: int = 0) -> tuple[str, int]:
    """
    `|` 换行，`[xxx]` 强调。

    字号按最长那行的字数反推，保证塞得进可用宽度而不折行。
    `inset` 是该风格额外占掉的横向空间（note 的竖线、band 的色块 padding），
    不扣掉的话标题会意外折行。
    """
    lines = [ln.strip() for ln in title.split("|") if ln.strip()]
    if not lines:
        sys.exit("[错误] 标题是空的。")

    # 算字数时不含方括号本身。ASCII 字符按半宽算。
    def width_in_chars(s: str) -> float:
        s = re.sub(r"[\[\]]", "", s)
        return sum(0.55 if ord(c) < 0x2E80 else 1.0 for c in s)

    max_chars = max(width_in_chars(ln) for ln in lines)
    avail = USABLE - inset
    size = min(TITLE_SIZE_CAP, int(avail / max(max_chars, 1) * 0.96))

    out = []
    for ln in lines:
        # [xxx] → <em>xxx</em>
        parts, pos = [], 0
        for m in re.finditer(r"\[([^\]]+)\]", ln):
            parts.append(esc(ln[pos:m.start()]))
            parts.append(f"<em>{esc(m.group(1))}</em>")
            pos = m.end()
        parts.append(esc(ln[pos:]))
        inner = "".join(parts)
        out.append(f'<span class="line">{inner}</span>' if style == "band" else inner)

    sep = "<br>" if style != "band" else "<br>"
    return sep.join(out), size


def build_html(args, cfg: dict, html_out: Path) -> str:
    tpl = TEMPLATE.read_text(encoding="utf-8")
    t_html, auto_size = title_html(args.title, args.style, cfg.get("inset", 0))
    size = args.title_size or auto_size

    align = args.align
    items = {"left": "flex-start", "center": "center", "right": "flex-end"}[align]

    subs = ""
    if args.sub:
        sub_lines = "<br>".join(esc(x.strip()) for x in args.sub.split("|") if x.strip())
        subs = f'<div class="sub">{sub_lines}</div>'

    tag = f'<div class="tag">{esc(args.tag)}</div>' if args.tag else ""
    sig = f'<div class="sig">{esc(args.sig)}</div>' if args.sig else ""

    repl = {
        "__FG__": args.fg or cfg["fg"],
        "__BGCOLOR__": args.bgcolor or cfg["bgcolor"],
        "__ACCENT__": args.accent or cfg["accent"],
        "__TITLE_SIZE__": str(size),
        "__SUB_SIZE__": str(args.sub_size),
        "__BG_URL__": bg_css(Path(args.bg) if args.bg else None, html_out),
        "__SCRIM__": cfg["scrim"] if args.bg else "none",
        "__TITLE_SHADOW__": cfg["shadow"] if args.bg else "",
        "__JUSTIFY__": cfg["justify"],
        "__ITEMS__": items,
        "__ALIGN__": align,
        "__BAND_BG__": cfg["band_bg"],
        "__TAG_FG__": cfg["tag_fg"],
        "__STYLE__": args.style,
        "__TAG_HTML__": tag,
        "__TITLE_HTML__": t_html,
        "__SUB_HTML__": subs,
        "__SIG_HTML__": sig,
    }
    for k, v in repl.items():
        tpl = tpl.replace(k, v)
    return tpl


# ------------------------------------------------------------------ main
def main() -> int:
    ap = argparse.ArgumentParser(
        description="把小红书封面渲染成 1080×1440 PNG",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="标题里 `|` 是换行，`[xxx]` 是强调色。",
    )
    ap.add_argument("--title", help="主标题。`|` 换行，`[xxx]` 强调")
    ap.add_argument("--sub", help="副标题，可用 `|` 换行")
    ap.add_argument("--tag", help="左上/顶部的小标签，如「旅行」")
    ap.add_argument("--sig", help="底部署名，如「@vivian」")
    ap.add_argument("--bg", help="背景图（通常是 image_gen 出的 1024×1536）")
    ap.add_argument("--style", default="plain", choices=sorted(STYLES), help="默认 plain")
    ap.add_argument("--align", default="left", choices=["left", "center", "right"])
    ap.add_argument("--fg", help="文字色，覆盖风格默认")
    ap.add_argument("--bgcolor", help="背景色，覆盖风格默认")
    ap.add_argument("--accent", help="强调色，覆盖风格默认")
    ap.add_argument("--title-size", type=int, help="主标题字号，默认按字数自动算")
    ap.add_argument("--sub-size", type=int, default=40, help="副标题字号，默认 40")
    ap.add_argument("--out", default="cover.png", help="输出 PNG，默认 cover.png")
    ap.add_argument("--from-html", help="跳过模板，直接渲染这个 HTML")
    ap.add_argument("--keep-html", action="store_true", help="（默认就会保留 cover.html，此项兼容用）")
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
    print(f"✅ {out}  ({kb:.0f} KB)")
    if not args.from_html:
        print(f"   排版源文件：{html}  ← 想微调就改这个，然后：")
        print(f"   python {Path(__file__).name} --from-html {html} --out {out}")

    if size:
        print(f"   尺寸：{size[0]}×{size[1]}", end="")
        if size == (W, H):
            print("  ✅ 3:4，符合小红书封面规范")
        else:
            print(f"  ⚠️ 期望 {W}×{H}，请检查")
            return 1
    else:
        print("   ⚠️ 读不出 PNG 尺寸，文件可能有问题")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
