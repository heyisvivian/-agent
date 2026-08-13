# xhs-agent · 小红书创作技能包

给 **Codex CLI** 用的小红书创作助手（同时兼容 Claude Code）。
按你自己的语气写文案、出 3:4 封面、写视频脚本和字幕，**并且在发布前把违规词和限流风险扫一遍**。

赛道侧重：**生活 · 日常 · vlog · 旅行**

---

## 它做四件事

| | 做什么 | 技能 |
|---|---|---|
| **写** | 从一个想法产出完整笔记，语气是你的 | `xhs-note` |
| **改** | 把你写好的稿子改好，但不动你的语气 | `xhs-polish` |
| **拍** | 视频脚本、分镜、口播稿、`.srt` 字幕 | `xhs-script` `xhs-vlog` |
| **过审** | 违禁词、限流风险、平台红线，发布前全扫一遍 | `xhs-guard` |

配套两个：`xhs-voice`（学你的语气，建档案）、`xhs-cover`（出封面图）。

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

装完 install 脚本会自检 Python、浏览器、Codex，并跑一次冒烟测试。

### Claude Code

这个仓库同时是一个标准 plugin（`.claude-plugin/plugin.json` + `skills/`）。
在 Claude Code 里把仓库目录添加为本地 plugin 就能用。

### 依赖

| 需要 | 用来 | 备注 |
|---|---|---|
| **Python 3.9+** | 合规扫描、封面渲染、字幕生成 | 只用标准库，不装任何包 |
| **Edge 或 Chrome** | 封面 HTML→PNG 渲染 | **Windows 自带 Edge，零安装** |
| Codex CLI | 出图用内置 `image_gen` | 走 ChatGPT 订阅，**不需要 API key** |

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

## 封面图怎么出的

| 做什么 | 谁做 | 为什么 |
|---|---|---|
| 背景、氛围、质感 | Codex 内置 `image_gen` | 走 ChatGPT 订阅，不需要 API key |
| **中文标题文字** | 本地 HTML/CSS 渲染 | AI 出图写中文经常缺笔画、错字、字距乱 |

封面标题是要被人读的，不能赌 AI 这次能不能把字写对。所以**背景归 AI，文字归渲染器**。

### 风格：zine 极简杂志风

视觉体系参考 [gc-minimal-zine-poster](https://github.com/LiamGvchi/gc-minimal-zine-poster)：
**纸纹负空间 + 单一高彩度锚色 + 安静的宋体／打字机字 + 印刷缺陷**（半调网点、
颗粒、套印偏移、套准标记）。纸纹和颗粒是 CSS + 内联 SVG 噪声做的，不依赖任何外部图片。

```bash
python skills/xhs-cover/scripts/render_cover.py \
  --title "京都下雨那天|我什么都没干" \
  --label "travel [03]" --caption "一个人旅行 · 第 3 天" \
  --micro "kyoto 2026.08" --sig "@vivian" --out cover.png
```

出 1080×1440（3:4）PNG。五种样式：

| 样式 | 说明 |
|---|---|
| `zine` ★默认 | 留白约 60%，标题 88–100px。安静但缩略图里读得清 |
| `zine-pure` | 忠实原版：留白 75%+，字很小。好看，但靠封面抓陌生人时吃亏 |
| `zine-photo` | 照片装进不出血窗口，去饱和 + 压网点 + 叠锚色油墨 |
| `plain` / `photo` | 传统大黑字封面。想要冲击力时用 |

**原版是 3:5 海报、留白 70–90%、字很小**；小红书封面是 3:4 且要在信息流缩略图里
被看清，完全照搬标题会小到读不出来。`zine` 是调过比例的版本，`zine-pure` 是忠实版
—— 两个都在，你自己挑。理由写在 [zine-style.md](skills/xhs-cover/references/zine-style.md)。

### 锚每篇按主题换

封面中间那个高彩度图形（锚）**不是固定方块** —— 26 个形状，按这篇的核心隐喻挑：

| 组 | 形状 |
|---|---|
| 几何 / 通用 | `block` `disc` `ring` `arc` `triangle` `cross` `slash` `bracket` |
| 数据 / 时间 | `bars` `timeline` `steps` `dots-grid` `arrow` |
| 制度 / 法规 | `stars` `stamp` `scale` `shield` `ban` |
| 自然 / 生活 | `moon` `waves` `rain` `sun` `window-frame` `cup` |
| 抽象材质 | `halftone` `grain-square` |

库里没有就 `--anchor-svg` 自己画（viewBox `0 0 100 100`，颜色用 `currentColor`）。

### 配色固定，锚变化

| | 变不变 | 为什么 |
|---|---|---|
| 纸色 + 锚色 + 署名 | **固定** | 主页九宫格的辨识度靠这个 |
| 锚形状 | **每篇换** | 封面要指向这一篇的内容 |

固定那部分写进 `profile/cover.json`，脚本自动往上找，不用每次敲。
命令行参数优先级更高，渲染时会打印实际生效的字段。

字号按字数自动算，扣掉字距和内缩，保证不折行。每次渲染都在 PNG 旁边留一份
`cover.html` —— 想微调改它，然后 `--from-html cover.html` 重渲。

---

## 产出长什么样

一篇一个文件夹：

```
drafts/2026-08-13-kyoto-rainy-day/
├── note.md          # 标题 / 正文 / 标签，正文能直接全选复制
├── note-b.md        # 进阶版（如果出了）
├── compliance.md    # 合规报告：命中项、等级、改法、改后对比
├── checklist.md     # 发布前逐项确认（含 AI 声明）
├── cover.png        # 1080×1440 封面
├── cover.html       # 排版源文件，可改
├── cover-bg.png     # image_gen 出的背景（如有）
├── imagegen.md      # 用过的出图 prompt，方便复现
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
│   └── voice.md                 # ★ 你的语气档案（跑 xhs-voice 生成）
├── samples/                     # 你的历史笔记（已 gitignore）
├── drafts/                      # 产出（已 gitignore）
└── skills/
    ├── xhs-voice/               # 学语气 · 建档案
    │   ├── scripts/voice_stats.py       句长、标点、emoji、口头禅统计
    │   └── references/questionnaire.md  没语料时的冷启动问卷
    ├── xhs-note/                # 写笔记
    │   └── references/          标题公式 / 正文结构 / 标签与 SEO
    ├── xhs-polish/              # 改稿
    ├── xhs-guard/               # ★ 合规审核
    │   ├── scripts/xhs_scan.py          扫描器
    │   ├── scripts/lexicon.json         分级词库
    │   └── references/                  平台规则 / 安全改写 / 发布清单
    ├── xhs-cover/               # 封面图
    │   ├── scripts/render_cover.py      HTML → 1080×1440 PNG
    │   ├── assets/cover-template.html   排版模板（纸纹/颗粒/网点都在这）
    │   └── references/zine-style.md     zine 视觉体系与改编说明
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

# 封面渲染
python skills/xhs-cover/scripts/render_cover.py --title "标题|第二行" --out cover.png
python skills/xhs-cover/scripts/render_cover.py --title "..." --tone kraft --accent tomato --out cover.png

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

所以：用了 `image_gen` 出图，或正文主要由 AI 写 —— 发布时记得

> 【设置】→【内容类型声明】→ 勾选【笔记含 AI 合成内容】

这条会出现在每一份 `checklist.md` 里，而且**不会替你打勾**。

---

## 免责

- 词库是根据公开资料整理的经验清单，不是官方词表。**命中不等于一定违规，
  未命中也不等于一定安全。** 最终以平台实际审核为准。
- 本仓库不提供、也不会帮你实现任何规避平台审核的手段。
- 不抓取小红书。语料一律手动提供。

---

MIT
