#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
语气统计器 —— 从历史笔记里量出可复现的写作特征。

为什么要这个：模型光「读几篇然后模仿」，产出的是它对「小红书博主」的刻板印象，
不是你。这个脚本先把能数的东西数出来（句长、标点频率、emoji 偏好、口头禅、
开头结尾套路），模型拿到的是数字而不是印象。

只用标准库。不联网。

用法：
    python voice_stats.py ../../../samples/*.md
    python voice_stats.py ../../../samples --json
    python voice_stats.py note1.md note2.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from statistics import median

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

CJK = r"一-鿿"

# 纯功能词组成的 n-gram 没有信息量，滤掉。
FUNCTION_CHARS = set("的了是在我你他她它就都也很有不这那一个我们你们和跟把被给去来"
                     "还又只没要会能对从到过着呢吧啊嘛呀哦么什怎为所以但而且然后")

# 标点分类统计
PUNCT_GROUPS = {
    "句号 。": "。",
    "逗号 ，": "，,",
    "感叹号 ！": "！!",
    "问号 ？": "？?",
    "顿号 、": "、",
    "省略号 …": "…",
    "波浪号 ～": "~～",
    "破折号 ——": "—",
    "冒号 ：": "：:",
    "引号「」“”": "「」“”\"",
    "括号（）": "（）()",
}

EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U0001F000-\U0001F2FF☀-➿⬀-⯿←-⇿]"
)


def strip_frontmatter(text: str) -> tuple[str, str]:
    """返回 (title, body)。"""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if not m:
        lines = text.splitlines()
        title = next((ln.strip().lstrip("#").strip() for ln in lines if ln.strip()), "")
        body = "\n".join(lines[1:]) if lines else ""
        return title, body
    head, body = m.group(1), m.group(2)
    title = ""
    for line in head.splitlines():
        if line.lower().startswith("title:"):
            title = line.partition(":")[2].strip().strip("\"'")
    return title, body


def clean_body(body: str) -> str:
    """去掉标签行和 markdown 噪音，只留她真正写的话。"""
    body = re.sub(r"#[^\s#]{1,20}", "", body)   # #标签
    body = re.sub(r"^\s*[-*>]\s*", "", body, flags=re.M)
    body = re.sub(r"\*\*|__|`", "", body)
    return body


def sentences(text: str) -> list[str]:
    parts = re.split(r"[。！？!?\n]+", text)
    return [p.strip() for p in parts if len(p.strip()) >= 2]


def cjk_len(text: str) -> int:
    return sum(1 for ch in text if not ch.isspace())


def ngrams(text: str, n: int) -> Counter:
    """CJK 字符 n-gram。不用分词库（不引第三方依赖），字符 n-gram 找口头禅够用。"""
    seq = re.sub(f"[^{CJK}]", "\n", text)
    c = Counter()
    for chunk in seq.split("\n"):
        for i in range(len(chunk) - n + 1):
            g = chunk[i : i + n]
            if all(ch in FUNCTION_CHARS for ch in g):
                continue
            c[g] += 1
    return c


def catchphrases(text: str, min_count: int = 3, top: int = 18) -> list[tuple[str, int]]:
    """
    找口头禅：取 2–5 字 n-gram，长的优先。
    若某短 gram 的出现次数与包含它的长 gram 相同，说明它只在那个长词里出现，丢掉。
    """
    pools = {n: ngrams(text, n) for n in (5, 4, 3, 2)}
    chosen: list[tuple[str, int]] = []
    covered: list[str] = []

    for n in (5, 4, 3, 2):
        for gram, cnt in pools[n].most_common(200):
            if cnt < min_count:
                continue
            # 已被更长的 gram 覆盖且次数相同 → 无独立信息
            if any(gram in longer and cnt <= dict(chosen).get(longer, 0) for longer in covered):
                continue
            chosen.append((gram, cnt))
            covered.append(gram)
            if len(chosen) >= top:
                return chosen
    return chosen


def analyse(files: list[Path]) -> dict:
    notes = []
    for p in files:
        raw = p.read_text(encoding="utf-8", errors="replace")
        title, body = strip_frontmatter(raw)
        body = clean_body(body)
        if cjk_len(body) < 20:
            continue
        notes.append({"file": p.name, "title": title, "body": body})

    if not notes:
        sys.exit("[错误] 没读到有效样本。samples/ 里放几篇你发过的笔记（.md 或 .txt）。")

    all_body = "\n".join(n["body"] for n in notes)
    all_titles = [n["title"] for n in notes if n["title"]]

    sent = sentences(all_body)
    sent_lens = [cjk_len(s) for s in sent]

    paras = [p.strip() for n in notes for p in n["body"].split("\n") if p.strip()]
    para_lens = [cjk_len(p) for p in paras]

    total = max(cjk_len(all_body), 1)

    punct = {}
    for label, chars in PUNCT_GROUPS.items():
        c = sum(all_body.count(ch) for ch in chars)
        punct[label] = {"count": c, "per_100": round(c / total * 100, 2)}

    emojis = EMOJI_RE.findall(all_body)

    # 开头：每篇第一段的前 12 字
    openers = [n["body"].strip().split("\n")[0][:12] for n in notes if n["body"].strip()]
    # 结尾：每篇最后一个句子
    closers = []
    for n in notes:
        ss = sentences(n["body"])
        if ss:
            closers.append(ss[-1][:24])

    first_person = len(re.findall(r"我(?!们)", all_body))
    we = len(re.findall(r"我们", all_body))
    you = len(re.findall(r"你(们)?", all_body))

    return {
        "样本": {
            "篇数": len(notes),
            "总字数": total,
            "每篇平均字数": round(total / len(notes)),
            "文件": [n["file"] for n in notes],
        },
        "句子": {
            "句数": len(sent),
            "平均句长": round(sum(sent_lens) / max(len(sent_lens), 1), 1),
            "中位句长": round(median(sent_lens), 1) if sent_lens else 0,
            "最短": min(sent_lens) if sent_lens else 0,
            "最长": max(sent_lens) if sent_lens else 0,
            "短句占比(≤10字)": f"{sum(1 for l in sent_lens if l <= 10) / max(len(sent_lens), 1):.0%}",
            "长句占比(≥30字)": f"{sum(1 for l in sent_lens if l >= 30) / max(len(sent_lens), 1):.0%}",
        },
        "段落": {
            "段数": len(paras),
            "平均段长": round(sum(para_lens) / max(len(para_lens), 1), 1),
            "每篇平均段数": round(len(paras) / len(notes), 1),
        },
        "标点": punct,
        "emoji": {
            "总数": len(emojis),
            "每百字": round(len(emojis) / total * 100, 2),
            "常用": Counter(emojis).most_common(12),
            "用不用": "几乎不用" if len(emojis) / total * 100 < 0.5 else "会用",
        },
        "人称": {
            "我": first_person,
            "我们": we,
            "你/你们": you,
            "倾向": "第一人称独白" if first_person > you * 2 else ("对话感强" if you > first_person else "混合"),
        },
        "口头禅候选": catchphrases(all_body),
        "开头前12字": openers[:15],
        "结尾句": closers[:15],
        "标题": {
            "数量": len(all_titles),
            "平均字数": round(sum(cjk_len(t) for t in all_titles) / max(len(all_titles), 1), 1),
            "样例": all_titles[:15],
        },
    }


def render(d: dict) -> str:
    L = ["=" * 64, "语气统计", "=" * 64, ""]

    s = d["样本"]
    L.append(f"样本：{s['篇数']} 篇，共 {s['总字数']} 字，平均每篇 {s['每篇平均字数']} 字")
    if s["篇数"] < 8:
        L.append(f"⚠ 只有 {s['篇数']} 篇。8 篇以下统计会不稳，建议再补一些。")
    L.append("")

    q = d["句子"]
    L.append(f"句子：{q['句数']} 句 ｜ 平均 {q['平均句长']} 字（中位 {q['中位句长']}）"
             f" ｜ 范围 {q['最短']}–{q['最长']}")
    L.append(f"      短句(≤10字) {q['短句占比(≤10字)']} ｜ 长句(≥30字) {q['长句占比(≥30字)']}")

    p = d["段落"]
    L.append(f"段落：每篇平均 {p['每篇平均段数']} 段，每段平均 {p['平均段长']} 字")
    L.append("")

    L.append("标点习惯（每百字）：")
    for label, v in sorted(d["标点"].items(), key=lambda kv: -kv[1]["per_100"]):
        if v["count"]:
            L.append(f"  {label:<12} {v['per_100']:>5}  （共 {v['count']}）")
    L.append("")

    e = d["emoji"]
    L.append(f"emoji：{e['用不用']}，每百字 {e['每百字']} 个（共 {e['总数']}）")
    if e["常用"]:
        L.append("  常用：" + "  ".join(f"{k}×{v}" for k, v in e["常用"]))
    L.append("")

    r = d["人称"]
    L.append(f"人称：我 {r['我']} ｜ 我们 {r['我们']} ｜ 你 {r['你/你们']}  →  {r['倾向']}")
    L.append("")

    L.append("口头禅候选（出现 ≥3 次）：")
    if d["口头禅候选"]:
        for gram, cnt in d["口头禅候选"]:
            L.append(f"  「{gram}」×{cnt}")
    else:
        L.append("  （样本太少，没找出重复模式）")
    L.append("")

    L.append("开头怎么起（每篇前 12 字）：")
    for o in d["开头前12字"]:
        L.append(f"  · {o}")
    L.append("")

    L.append("结尾怎么收：")
    for c in d["结尾句"]:
        L.append(f"  · {c}")
    L.append("")

    t = d["标题"]
    L.append(f"标题：平均 {t['平均字数']} 字")
    for x in t["样例"]:
        L.append(f"  · {x}")
    L.append("")
    L.append("-" * 64)
    L.append("这些是数字，不是结论。接下来由模型结合原文读出「她为什么这么写」，")
    L.append("写进 profile/voice.md。数字用来校验，不是用来堆砌。")
    L.append("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description="从历史笔记统计写作特征")
    ap.add_argument("paths", nargs="+", help="样本文件或目录")
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args()

    files: list[Path] = []
    for raw in args.paths:
        p = Path(raw)
        if p.is_dir():
            files += sorted(list(p.glob("*.md")) + list(p.glob("*.txt")))
        elif p.is_file():
            files.append(p)
    files = [f for f in files if f.name.lower() != "readme.md"]

    if not files:
        sys.exit("[错误] 没找到样本文件。")

    d = analyse(files)
    print(json.dumps(d, ensure_ascii=False, indent=2) if args.as_json else render(d))
    return 0


if __name__ == "__main__":
    sys.exit(main())
