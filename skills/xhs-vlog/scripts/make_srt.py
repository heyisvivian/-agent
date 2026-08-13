#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
口播稿 → .srt 字幕。

剪映、Premiere、DaVinci 都能直接导入 .srt，导进去就是排好的字幕轨，
比在剪映里一句一句敲快得多。

两种模式：

1) 自动配时（默认）—— 按中文语速估算每句时长
   输入：一行一句话
       老板娘端来焙茶的时候
       说这种天最好不要出门
       我就真的没出门

2) 手动配时 —— 行首写时间码，脚本照用
   输入：
       00:00 老板娘端来焙茶的时候
       00:04 说这种天最好不要出门
   或者写完整区间：
       00:07.5-00:11 我就真的没出门

只用标准库。不联网。

用法：
    python make_srt.py narration.txt -o subtitle.srt
    python make_srt.py narration.txt -o subtitle.srt --cps 5.0 --max-chars 14
    python make_srt.py script.md -o subtitle.srt --section 口播
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# 行首时间码：00:00 / 1:02 / 00:04.5 / 00:00:04,500
TC = r"(?:\d{1,2}:)?\d{1,2}:\d{1,2}(?:[.,]\d{1,3})?"
RE_RANGE = re.compile(rf"^\s*({TC})\s*[-–~]\s*({TC})\s+(.+)$")
RE_START = re.compile(rf"^\s*({TC})\s+(.+)$")

# CJK 起始码位。低于这个的按半宽算（ASCII、数字、标点）
CJK_START = 0x2E80


def parse_tc(s: str) -> float:
    """时间码 → 秒。支持 mm:ss / hh:mm:ss，小数点或逗号做毫秒分隔。"""
    s = s.strip().replace(",", ".")
    parts = s.split(":")
    if len(parts) == 2:
        h, m, sec = "0", parts[0], parts[1]
    elif len(parts) == 3:
        h, m, sec = parts
    else:
        raise ValueError(f"看不懂的时间码：{s}")
    return int(h) * 3600 + int(m) * 60 + float(sec)


def fmt_tc(t: float) -> str:
    """秒 → SRT 的 HH:MM:SS,mmm"""
    t = max(t, 0.0)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def display_width(text: str) -> float:
    """中文按 1，ASCII 按 0.5。用来判断一行会不会太长。"""
    return sum(0.5 if ord(c) < CJK_START else 1.0 for c in text)


def split_line(text: str, max_chars: float) -> list[str]:
    """
    太长的句子切开。优先在标点处断，其次在空格处，最后才硬切。
    竖屏视频一行超过 14–16 个字就压不下了。
    """
    if display_width(text) <= max_chars:
        return [text]

    chunks = [c for c in re.split(r"(?<=[，。！？、；：,.!?])", text) if c.strip()]
    if len(chunks) <= 1:
        chunks = [c for c in re.split(r"(?<=\s)", text) if c.strip()]

    merged: list[str] = []
    buf = ""
    for ch in chunks:
        if buf and display_width(buf + ch) > max_chars:
            merged.append(buf.strip())
            buf = ch
        else:
            buf += ch
    if buf.strip():
        merged.append(buf.strip())

    # 还有超长的（整句没标点），按宽度硬切
    final: list[str] = []
    for seg in merged:
        while display_width(seg) > max_chars:
            cut, w = 0, 0.0
            for i, c in enumerate(seg):
                w += 0.5 if ord(c) < CJK_START else 1.0
                if w > max_chars:
                    break
                cut = i + 1
            cut = max(cut, 1)
            final.append(seg[:cut])
            seg = seg[cut:]
        if seg:
            final.append(seg)
    return final or [text]


def extract_lines(raw: str, section: str | None) -> list[str]:
    """从输入里挑出口播行。可以只取某个 markdown 小节。"""
    lines = raw.splitlines()

    if section:
        picked: list[str] = []
        inside, level = False, 0
        for ln in lines:
            m = re.match(r"^(#{1,6})\s*(.+)$", ln)
            if m:
                if section in m.group(2):
                    inside, level = True, len(m.group(1))
                    continue
                if inside and len(m.group(1)) <= level:
                    break
                continue
            if inside:
                picked.append(ln)
        if not picked:
            sys.exit(f"[错误] 找不到叫「{section}」的小节。")
        lines = picked

    out: list[str] = []
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if s.startswith(("#", "|", "---", "```", "<!--")):   # markdown 噪音
            continue
        s = re.sub(r"^[-*>]\s*", "", s)                       # 列表/引用符号
        s = re.sub(r"^\d+[.、)]\s*", "", s)                   # 行首序号
        s = re.sub(r"\*\*|__|`", "", s)                       # 强调符号
        s = s.strip()
        if s:
            out.append(s)
    return out


def build_cues(lines: list[str], cps: float, min_d: float, max_d: float,
               gap: float, max_chars: float, offset: float) -> list[tuple[float, float, str]]:
    """
    中间表示是 (start, end, pieces)，pieces 是这句断开后的若干行。
    end 为 None 表示「只给了起点」，收尾时间用下一条的起点补。
    """
    staged: list[tuple[float, float | None, list[str]]] = []
    cursor = offset

    for raw in lines:
        m = RE_RANGE.match(raw)          # 00:00-00:04 文字
        if m:
            start, end = parse_tc(m.group(1)), parse_tc(m.group(2))
            staged.append((start, end, split_line(m.group(3).strip(), max_chars)))
            cursor = end
            continue

        m = RE_START.match(raw)          # 00:00 文字
        if m:
            start = parse_tc(m.group(1))
            staged.append((start, None, split_line(m.group(2).strip(), max_chars)))
            cursor = start
            continue

        # 自动配时：每片独立算时长，依次排下去
        for piece in split_line(raw, max_chars):
            dur = min(max(display_width(piece) / cps, min_d), max_d)
            staged.append((cursor, cursor + dur, [piece]))
            cursor += dur + gap

    # 补齐 end=None 的条目
    resolved: list[tuple[float, float, list[str]]] = []
    for i, (start, end, pieces) in enumerate(staged):
        if end is None:
            nxt = next((staged[j][0] for j in range(i + 1, len(staged))
                        if staged[j][0] > start), None)
            if nxt is not None:
                end = nxt - gap
            else:
                span = sum(display_width(p) for p in pieces) / cps
                end = start + min(max(span, min_d), max_d)
        resolved.append((start, end, pieces))

    # 一句被断成多行时，按字数比例分摊这段时长
    out: list[tuple[float, float, str]] = []
    for start, end, pieces in resolved:
        if len(pieces) == 1:
            out.append((start, end, pieces[0]))
            continue
        total = sum(display_width(p) for p in pieces) or 1.0
        t = start
        for p in pieces:
            d = (end - start) * display_width(p) / total
            out.append((t, t + d, p))
            t += d
    return out


def to_srt(cues: list[tuple[float, float, str]]) -> str:
    blocks = []
    for i, (start, end, text) in enumerate(cues, 1):
        if end <= start:
            end = start + 0.8
        blocks.append(f"{i}\n{fmt_tc(start)} --> {fmt_tc(end)}\n{text}\n")
    return "\n".join(blocks)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="口播稿 → .srt 字幕",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("input", help="口播稿文件（一行一句；行首可写时间码）")
    ap.add_argument("-o", "--out", help="输出 .srt，默认与输入同名")
    ap.add_argument("--section", help="只取 markdown 里这个小节，如「口播」")
    ap.add_argument("--cps", type=float, default=5.5,
                    help="每秒几个字，默认 5.5（中文 vlog 常速；语速慢就调到 4.5）")
    ap.add_argument("--min", dest="min_d", type=float, default=1.2, help="单条最短秒数，默认 1.2")
    ap.add_argument("--max", dest="max_d", type=float, default=6.0, help="单条最长秒数，默认 6.0")
    ap.add_argument("--gap", type=float, default=0.08, help="条间间隔秒数，默认 0.08")
    ap.add_argument("--max-chars", type=float, default=16,
                    help="单行最多几个字，超了自动断句，默认 16（竖屏建议 12–16）")
    ap.add_argument("--offset", type=float, default=0.0, help="整体延后几秒，默认 0")
    args = ap.parse_args()

    src = Path(args.input)
    if not src.is_file():
        sys.exit(f"[错误] 找不到文件：{src}")

    lines = extract_lines(src.read_text(encoding="utf-8", errors="replace"), args.section)
    if not lines:
        sys.exit("[错误] 没读到口播内容。")

    cues = build_cues(lines, args.cps, args.min_d, args.max_d,
                      args.gap, args.max_chars, args.offset)

    out = Path(args.out) if args.out else src.with_suffix(".srt")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(to_srt(cues), encoding="utf-8")

    total = cues[-1][1] if cues else 0.0
    longest = max((display_width(c[2]) for c in cues), default=0)
    print(f"✅ {out}")
    print(f"   {len(cues)} 条字幕 ｜ 总时长 {int(total // 60)}:{total % 60:04.1f}"
          f" ｜ 最长一行 {longest:.0f} 字")
    print(f"   语速按 {args.cps} 字/秒估的，配音后对不上就调 --cps 重跑")
    print("   剪映：导入 → 字幕 → 本地字幕，选这个 .srt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
