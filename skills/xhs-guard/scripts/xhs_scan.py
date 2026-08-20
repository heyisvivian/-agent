#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小红书笔记合规扫描器 —— 确定性的那一层。

只用标准库，不联网，不上传任何内容。

它做什么：
  · 按分级词库扫出风险命中项（L1 硬红线 / L2 高风险 / L3 中风险 / L4 压流量）
  · 检查格式软指标（标题字数、正文长度、标签数量、emoji 密度、段落长度）
  · 给每条命中输出「为什么」和「怎么改」

它不做什么：
  · 不判断语境。「最好提前订票」和「最好用的防晒」它都会命中「最好」。
    语境判断交给模型（见 ../SKILL.md 的第 3 步），本脚本负责的是召回率。
  · 不帮你把违禁词伪装成检测不到的样子。改的是主张，不是拼写。

用法：
    python xhs_scan.py note.md
    python xhs_scan.py note.md --json
    python xhs_scan.py --text "全网最好吃的一家，私我拿地址"
    type note.md | python xhs_scan.py -

    --min-tier L3   只看 L1/L2/L3，忽略 L4
    --strict        把 L3 也算作拦截项（默认只有 L1/L2 拦截）

退出码：
    0 = 没有拦截项
    1 = 有拦截项（默认 L1/L2；--strict 时含 L3）
    2 = 参数或文件错误
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

# ---------------------------------------------------------------- Windows 控制台
# PowerShell / cmd 默认编码不是 UTF-8，中文和 emoji 会炸。强制切一下。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # 老版本 Python 或已被重定向
        pass

LEXICON_PATH = Path(__file__).with_name("lexicon.json")
TIER_ORDER = ["L1", "L2", "L3", "L4"]

# emoji 大致范围。不求精确，只用来估密度。
EMOJI_RANGES = (
    (0x1F300, 0x1FAFF),
    (0x1F000, 0x1F2FF),
    (0x2600, 0x27BF),
    (0x2B00, 0x2BFF),
    (0xFE0F, 0xFE0F),
    (0x2190, 0x21FF),
)


# ---------------------------------------------------------------- 载入词库
def load_lexicon(path: Path = LEXICON_PATH) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.exit(f"[错误] 找不到词库：{path}")
    except json.JSONDecodeError as exc:
        sys.exit(f"[错误] 词库不是合法 JSON：{exc}")

    # 预编译。有坏正则就报出来，不要静默跳过。
    for rule in data["rules"]:
        try:
            rule["_re"] = re.compile(rule["pattern"])
        except re.error as exc:
            sys.exit(f"[错误] 规则 {rule['id']} 的正则有问题：{exc}")
        # exclude：中文子串误报的解药。
        # 「平安神宫」里的「安神」、「治愈系」里的「治愈」都不该报。
        # 命中位置若落在任一 exclude 词的范围内，就丢掉这次命中。
        try:
            rule["_exclude"] = [re.compile(p) for p in rule.get("exclude", [])]
        except re.error as exc:
            sys.exit(f"[错误] 规则 {rule['id']} 的 exclude 正则有问题：{exc}")
    return data


def excluded(rule: dict, text: str, start: int, end: int) -> bool:
    """命中区间是否被包在某个豁免词里。"""
    for ex in rule["_exclude"]:
        for m in ex.finditer(text):
            if m.start() <= start and end <= m.end():
                return True
    return False


# ---------------------------------------------------------------- 解析笔记
def parse_note(raw: str) -> dict:
    """
    支持两种输入：

    1) 带 frontmatter 的 note.md（xhs-note 的标准产出）
       ---
       title: 京都下雨那天我什么也没干
       tags: [京都旅行, 雨天, 一个人旅行]
       ---
       正文……

    2) 纯文本 —— 第一行当标题，行内 #xxx 当标签
    """
    title, tags, body = "", [], raw

    fm = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", raw, re.S)
    if fm:
        head, body = fm.group(1), fm.group(2)
        for line in head.splitlines():
            if ":" not in line:
                continue
            key, _, val = line.partition(":")
            key, val = key.strip().lower(), val.strip()
            if key == "title":
                title = val.strip("\"'")
            elif key == "tags":
                val = val.strip("[]")
                tags = [t.strip().strip("\"'#") for t in re.split(r"[,，]", val) if t.strip()]
    else:
        lines = [ln for ln in raw.splitlines()]
        for ln in lines:
            if ln.strip():
                title = ln.strip().lstrip("#").strip()
                break

    # 正文里的 #标签（小红书的话题写法），合并进标签列表
    for m in re.finditer(r"#([^\s#\[\]]{1,20})", body):
        tag = m.group(1).strip("＃")
        if tag and tag not in tags:
            tags.append(tag)

    return {"title": title, "tags": tags, "body": body, "raw": raw}


# ---------------------------------------------------------------- 工具
def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def snippet(text: str, start: int, end: int, pad: int = 14) -> str:
    left = max(0, start - pad)
    right = min(len(text), end + pad)
    out = text[left:start] + "【" + text[start:end] + "】" + text[end:right]
    return out.replace("\n", "⏎")


def is_emoji(ch: str) -> bool:
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in EMOJI_RANGES)


def count_emoji(text: str) -> int:
    return sum(1 for ch in text if is_emoji(ch))


def visible_len(text: str) -> int:
    """字数：按小红书的直觉数 —— 中文/emoji 算 1，忽略空白和换行。"""
    return sum(1 for ch in text if not ch.isspace() and unicodedata.category(ch) != "Cf")


# ---------------------------------------------------------------- 扫描
def scan_text(note: dict, lex: dict, min_tier: str = "L4") -> list[dict]:
    cutoff = TIER_ORDER.index(min_tier)
    # 标题 + 正文 + 标签一起扫。标题和标签也是审核范围。
    target = note["raw"]
    hits, seen = [], set()

    for rule in lex["rules"]:
        if TIER_ORDER.index(rule["tier"]) > cutoff:
            continue
        for m in rule["_re"].finditer(target):
            matched = m.group(0)
            if excluded(rule, target, m.start(), m.end()):
                continue
            key = (rule["id"], matched)
            if key in seen:  # 同一规则同一词只报一次，避免刷屏
                continue
            seen.add(key)
            hits.append(
                {
                    "rule": rule["id"],
                    "tier": rule["tier"],
                    "category": rule["category"],
                    "matched": matched,
                    "line": line_of(target, m.start()),
                    "snippet": snippet(target, m.start(), m.end()),
                    "why": rule["why"],
                    "fix": rule["fix"],
                    "context": rule.get("context", ""),
                }
            )

    hits.sort(key=lambda h: (TIER_ORDER.index(h["tier"]), h["line"]))
    return hits


def check_format(note: dict, lex: dict, note_type: str = "life") -> list[dict]:
    s = lex["soft_signals"]
    out = []
    # 正文长度的舒适区跟内容类型有关：科普/清单型天然比生活片段长
    body_lo, body_hi = s.get("body_sweet_spot_by_type", {}).get(
        note_type, s["body_sweet_spot"]
    )

    def add(level, item, actual, want, advice):
        out.append({"level": level, "item": item, "actual": actual, "want": want, "advice": advice})

    # 标题
    tl = visible_len(note["title"])
    if tl == 0:
        add("warn", "标题", "空", f"{s['title_sweet_spot'][0]}–{s['title_sweet_spot'][1]} 字", "没有标题，笔记基本不会被推。")
    elif tl > s["title_max_chars"]:
        add("bad", "标题字数", f"{tl} 字", f"≤ {s['title_max_chars']} 字",
            f"超出 {tl - s['title_max_chars']} 字，会被截断。前 {s['title_max_chars']} 字要能独立成句。")
    elif not (s["title_sweet_spot"][0] <= tl <= s["title_sweet_spot"][1]):
        add("warn", "标题字数", f"{tl} 字", f"{s['title_sweet_spot'][0]}–{s['title_sweet_spot'][1]} 字",
            "偏短的标题信息量不够，偏长的在封面上不好排。")
    else:
        add("ok", "标题字数", f"{tl} 字", "—", "")

    # 正文
    bl = visible_len(note["body"])
    if bl > s["body_max_chars"]:
        add("bad", "正文字数", f"{bl} 字", f"≤ {s['body_max_chars']} 字",
            f"超 {bl - s['body_max_chars']} 字，发不出去，需要删减。")
    elif not (body_lo <= bl <= body_hi):
        add("warn", "正文字数", f"{bl} 字", f"{body_lo}–{body_hi} 字（{note_type} 型）",
            "这个区间的完读率通常最好。类型不对就换 --type（life / guide / short）。")
    else:
        add("ok", "正文字数", f"{bl} 字（{note_type} 型）", "—", "")

    # 标签
    tn = len(note["tags"])
    lo, hi = s["tags_recommended"]
    if tn == 0:
        add("bad", "标签", "0 个", f"{lo}–{hi} 个", "没标签等于放弃搜索流量，而搜索占小红书流量的大头。")
    elif tn > s["tags_hard_warn"]:
        add("bad", "标签数量", f"{tn} 个", f"{lo}–{hi} 个", "堆标签会被判蹭流量，反而压推荐。")
    elif not (lo <= tn <= hi):
        add("warn", "标签数量", f"{tn} 个", f"{lo}–{hi} 个", "宁少勿凑。每个标签都要跟内容真的相关。")
    else:
        add("ok", "标签数量", f"{tn} 个", "—", "")

    # emoji 密度（只算正文，frontmatter 不算）
    total = max(visible_len(note["body"]), 1)
    per100 = count_emoji(note["body"]) / total * 100
    if per100 > s["emoji_density_warn_per_100"]:
        add("warn", "emoji 密度", f"每百字 {per100:.1f} 个", f"≤ {s['emoji_density_warn_per_100']} 个",
            "emoji 太密会显得像模板号。留给真正需要停顿的地方。")
    else:
        add("ok", "emoji 密度", f"每百字 {per100:.1f} 个", "—", "")

    # emoji 连排 —— 比密度更能说明问题：😍😍😍 是模板号的标志
    runs = []
    for i, ch in enumerate(note["body"]):
        if not is_emoji(ch):
            continue
        run = 1
        while i + run < len(note["body"]) and note["body"][i + run] == ch:
            run += 1
        if run >= 3 and (i == 0 or note["body"][i - 1] != ch):
            runs.append(f"{ch}×{run}")
    if runs:
        add("warn", "emoji 连排", "、".join(runs[:6]), "同一个最多 2 连",
            "同一个 emoji 连打三个以上是模板号最明显的特征之一。删到 1–2 个，情绪不会少。")
    else:
        add("ok", "emoji 连排", "无", "—", "")

    # 段落长度
    long_lines = [
        (i, visible_len(ln)) for i, ln in enumerate(note["body"].splitlines(), 1)
        if visible_len(ln) > s["line_len_warn"]
    ]
    if long_lines:
        where = "、".join(f"第{i}行({n}字)" for i, n in long_lines[:5])
        add("warn", "段落长度", f"{len(long_lines)} 段偏长", f"每段 ≤ {s['line_len_warn']} 字",
            f"{where}。手机上是窄屏，长段落会被划走。")
    else:
        add("ok", "段落长度", "都不长", "—", "")

    return out


# ---------------------------------------------------------------- 输出
def render(note: dict, hits: list[dict], fmt: list[dict], lex: dict, strict: bool) -> tuple[str, bool]:
    tiers = lex["tiers"]
    gate_tiers = {t for t, v in tiers.items() if v["gate"]}
    if strict:
        gate_tiers.add("L3")
    blocked = any(h["tier"] in gate_tiers for h in hits)

    L = []
    L.append("=" * 68)
    L.append("小红书发布前合规扫描")
    L.append(f"词库版本 {lex['version']}（更新于 {lex['updated']}）")
    L.append("=" * 68)

    counts = {t: sum(1 for h in hits if h["tier"] == t) for t in TIER_ORDER}
    summary = "  ".join(f"{tiers[t]['mark']} {tiers[t]['label']} {counts[t]}" for t in TIER_ORDER)
    L.append(f"\n命中统计：{summary}")
    L.append(f"结论：{'❌ 不建议直接发布，先处理拦截项' if blocked else '✅ 无拦截项'}")

    # 风险命中
    if hits:
        for tier in TIER_ORDER:
            group = [h for h in hits if h["tier"] == tier]
            if not group:
                continue
            info = tiers[tier]
            L.append("")
            L.append("-" * 68)
            L.append(f"{info['mark']} {tier} {info['label']} —— {info['action']}")
            L.append("-" * 68)
            for h in group:
                L.append(f"\n  ▸ 「{h['matched']}」  第 {h['line']} 行 · {h['category']} · [{h['rule']}]")
                L.append(f"    上下文：{h['snippet']}")
                L.append(f"    为什么：{h['why']}")
                L.append(f"    怎么改：{h['fix']}")
                if h["context"]:
                    L.append(f"    ⚠ 语境：{h['context']}")
    else:
        L.append("\n没有命中任何风险词。")

    # 格式
    L.append("")
    L.append("-" * 68)
    L.append("格式与体感检查")
    L.append("-" * 68)
    icon = {"ok": "✅", "warn": "🟡", "bad": "🔴"}
    for f in fmt:
        line = f"  {icon[f['level']]} {f['item']}：{f['actual']}"
        if f["level"] != "ok":
            line += f"（建议 {f['want']}）"
        L.append(line)
        if f["advice"]:
            L.append(f"      → {f['advice']}")

    if note["tags"]:
        L.append(f"\n  当前标签：{' '.join('#' + t for t in note['tags'])}")

    L.append("")
    L.append("-" * 68)
    L.append("必须人工确认（脚本查不了的）")
    L.append("-" * 68)
    L.append("  □ 图片/视频里有没有其他平台水印、他人正脸、车牌、证件、门牌号")
    L.append("  □ 正文主要由 AI 起草 → 发布页勾选【内容类型声明·笔记含 AI 合成内容】")
    L.append("  □ 有任何对价（钱 / 免费 / 置换 / 返现）→ 必须走蒲公英报备")
    L.append("  □ 价格、营业时间、签证政策这类会过期的信息，是不是刚核实过")
    L.append("  □ 标签一次选对 —— 有流量后再改容易限流")
    L.append("")
    L.append(lex["disclaimer"])
    L.append("")

    return "\n".join(L), blocked


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(
        description="小红书笔记合规扫描器", formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("files", nargs="*", help="要扫的文件；用 - 表示从 stdin 读")
    ap.add_argument("--text", help="直接扫一段文字")
    ap.add_argument("--json", action="store_true", dest="as_json", help="输出 JSON，给程序用")
    ap.add_argument("--min-tier", default="L4", choices=TIER_ORDER, help="最低报告等级，默认 L4（全部）")
    ap.add_argument("--strict", action="store_true", help="把 L3 也算拦截项")
    ap.add_argument("--type", default="life", dest="note_type",
                    choices=["life", "guide", "short"],
                    help="内容类型，只影响正文长度的舒适区判断："
                         "life 生活片段 300–600 字（默认）、"
                         "guide 科普/攻略/清单 400–950 字、"
                         "short 一句话笔记 80–300 字")
    args = ap.parse_args()

    if not args.files and not args.text:
        ap.print_help()
        return 2

    lex = load_lexicon()
    inputs: list[tuple[str, str]] = []

    if args.text:
        inputs.append(("<--text>", args.text))
    for f in args.files:
        if f == "-":
            inputs.append(("<stdin>", sys.stdin.read()))
        else:
            p = Path(f)
            if not p.is_file():
                print(f"[错误] 文件不存在：{f}", file=sys.stderr)
                return 2
            inputs.append((str(p), p.read_text(encoding="utf-8", errors="replace")))

    any_blocked, payload = False, []

    for name, raw in inputs:
        note = parse_note(raw)
        hits = scan_text(note, lex, args.min_tier)
        fmt = check_format(note, lex, args.note_type)
        text, blocked = render(note, hits, fmt, lex, args.strict)
        any_blocked = any_blocked or blocked

        if args.as_json:
            payload.append(
                {
                    "source": name,
                    "title": note["title"],
                    "tags": note["tags"],
                    "blocked": blocked,
                    "hits": hits,
                    "format": fmt,
                }
            )
        else:
            if len(inputs) > 1:
                print(f"\n########## {name} ##########")
            print(text)

    if args.as_json:
        print(json.dumps({"lexicon_version": lex["version"], "results": payload},
                         ensure_ascii=False, indent=2))

    return 1 if any_blocked else 0


if __name__ == "__main__":
    sys.exit(main())
