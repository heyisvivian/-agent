# zine 极简杂志风 · 视觉体系

改编自 [gc-minimal-zine-poster](https://github.com/LiamGvchi/gc-minimal-zine-poster)
的 `references/style-system.md`（MIT）。

原版核心身份：**"Poetic paper-texture negative-space micro-editorial poster"**
—— 诗性的、纸纹的、负空间的、微编辑感海报。

调性是日韩独立 zine / 极简编辑设计。**不是**商业广告、不是光泽样机、不是电影感。

---

## 我改了什么，为什么

| 项 | 原版 | 本仓库 | 原因 |
|---|---|---|---|
| 画布 | 3:5 竖版 | **3:4** | 小红书信息流曝光面积最大的比例 |
| 负空间 | 70%–90% | `zine` 约 60% / `zine-pure` 75%+ | 缩略图里标题要读得清 |
| 标题字号 | 很小，"像便条不像广告标题" | `zine` 88–100px / `zine-pure` 约 62px | 同上 |
| 实现方式 | 全部靠 image_gen | 文字用本地 HTML/CSS 渲染 | AI 写中文不可靠 |

其余（纸纹、锚色系统、字体类别、印刷缺陷、装饰元素、反身份清单）**照搬**。

原版是海报，可以要求观者靠近看。小红书封面要在缩略图竞争里活下来 ——
这是唯一的分歧点，其他地方原版的判断都比"小红书封面最佳实践"更好。

---

## 画布与表面

- 满幅暖纸纹理：纤维可见、细颗粒、灰尘、扫描噪声、轻微泛旧、哑光
- 默认无边框、无样机
- 平面正投影扫描感，漫射光，低到中对比，**无硬阴影**

实现：`.paper-fiber`（两层 repeating-linear-gradient 做纤维 + 一层
radial-gradient 做边缘泛旧）+ `.grain`（内联 SVG `feTurbulence` 噪声，
`mix-blend-mode: multiply`）。全部 CSS，不依赖外部图片。

---

## 构成规则

- **负空间**：读起来是"敞开的纸"
- **视觉簇**：占画面 8%–25%
- **一个主隐喻** —— 不要完整插画场景，不要物件清单
- **簇的位置**（`--pos`）：
  `lower-left` · `upper-right` · `center-low` · `center-high` · `left-middle` · `right-middle`

原版还有"deliberate offset"（刻意偏移）—— 想要的话直接改 `cover.html` 的
`.content` inset。

---

## 锚色系统（这是命门）

- **一个**主高彩度色。可选：
  钴蓝 cobalt · 群青 ultramarine · 青 cyan · 紫 violet · 洋红 magenta ·
  粉 pink · 柠檬黄 lemon · 梨绿 pear · 橙 orange · 番茄红 tomato
- 锚色占**全画面 0.8%–2.5%**，或**视觉簇的 15%–35%**
- 载体：主体物、剪影、色块、局部照片、或加粗的碎片化文字
- 可选第二色：**最多约 10% 的彩色面积**，必须明显次要
  （本仓库只用它做套印偏移，`--accent2`）
- **纸、灰度图像、微文字保持低调**

> 多色 = 违背整套风格。一个颜色，一个位置，说清占多少。

---

## 字体

允许的类别：**打字机 · 老式衬线 · 细衬线 · 等宽 · 克制的小号无衬线**

行为（原文）：
> "Text behaves like a note, fragment, label, date, or private sentence
> rather than an advertising headline."
> 文字的行为像便条、碎片、标签、日期、私人句子，而不是广告标题。

分布方式：贴边短语 · 档案微文字 · 斜向碎片 · 散落字母 · 色块内文字 ·
幽灵文字 · 极简说明

本仓库的实现：
- 标题用宋体族（`Songti SC` / `STSong` / `Source Han Serif SC` / `SimSun`），
  字重 400，字距 0.05–0.14em
- 标签、说明、微文字、署名用等宽族（`Courier New` / `SFMono`），字距 0.10–0.34em，大写

**中文用宋体是关键。** 换成黑体粗体立刻变成通稿封面。

---

## 印刷与质感词汇

复制方式：半调 halftone · xerox 柔化 · riso 颗粒 · 活版压痕 letterpress bleed ·
扫描线 scanline · 纸张边缘 · 轻微套印偏移 misregistration

纸色：暖白 warm-white · 象牙 ivory · 浅灰 light-gray · 旧纸黄 old-yellow ·
浅卡其 khaki · 浅牛皮纸 kraft

实现：
- 套印偏移 = 锚色块的 `::after` 用第二色错开 4px/3px，`mix-blend-mode: multiply`
- 半调 = `radial-gradient` 圆点，`background-size: 4px 4px`，multiply 叠在照片上
- 扫描线 = 极轻的 `repeating-linear-gradient`

---

## 视觉锚形态

单锚 · 双面板 · 重叠碎片 · 不规则剪裁 · 环绕标记 · 文字主导

主体形态：褪色照片 · 剪报 · 平面剪影 · 实心油墨块 · 印刷插图 · 标本 ·
半透明叠层 · 抽象材质窗口

本仓库默认用**不规则剪裁的实心油墨块**（`clip-path` 轻微不规则四边形）
和**照片窗口**（`zine-photo`）。

---

## 装饰元素

细线 · 虚线 · 小箭头 · 透明矩形 · 点群 · 套准标记 · 手绘曲线

本仓库有：细实线（`.rule`）、虚线（`.rule-dashed`）、点群（`.dots`）、
套准标记（`.regmark`，十字 + 圆环，左上右下各一）。

`--no-marks` 可以全关掉。

---

## 调性词汇

安静 · 诗性 · 疏离 · 档案感 · 日记感 · 记忆感 · 日韩独立 zine
夏天 · 独处 · 童年 · 海边 · 午后 · 夜晚 · 轻微超现实

写 image_gen prompt 时从这里取词。

---

## 反身份（必须避开）

满幅场景 · 商业层级 · 产品广告 · logo · CTA · 光泽样机 · 干净 UI 白 ·
电影感打光 · 3D · 霓虹 · 赛博朋克 · 可爱风 · 时尚大片感 · 密集拼贴 ·
多色混乱 · 库存照片写实感 · 长段文字块

这份清单直接抄进 image_gen 的负面提示里。

---

## 为什么这套风格适合她

她的 voice profile（见 `profile/voice.md`）是：第一人称独白、不用感叹号、
不用 emoji、标题偏短的陈述句、结尾不升华。

zine 这套是**视觉上的同一件事** —— 安静、克制、靠一个具体的东西承载情绪，
而不是靠喊。

反过来，`plain` / `photo` 那种大黑字封面，视觉语气和她的文字语气是冲突的：
封面在喊，正文在低声说话。用户点进来会有落差。

**封面的语气应该和正文的语气一致。** 这比"哪种封面点击率高"更重要 ——
点击率高但语气不符，涨的是不会留下的粉。
