#!/usr/bin/env python3
"""xhs_scan.py 的回归断言。

为什么需要这个文件
──────────────────
`lexicon.json` 是 README 明确让用户**定期手改**的文件：

  被限流但扫描器没报 → 把原因补成新规则
  误报              → 加到对应规则的 exclude 数组

每次手改都可能撞坏已有的豁免（真违规漏过去）或者放走已有的拦截（误报回归）。
这里把两组东西钉住：**必须放行的**和**必须拦下的**。

跑法
────
    python skills/xhs-guard/scripts/test_xhs_scan.py

只用标准库（AGENTS.md §6），不联网。走 CLI 的 --json 接口，
所以它测的是使用者真正依赖的那个契约，不是内部函数。
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCAN = Path(__file__).with_name("xhs_scan.py")

# ── 必须放行 ──────────────────────────────────────────────────────
# 每一条都是真实误报，改词库时不许让它们回来。
# 括号里是它当初误报成的规则。
CLEAR = [
    # 序号 / 量词，不是排名宣称（abs-number-one）
    # 原规则用前向否定排除，量词有几十个，漏过 步/年/个/行/页…
    *[(f"这是第一{q}的内容", "abs-number-one") for q in
      "行 页 段 句 张 篇 部 集 课 章 版 步 遍 轮 批 波 层 条 届 季 顿 口 面 个 位 年 周 月".split()],
    ("第一次去京都我做了很详细的攻略", "abs-number-one"),
    ("🧱 第一步：先确认你手里有税号", "abs-number-one"),
    ("如果你是第一年报税，系统可能还没自动识别", "abs-number-one"),
    ("她是我们公司第二个讲英语的人，我是第一个", "abs-number-one"),
    # 「唯一」+ 缺点是在讲不足，不是「唯一的选择」那种宣称
    ("唯一不好一点，是这个地方经常维修", "abs-number-one"),
    ("唯一的缺点是有点贵", "abs-number-one"),
    ("唯一的问题是人太多", "abs-number-one"),
    # 自己的证件不是他人隐私（privacy-others）。护照号/机票照片 仍然要拦，见 BLOCK。
    ("等待拿护照啦！", "privacy-others"),
    ("并且我的护照也更新过之后", "privacy-others"),
    ("换护照之后要重新填", "privacy-others"),
    # 「N 天 + 白/瘦/见效」最容易撞序号和日常表达（efficacy-quantified）。
    # exclude 治不了这类 —— 命中区间跨出豁免词边界，靠模式里的 (?<!第) 和 白(?!天)。
    ("第一天白天出发", "efficacy-quantified"),
    ("这两天白天很热", "efficacy-quantified"),
    ("第十四天到达", "efficacy-quantified"),
    ("第三天下雨", "efficacy-quantified"),
    ("一天到晚在赶 ddl", "efficacy-quantified"),
    # 中文子串误报，README 点名的四个（改词库最容易撞坏这几条）
    ("平安神宫人不多，雨停了一会儿", None),
    ("这家店治愈系装修", None),
    ("记得装个避雷针", None),
    ("用了特效镜头", None),
]

# ── 必须拦下 ──────────────────────────────────────────────────────
# 豁免加宽了就会从这里漏出去。rule=None 表示只要求 blocked。
BLOCK = [
    ("我们拿了第一名", "abs-number-one"),
    ("行业第一品牌", "abs-number-one"),
    ("稳居第一梯队", "abs-number-one"),
    ("全网第一的性价比", "abs-number-one"),
    ("全国最好用的防晒", "abs-number-one"),
    ("世界第一的味道", "abs-number-one"),
    ("销量 NO.1", "abs-number-one"),
    ("口碑 TOP 1", "abs-number-one"),
    ("独一无二的体验", "abs-number-one"),
    ("这是你唯一的选择", "abs-number-one"),
    ("唯一推荐这一家", "abs-number-one"),
    ("护照号发我一下", "privacy-others"),
    ("身份证正反面拍给我", "privacy-others"),
    ("车牌都能看清", "privacy-others"),
    ("全网最好吃的一家，私我拿地址", "abs-zui-superlative"),
    # 功效宣称 · 量化。中文数字必须和阿拉伯数字同等对待 ——
    # 把「7天」写成「七天」是变体规避（铁律 1.1），扫描器不能对它瞎。
    ("7天变白", "efficacy-quantified"),
    ("七天变白", "efficacy-quantified"),
    ("3天见效", "efficacy-quantified"),
    ("三天见效", "efficacy-quantified"),
    ("持妆12小时", "efficacy-quantified"),
    ("持妆十二小时", "efficacy-quantified"),
    ("十天瘦", "efficacy-quantified"),
    ("十一天白", "efficacy-quantified"),
    ("祛痘特效", "efficacy-strong"),
    ("包治百病", "efficacy-medical"),
]


def scan(*args: str) -> dict:
    r = subprocess.run([sys.executable, str(SCAN), *args, "--json"],
                       capture_output=True, text=True)
    if not r.stdout.strip():
        raise SystemExit(f"[错误] 扫描器没有输出。\nargs={args}\nstderr={r.stderr}")
    return json.loads(r.stdout)["results"][0]


def fmt_item(res: dict, name: str) -> dict | None:
    return next((f for f in res["format"] if f["item"] == name), None)


def main() -> int:
    ok = bad = 0

    def check(cond: bool, label: str, detail: str = "") -> None:
        nonlocal ok, bad
        if cond:
            ok += 1
        else:
            bad += 1
            print(f"  ❌ {label}")
            if detail:
                print(f"     {detail}")

    print("必须放行")
    for text, rule in CLEAR:
        hits = scan("--text", text)["hits"]
        got = [h for h in hits if rule is None or h["rule"] == rule]
        check(not got, f"{text[:34]}",
              "误报：" + "、".join(f"{h['matched']}[{h['rule']}]" for h in got))

    print("必须拦下")
    for text, rule in BLOCK:
        res = scan("--text", text)
        if rule:
            check(any(h["rule"] == rule for h in res["hits"]), f"{text[:34]}",
                  f"没命中 {rule}，实际：" +
                  ("、".join(h["rule"] for h in res["hits"]) or "零命中"))
        else:
            check(res["blocked"], f"{text[:34]}", "没有被拦截")

    print("frontmatter：只扫会发布的部分")
    with tempfile.TemporaryDirectory() as d:
        # 非发布键（备注/互动/线）里的违规词不该报
        p = Path(d, "meta.md")
        p.write_text("---\ntitle: 测试笔记\n备注: 这篇是工具属性最强的一篇\n"
                     "互动: 全网第一\n---\n今天天气不错。\n", encoding="utf-8")
        res = scan(str(p))
        check(not res["hits"], "备注/互动里的违规词不报",
              "、".join(f"{h['matched']}[{h['rule']}]" for h in res["hits"]))

        # 但 title 和 tags 会发布，必须扫
        p2 = Path(d, "title.md")
        p2.write_text("---\ntitle: 全网最好吃的一家\ntags: [美食]\n备注: 无\n---\n"
                      "正文很正常。\n", encoding="utf-8")
        check(scan(str(p2))["blocked"], "title 里的违规词要报")

        # 行号必须还对得上原文（非发布行是清空不是删除）
        p3 = Path(d, "line.md")
        p3.write_text("---\ntitle: 测试\n备注: 无\n---\n第一行正文\n"
                      "第二行有个最好吃的东西\n", encoding="utf-8")
        hits = scan(str(p3))["hits"]
        h = next((x for x in hits if x["matched"] == "最好吃"), None)
        check(h is not None and h["line"] == 6, "行号对得上原文（应为第 6 行）",
              f"实际 line={h['line'] if h else '未命中'}")

    print("emoji：评分刻度 vs 堆砌")
    with tempfile.TemporaryDirectory() as d:
        # 同一 emoji 多行、数量不同 = 评分刻度，放行
        p = Path(d, "scale.md")
        p.write_text("游泳馆测评\nA 池 💣💣💣\nB 池 💣\nC 池 🌟🌟\nD 池 🌟🌟🌟🌟\n",
                     encoding="utf-8")
        f = fmt_item(scan(str(p)), "emoji 连排")
        check(f is not None and f["level"] == "ok", "💣/🌟 刻度按 ok 放行",
              f"实际 level={f['level'] if f else '缺失'}")

        # 数量全一样 = 堆砌，仍要警告
        p2 = Path(d, "spam.md")
        p2.write_text("第一家😍😍😍\n第二家😍😍😍\n", encoding="utf-8")
        f2 = fmt_item(scan(str(p2)), "emoji 连排")
        check(f2 is not None and f2["level"] == "warn", "同数量连排仍然警告",
              f"实际 level={f2['level'] if f2 else '缺失'}")

    print("词库自身")
    lex = json.loads(Path(SCAN).with_name("lexicon.json").read_text(encoding="utf-8"))
    check(bool(lex.get("version")) and bool(lex.get("updated")),
          "version / updated 都在")
    ids = [r["id"] for r in lex["rules"]]
    check(len(ids) == len(set(ids)), "规则 id 无重复",
          "重复：" + "、".join({i for i in ids if ids.count(i) > 1}))

    print(f"\n{'═' * 46}\n{ok} 通过 / {bad} 失败\n{'═' * 46}")
    if bad:
        print("改了 lexicon.json 之后失败 = 豁免加宽了（漏拦）或者规则收紧了（误报回归）。\n"
              "两种都不该带上线。")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
