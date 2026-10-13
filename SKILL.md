---
name: product-promo-video
description: |
  用纯代码制作 Apple 产品介绍风格的 40–65 秒产品宣传片（code2video）：HTML/CSS/JS 写 2D 动画（render(t) 纯函数），无头 Chrome 逐帧截图 + ffmpeg 出 1080p 视频，numpy 合成卡拍配乐与界面音效，可选 TTS 旁白，一键出中英双语版、网页压缩版和封面。片头片尾是彩色剪纸拼贴，功能段是浅色桌面 + 1:1 复刻的真实产品界面 + 光标交互演示，标题关键词渐变色 + 手绘强调。内含可直接渲染的模板项目、渲染/配乐/人声/收尾脚本，以及从 26 版真实迭代里总结的分镜、文案、视觉、配乐经验和审片清单。
  当用户想给 App、软件、SaaS、开源项目、插件、硬件配套 App 做产品介绍视频、宣传片、promo video、demo 视频、launch video、官网首屏视频、README/博客里的演示动画、产品发布短片，或提到"像苹果发布会那样介绍产品""用代码生成视频""code2video""HTML 动画导出 MP4""给视频配卡点音乐"时使用——即使用户没说"技能"或没提到具体技术也应使用。不适用于剪辑实拍素材、纯 AI 文生视频、或只要一张静态海报的场景。
---

# 产品介绍视频（code2video）

产出：一支 40–65 秒、1920×1080、30fps 的产品介绍片，画面和声音全部由代码生成，可逐帧复现、可反复小改。
风格基准：Apple 产品介绍式的克制讲述（一段只讲一件事、标题短、留白多），片头片尾用彩色剪纸拼贴做记忆点，中间功能段用真实界面演示"怎么用"。

> 这套方法的核心价值是**改得动**：宣传片要改很多轮（原始项目改了 26 版），每轮反馈通常只涉及一个时间点、一句文案或一个小节的配乐。所以一切设计都服务于"小改一处，重渲即得"。

## 技术栈与目录

| 层 | 做法 | 文件（本技能内） |
|---|---|---|
| 画面 | 单个 HTML，`render(t)` 只依赖时间 t；文案集中在 `TX`，`?lang=en` 切语言 | `assets/template/promo.html` |
| 时间轴 | 页面里的 `<script id="timeline" type="application/json">`：BPM、小节、场景、事件、台词。**画面、配乐、人声都读这一份** | 同上 |
| 渲染 | Node 原生 WebSocket 走 CDP 驱动无头 Chrome，逐帧 `render(t)` → 截图 → 管道给 ffmpeg | `scripts/render_video.mjs` |
| 配乐 | numpy/scipy 加性合成：铺底和弦 + 固定动机 + 按场景 energy 加减配器 + 界面音效 | `scripts/synth_music.py`（依赖 `scripts/timeline.py`） |
| 人声（可选） | macOS `say` 或外部录音，按台词时间对齐，自动压低配乐 | `scripts/add_voice.py` |
| 收尾 | 响度归一合成、网页两遍编码、封面、关键帧总览图、响度测量 | `scripts/finalize.py` |

环境：Node ≥ 22、ffmpeg、Chrome/Chromium（`CHROME=` 可指定路径）、Python 3 + numpy + scipy + Pillow。开始前先确认这些都在，缺什么告诉用户，不要擅自装进用户的 Python 环境。

建议的项目结构（在用户的项目里新建，例如 `promo/`）：

```
promo/
├── promo.html          # 从 assets/template/promo.html 复制后改
├── assets/             # 产品截图、图标、照片、导出的界面素材
├── storyboard.md       # 分镜表 + 事实出处表（阶段 1 产出）
├── out/                # 成片：<产品>-promo-<秒>s-v<N>[-en].mp4，旧版不覆盖
└── log/                # 各脚本自动写日志
```

所有脚本都在 `promo/` 目录下运行，路径参数相对于它。下文 `$SK` 指本技能目录。

## 工作流程

每个阶段末尾都有一个**确认点**：把产出给用户看，得到确认再进入下一阶段。原因是越往后改动越贵——文案和分镜改起来几乎零成本，渲染好的整片要 1–2 分钟一遍，配乐重新编排更费时间。

### 阶段 0：收集事实与目标

先读产品本身：README、官网文案、源码里的界面代码、截图、发布说明。然后跟用户确认（已能从材料里得到答案的就不要问）：

- **用途与受众**：官网首屏、社媒、路演、README/博客？决定时长、节奏和是否需要声音（官网首屏常静音自动播放 → 画面要能独立讲清楚）。
- **要讲的功能**：挑 3–5 个，每个功能一段。超过 5 个就要取舍，宁可少讲，讲透。
- **语言版本**、**品牌色与字体**、**能公开的素材**（真人照片、仓库地址、用户数据都要用户明确同意）。
- **需不需要旁白**：默认不要（Apple 风多是字幕式标题 + 音乐），用户想要再加。

把每个要上画面的**数字和说法都记下出处**（源码注释、README、实测数据）。宣传片里的一句错话会被反复看到；原始项目就出现过"支持任意 OpenAI 兼容模型"这种实际没实现的说法，后来不得不改。拿不准的说法问用户，不要自己补。

### 阶段 1：分镜与文案（确认点）

写 `storyboard.md`：一张分镜表 + 一张事实出处表。结构、节拍、文案写法见 `references/storyboard-copy.md`。要点：

- 先定 BPM，所有镜头切换对齐小节（96 BPM → 每小节 2.5 s；128 BPM → 1.875 s）。音乐卡点是这种片子"高级感"的主要来源。
- 默认结构：片头（产品名 + 一句价值主张）→ 3–5 个功能段（每段一个标题 + 一次真实交互）→ 总结 → 片尾（呼应片头 + 行动入口）。
- 每段标题是一句短的结论句，关键词上色；副标题说清"怎么做到的"。

给用户看分镜表和全部文案，确认后再写代码。

### 阶段 2：风格定调（确认点，建议做）

片头是第一印象，也是审美分歧最大的地方。先用模板做 2–3 张片头静帧试稿（不同构图/配色），用 `render_video.mjs stills` 出图让用户挑，而不是直接做整片再推翻。视觉规则见 `references/visual-motion.md`。

### 阶段 3：搭画面

1. `cp $SK/assets/template/promo.html promo/promo.html`，先原样渲染一次静帧，确认环境没问题。
2. 改 `#timeline`：BPM、小节数、场景（`energy` 0–3 决定配乐密度，`deco` 决定标题强调方式）、事件（点击、输入、出卡片……每个有 `id` 给画面引用，`type` 决定音效）。
3. 改 `TX` 文案，然后把示例产品窗口换成**真实产品界面的复刻**：从源码或截图读出真实尺寸、圆角、颜色、文案，按统一倍数（通常 1.4–1.6 倍）放大。界面上出现的按钮、状态文字、输出内容都要和真实产品一致——观众会拿视频和产品对照，任何"视频里有、产品里没有"的东西都会让人不信任。
4. 每个功能段里要有**动作**：光标移动 → 点击涟漪 → 界面响应。一个画面静止超过约 2 秒就会显得"没东西"，要补一个小交互（删除、滚动、切换状态）。

模板里已有的可复用部件：剪纸拼贴（`put/paper/tape/ctext/cluster/enter`）、标题与手绘强调（`headline/decorate`）、窗口进出场、光标路径与点击涟漪（`CUR/cursorAt/cursor`）、逐字输入、流式回复、大数字盖章、总结卡片。新部件照同样的写法加：一个函数接收 t，用 `E/EI/win/reveal/pop` 计算状态，在 `render(t)` 里调用。

**边写边看静帧**：

```bash
node $SK/scripts/render_video.mjs stills promo.html out/stills 3,8.5,12.2   # 关键时刻的静帧
node $SK/scripts/render_video.mjs sheet  promo.html out/sheet --every 2.5     # 每 2.5 s 一张
python $SK/scripts/finalize.py sheet out/sheet out/sheet.jpg                  # 拼成带时间标签的总览图
```

渲染脚本遇到页面 JS 报错会立即中止并打印错误，不会默默输出一片空白。

### 阶段 4：声音

```bash
python $SK/scripts/synth_music.py promo.html out/music.wav          # 配乐 + 时间轴里所有事件的音效
python $SK/scripts/add_voice.py promo.html out/music.wav out/music_voice.wav --style clean   # 可选：旁白
```

配乐脚本按时间轴自动卡点，改了分镜重跑即可。它会报告"低于 -40 dB 的 100 ms 窗口数"，应为 0（有空洞就会显得不连贯）。改和弦、动机、音色、加新音效类型的方法，以及多轮试听得出的编曲原则，见 `references/audio.md`。如果用户有授权曲库音乐，就用它的 BPM 设时间轴，跳过合成。

配乐要让用户**单独试听**确认（导一个 mp3 或直接合到片子里），音乐好不好只能靠人耳判断。

### 阶段 5：渲染、审片（确认点）

```bash
node $SK/scripts/render_video.mjs video promo.html out/silent.mp4                 # 整片（时长读 window.DURATION）
node $SK/scripts/render_video.mjs video promo.html out/part.mp4 --from 12 --to 20 # 只渲一段，改局部时用
python $SK/scripts/finalize.py mux out/silent.mp4 out/music.wav out/<产品>-promo-40s-v1.mp4   # 默认 -16 LUFS
python $SK/scripts/finalize.py sheet out/<产品>-promo-40s-v1.mp4 out/v1-sheet.jpg --every 2
```

渲染耗时约为片长的 1.5 倍（40 s 的片子约 1 分钟）。交给用户前自己先按 `references/qa-checklist.md` 过一遍：看总览图，再对每个功能段的关键时刻出静帧放大检查文字遮挡、溢出、对齐、与真实界面不一致的地方。

### 阶段 6：迭代

- 每一版都**新文件名**（`-v2`、`-v3`），不覆盖旧版；页面文件在风格大改时也另存一份（`promo_v2.html`），小改直接改。
- 只改反馈指向的地方。用户说"这段太空"，就补一个交互，不要顺手重做配色。
- 每轮在 `storyboard.md` 末尾记一行：版本号、用户反馈、改了什么。这份记录本身就是下一次做视频时最有用的东西。
- 改时长 / 插入段落时，在时间轴里整体顺延后续小节，配乐会自动跟上；注意页面里写死的秒数（如果有）也要一起改。

### 阶段 7：交付

```bash
node $SK/scripts/render_video.mjs video promo.html out/silent-en.mp4 --query lang=en     # 英文版
python $SK/scripts/finalize.py mux out/silent-en.mp4 out/music.wav out/<产品>-promo-40s-v3-en.mp4
python $SK/scripts/finalize.py web  out/<产品>-promo-40s-v3.mp4 out/web.mp4               # 500k+96k 两遍编码，约 3–5 MB
python $SK/scripts/finalize.py poster out/<产品>-promo-40s-v3.mp4 3.4 out/poster.jpg      # 封面取片头标题帧
```

- 英文版：只翻标题、说明和剪纸文案；产品自己的界面和输出如果真实产品只有中文，就保持中文（忠于产品）。英文通常比中文长 30–50%，必须逐段出静帧检查折行。
- 脱敏版：需要公开但不想带个人信息（姓名、仓库地址）时，在页面里加一个 URL 参数（模板的做法：`?anon=1` 时替换 `TX.cta`），渲染时 `--query anon=1`。
- 最后整理：只保留最新版和风格有明显变化的节点版本，其余移到归档/回收站前先列清单给用户看。

## 最容易踩的坑（来自真实迭代）

1. **画面跟着鼓点抖动 / 放大缩小**：看着廉价、晃眼。卡拍应体现在"东西在拍点上出现"，不是整体震动。
2. **广告腔**：痛点开场（"太麻烦了！"）、数字轰炸、放射光、满屏高饱和色——用户会觉得像电商广告。Apple 风要克制：中性背景，彩色只给关键词。
3. **示例不真实**：演示内容要用产品真实会输出的东西（真实的查词卡格式、真实的回答结构），不要编一个更好看的。
4. **功能段画面静止**：超过约 2 秒没有任何变化就要补交互。
5. **一处改动牵动时间**：所有时间点都从 `#timeline` 推出来，不在别处写死秒数；手工在两处同步时间迟早会错位。
6. **配乐"不连贯"**：几乎总是因为段落之间有空洞或和弦循环被打断，不是因为调子不好。
7. **标注和手绘圈太多**：交互动画本身就能说明的，不要再加"更高""点两下才删"这类标注，用户会嫌啰嗦。
8. **英文版排版**：标题折成三行、副标题被窗口挡住是常态，要对英文单独调标题区宽度和字号。
9. **素材分辨率**：放大 1.3 倍以上的位图会糊，导出素材时就按最终显示尺寸的 1–2 倍准备。

## 参考文件

- `references/storyboard-copy.md`：分镜结构模板（40/60 s 两种）、节拍换算、标题与副标题写法、示例取材、双语处理。**写分镜前读。**
- `references/visual-motion.md`：版式坐标、配色规则、剪纸材质配方、动效词汇表（每种动效什么时候用）、复刻真实界面的方法。**搭画面前读。**
- `references/audio.md`：配乐脚本结构、怎么改调性/动机/配器、音效类型扩展、旁白与环境声、响度标准、试听迭代的经验。**做声音前读。**
- `references/qa-checklist.md`：审片与交付清单。**每次交片前过一遍。**
