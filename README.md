# xhs-agent · 小红书创作技能包

给 **Codex CLI** 用的小红书创作助手（同时兼容 Claude Code）。
**先根据你的真实数据定方向和选题**，再写文案、出 3:4 封面、写视频脚本和字幕，
**并且在发布前把违规词和限流风险扫一遍**。

赛道侧重：**法国生活实操 · 异国恋 · AI · 好物**

---

## 它做五件事

| | 做什么 | 技能 |
|---|---|---|
| **定方向** ★ | 从你的互动数据判断哪条线加码、哪条减、下一步发什么 | `xhs-strategy` |
| **写** | 从一个想法产出完整笔记 | `xhs-note` |
| **改** | 把你写好的稿子改得更好读 | `xhs-polish` |
| **拍** | 视频脚本、分镜、口播稿、`.srt` 字幕 | `xhs-script` `xhs-vlog` |
| **过审** | 违禁词、限流风险、平台红线，发布前全扫一遍 | `xhs-guard` |

配套一个：`xhs-voice`（语气护栏 —— 防 AI 通稿腔）。

**不做封面，不出图。** 封面你自己做 —— 本仓库只负责提醒字数规范，以及**扫封面上的文字**（封面文字一样会被审核）。

### 重心不是模仿笔锋

大部分「AI 写小红书」的工具在做的事是模仿语气。这个仓库 v0.2 起**不这么定位**：

> 「不用太细讲究我的笔锋 我也不是文字博主」—— 用户 2026-08-20

选题选对了，同样的文笔差十倍。所以第一优先是 `xhs-strategy`（发什么），
语气只留一层护栏：**别写成 AI 通稿，别删掉观众认得的记忆点。**

---

## 装

### Codex CLI

```bash
git clone https://github.com/heyisvivian/-agent.git xhs-agent
cd xhs-agent
```

Windows：

```powershell
.\install.ps1
```

macOS / Linux：

```bash
./install.sh
```

装完技能会出现在 `~/.codex/skills/` 和 `~/.agents/skills/`，
默认是**目录联接/符号链接**指向这个仓库 —— 以后 `git pull` 技能自动更新，不用重装。

想用复制而不是链接：`.\install.ps1 -Mode copy` / `./install.sh --copy`
卸载：`.\install.ps1 -Uninstall` / `./install.sh --uninstall`

装完 install 脚本会自检 Python 和 Codex，并跑一次冒烟测试。

### Claude Code

这个仓库同时是一个标准 plugin（`.claude-plugin/plugin.json` + `skills/`）。
在 Claude Code 里把仓库目录添加为本地 plugin 就能用。

### 依赖

| 需要 | 用来 | 备注 |
|---|---|---|
| **Python 3.9+** | 合规扫描、语气统计、字幕生成 | 只用标准库，不装任何包 |
| Codex CLI | 可选 | 不需要任何图像生成 API key |

---

## 快速开始

```bash
# 1. 把你发过的笔记放进 samples/，按类型分子目录：
#      samples/guide/   科普 / 信息型
#      samples/life/    生活 / 日常 / vlog / 旅行
#    每种 8 篇以上比较准。见 samples/README.md

# 2. 开 codex，让它学你的语气
```
> 学一下我的语气

会生成 `profile/voice.md`。**这一步做过一次就行**，之后所有写/改都基于它。

⚠️ **档案是分模式的。** 同一个人写科普和写生活不是同一套写法 ——
科普稿里 emoji 当项目符号是对的，生活稿里同样密度就成模板号了。
所以要分开放样本、分开统计、分开建档，写之前先定模式。

```
# 3. 然后就可以直接说话了
```
> 帮我写篇笔记：京都下雨那天我什么也没干，在民宿窗边坐了一下午
>
> 这个文案帮我改改：<贴上你的稿子>
>
> 做个封面，标题用「京都下雨那天 我什么都没干」
>
> 审一下这个文案能不能发
>
> 帮我写个 vlog 脚本，60 秒左右

---

## 合规这块的立场

网上大量「违禁词替换」教程教的是把 `最好` 写成 `zui好`、`绝对` 写成 `jue对`、
中间插空格或 emoji。**这个仓库不这么干**，三个原因：

1. 平台对变体词、谐音、拼音、形近字的识别早就上线了，绕不过去；
2. 「刻意规避审核」是独立的违规项，罚得比原违规更重；
3. 《社区公约 2.0》的核心是「真诚分享」，规避检测与之直接冲突。

正确的做法是**换掉那个站不住的主张**：

| ❌ 违规 | ❌ 伪装（更糟） | ✅ 正确 |
|---|---|---|
| 最好吃的一家 | zui好吃的一家 | 我今年去了三次的一家 |
| 100% 出片 | 100%出片✨ | 我拍了 40 张，有 6 张我挺喜欢 |
| 皮肤变白了 | 皮肤变⚪了 | 我自己觉得暗沉没那么明显了 |

右列是**可验证的个人事实**，左列是**无法举证的宣称**。

### 合规引擎是两层的

**第一层 · 确定性扫描**（`skills/xhs-guard/scripts/xhs_scan.py`）
纯正则 + 分级词库，不联网，不上传任何内容。负责**召回**。

```bash
python skills/xhs-guard/scripts/xhs_scan.py note.md
```

四个等级：🛑 L1 硬红线 / 🔴 L2 高风险 / 🟠 L3 中风险 / 🟡 L4 压流量。
L1/L2 是拦截项（exit 1）。

**第二层 · 语境裁决**（模型做）
扫描器不懂语境 —— 它会把「最好提前订票」和「最好用的防晒」都命中「最好」。
前者是建议语气完全安全，后者必须改。所以每条命中都要模型判断，
结论只有三种：**必须改 / 建议改 / 误报放行**。

中文子串误报用词库的 `exclude` 字段治：`平安神宫` 里的「安神」、
`治愈系` 里的「治愈」、`避雷针` 里的「避雷」、`特效镜头` 里的「特效」都不会误报。

---


## 产出长什么样

一篇一个文件夹：

```
drafts/2026-08-13-kyoto-rainy-day/
├── note.md          # 标题 / 正文 / 标签，正文能直接全选复制
├── compliance.md    # 合规报告：命中项、等级、改法、改后对比
├── checklist.md     # 发布前逐项确认（含 AI 声明）
├── script.md        # 分镜 + 口播 + 拍摄清单（视频笔记）
└── subtitle.srt     # 字幕（视频笔记）
```

`drafts/` 已 gitignore，不会上传。

---

## 目录结构

```
.
├── AGENTS.md                    # Agent 宪法：铁律、工作流、产出规范
├── README.md
├── install.ps1 / install.sh
├── .claude-plugin/plugin.json   # Claude Code plugin manifest
├── profile/
│   ├── account.md               # ★ 数据基线与内容方向（xhs-strategy 的输入）
│   └── voice.md                 # 语气护栏（跑 xhs-voice 生成）
├── samples/                     # 你的历史笔记（已 gitignore）
├── drafts/                      # 产出（已 gitignore）
└── skills/
    ├── xhs-strategy/            # ★ 定方向 · 数据复盘 · 选题
    ├── xhs-voice/               # 语气护栏 · 建档案
    │   ├── scripts/voice_stats.py       句长、标点、emoji、口头禅统计
    │   └── references/questionnaire.md  没语料时的冷启动问卷
    ├── xhs-note/                # 写笔记
    │   └── references/          标题公式 / 正文结构 / 标签与 SEO
    ├── xhs-polish/              # 改稿
    ├── xhs-guard/               # ★ 合规审核
    │   ├── scripts/xhs_scan.py          扫描器
    │   ├── scripts/lexicon.json         分级词库
    │   └── references/                  平台规则 / 安全改写 / 发布清单
    ├── xhs-script/              # 视频脚本 · 分镜
    └── xhs-vlog/                # 剪辑协助 · 字幕
        └── scripts/make_srt.py          口播稿 → .srt
```

---

## 三个脚本，单独也能用

```bash
# 合规扫描
python skills/xhs-guard/scripts/xhs_scan.py note.md
python skills/xhs-guard/scripts/xhs_scan.py --text "全网最好吃的一家，私我拿地址"
python skills/xhs-guard/scripts/xhs_scan.py note.md --strict --json

# 语气统计
python skills/xhs-voice/scripts/voice_stats.py samples

# 字幕生成
python skills/xhs-vlog/scripts/make_srt.py narration.txt -o subtitle.srt --cps 5.0
```

全部只用 Python 标准库。不联网，不上传任何内容。

---

## 维护

`skills/xhs-guard/scripts/lexicon.json` 是**经验性风险清单，不是小红书官方词表**。
平台规则在变（《社区公约 2.0》2026-01-19、AI 内容治理规则 2026-04），词库会过期。

- **被限流但扫描器没报** → 去创作中心看具体违规提示，把原因补成新规则，
  更新 `version` 和 `updated`
- **误报** → 加到对应规则的 `exclude` 数组
- **`updated` 距今超过半年** → 该去复核平台最新规则了

`profile/voice.md` 也要维护：**每积累 10 篇新笔记就重跑一次 `xhs-voice`**，
看看统计有没有漂移。她说「这个不像我」的时候，把结论写回档案 ——
一次这样的反馈价值大于十篇样本。

---

## 关于 AI 声明

《社区公约 2.0》已把「主动标明 AI 辅助工具创作」写进社区规则。
2026-04 的 AI 内容治理规则明确：平台**鼓励** AI 辅助创作
（AI 视觉创作、AI 角色创作、AI 知识科普都是鼓励方向），
但打击 AI 造假、AI 托管养号、以及**不标注的纯 AI 内容**。

封面不涉及这一条（本地 CSS 排版不是生成）。但**正文主要由 AI 起草**时 —— 发布时记得

> 【设置】→【内容类型声明】→ 勾选【笔记含 AI 合成内容】

这条会出现在每一份 `checklist.md` 里，而且**不会替你打勾**。

---

## 免责

- 词库是根据公开资料整理的经验清单，不是官方词表。**命中不等于一定违规，
  未命中也不等于一定安全。** 最终以平台实际审核为准。
- 本仓库不提供、也不会帮你实现任何规避平台审核的手段。
- 读取小红书：**只在你本人登录态下读你自己的笔记**（2026-08 放开，见 `AGENTS.md` 1.5）。
  不绕验证码/风控、不读别人的笔记、不批量扫站。优先走创作者后台。

---

MIT
