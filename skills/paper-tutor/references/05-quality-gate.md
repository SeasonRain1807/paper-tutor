# 质量闸门：`check.py` 怎么判、怎么改

三道硬约束里，"原文逐字照录"和"段落不漏不并"是机器可判的；"译文严谨"和"注释有用"只能半自动判。`check.py` 就是这道闸门：它不能替你读懂论文，但能保证交付的页面里没有编造、没有遗漏、没有把两段并成一段这类硬伤。

**基准永远是 `source.txt`**：数据向基准靠拢。只有在基准本身提取错了的时候才改基准，且改完要重跑两边。

## 一、怎么跑

```bash
python "<skill_dir>/scripts/check.py" "<dir>/data.json" --source "<dir>/source.txt"
python "<skill_dir>/scripts/check.py" "<dir>/data.json" --source "<dir>/source.txt" --json     # 给程序读
python "<skill_dir>/scripts/check.py" "<dir>/data.json" --source "<dir>/source.txt" --allow-transcribed   # 人工誊录时用
```

- 位置参数或 `--data` 都可。
- 不给 `--source` 只跑结构、译文、注释检查，并固定给一条 `no-source` 警告——**交付前必须给**。
- 退出码：有 `error` 返回 1，否则 0。可以写进循环里当断言用。

## 二、怎么读输出

```
数据：12 段 / 6 节
基准：source.txt（5710 字符）
覆盖：13/13 段原文已收录，12/12 段原文逐字命中
图片：2/2 张已按记录字节核验（sha256）

错误 [p2/verbatim] p2 的原文在 source 中找不到（最相似只有 78%）——……
提示 [verbatim-diff] p2 首个差异在 source 第 963 字符附近（数据里改了措辞、标点或数字）
      原文……grows faster than th……… / 数据……grows faster than t………

结论：未通过 — 错误 2，警告 0，提示 2
先修错误项再生成 HTML；警告项请逐条判断是否真的需要改。
```

读法：

1. 先看**覆盖**行。`13/13 段原文已收录` 说明 `source.txt` 里每个非空文本块都能在数据里找到对应；`12/12 段原文逐字命中` 说明每段 `en` 在基准里确实逐字出现。两个数不等就是有段落被并、被拆或漏掉。
2. 有图的论文再看**图片**行。`2/2 张已按记录字节核验` 才是全部通过；分子小于分母说明有图没记哈希或没通过核验。详见 `references/07-figures.md`。
3. 再看**错误**：必须清零，否则不许构建页面。
4. **警告**逐条判断：有的要改数据，有的要在交付说明里讲清楚为什么保留（例如译文比原文短是原文本身就是定义句）。
5. **提示**是线索不是罪状：`verbatim-diff` 只在你已经有一条 `verbatim` 错误时出现，告诉你第一个差异字符在哪，方便定位改错。

## 三、finding 代码表

| code | 级别 | 含义 | 处置 |
|---|---|---|---|
| `schema` | 错误 | 结构不合规范：缺字段、`id` 不连续、`section` 引用不存在、`kind` 非法、`argument_map` 引用了不存在的段 | 按 `references/02-data-contract.md` 补齐；`id` 必须是 `p1,p2,…` 连续 |
| `verbatim` | 错误 | 该段 `en` 在 `source.txt` 里找不到（归一化空白后仍找不到） | 回基准复制原文，不要凭记忆重打 |
| `verbatim-diff` | 提示 | 定位到第一个差异字符（附两侧各 40 字上下文） | 按提示把那个词/标点改回原文 |
| `para-span` | 错误 | 该段原文在基准里横跨两个文本块 | 原文是一段 → 把数据里两条并成一条；基准多空行 → 修 `source.txt` |
| `para-split` | 错误 | 两条数据对应基准里同一段 | 数据把一段拆成两条 → 合并；基准把两段并成一块 → 修 `source.txt` |
| `coverage` | 错误 | 基准里有整块文字没有对应段（≥40 字符的非标题块） | 补段；若确实是有意排除（图表标题、参考文献），在 `meta.source_note` 写明 |
| `coverage-summary` | 提示 | 覆盖数不等于总数时的汇总 | 同上，逐条看 `coverage` |
| `source-empty` | 错误 | `source.txt` 是空的或只有空白 | 重新提取 |
| `no-source` | 警告 | 没给 `--source`，逐字与覆盖全部跳过 | 交付前必须补 |
| `zh-missing` | 错误 | `zh` 没有任何中文 | 翻译 |
| `zh-not-chinese` | 错误 | `zh` 看起来就是英文原文（中文占比过低） | 翻译；不要把 `en` 复制过来占位 |
| `zh-short` | 警告 | 汉字数 / 英文词数 < 0.72（英文 ≥12 词才判） | 多半漏译了从句或插入语，逐句对照补 |
| `zh-long` | 警告 | 该比值 > 2.6 | 多半加了原文没有的解释，删回严谨翻译 |
| `zh-merged` | 警告 | 英文 ≥2 句，译文句数不到一半 | 把并掉的句子拆开 |
| `zh-split` | 警告 | 译文句数 > 英文句数×3+2 | 断句过碎，合并 |
| `note-thin` | 警告 | `summary`/`function`/`position` 某一栏 < 24 字符 | 按 `references/04-analysis-rubric.md` 重写，不能写"介绍了背景" |
| `note-duplicate` | 错误 | 三栏中两栏相似度 > 85% | 三栏回答的是三个不同问题，不能互相复制 |
| `term-untranslated` | 警告 | `terms[].en` 与 `zh` 相同 | 补上中文译名，或删掉这条术语 |
| `section-title` | 警告 | `sections[].title_en` 在基准里找不到 | 核对标题原文拼写 |
| `figure-missing` | 错误 | `figures[].path` 指向的文件不存在 | 把原图放进 `figures/`，或改相对路径 |
| `figure-type` | 错误 | 文件内容不是可识别的图片（下成了 HTML 错误页、扩展名错） | 重新取图 |
| `figure-hash` | 错误 | 图片字节与 `sha256` 记录不一致 = 图被改动过 | 从原始来源重取覆盖；确属有意换图才重跑 `--write-figure-hashes` |
| `figure-unrecorded` | 提示 | 该图还没有哈希记录 | 跑一次 `check.py --write-figure-hashes` |
| `figure-unlabeled` | 警告 | 既无 `label` 也无 `caption` | 补图号或一句图注 |
| `figure-outside` | 警告 | 图在 `data.json` 目录之外 | 复制进 `figures/`，避免交付丢图 |
| `figure-unused` | 提示 | `figures/` 里有未被任何段落引用的图 | 挂到对应段落，或删掉 |
| `figure-split` | 错误 | 同一个图号被拆到多个段落/多条 `figures[]` 里登记 | 合并成一条，挂在第一次详细展开的那段 |
| `figure-panel-label` | 错误 | `label` 写成 `Fig. 5(a)` 这类子图号 | `label` 只写 `Fig. 5`，子图说明写进 `caption` |
| `figure-band` | 错误 | 文件像素尺寸正好是某张完整图一条分带的尺寸 = 图被拦腰切断 | 用 `scripts/figures.py extract` 重取整张 |
| `figure-caption-truncated` | 错误 | `caption` 只是 `figures/_manifest.json` 里整条图注的前缀 = (a)(b) 被截掉了 | 抄 manifest 的整条 `caption` |
| `figure-label-mismatch` | 警告 | `label` 的图号与 `caption` 开头的图号不一致 | 核对图注归属，改对图号 |

## 四、判定阈值（都在 `check.py` 里，改了要同步本文）

| 项 | 阈值 | 依据 |
|---|---|---|
| 逐字相似度 | ≥ 55% 才给 diff 提示 | 低于此值多半整段重写，直接重抄更快 |
| 译文长度比 | 0.72 ≤ `zh_chars/en_words` ≤ 2.6（英文 ≥12 词时判） | 正常严谨翻译落在 1.2–2.2；中文更紧凑所以下限不是 1.0 |
| 译文句数 | `zh_sent×2 < en_sent` 判合并；`zh_sent > en_sent×3+2` 判断碎 | 允许一定重组，不允许整段并句 |
| 注释单栏 | < 24 字符判单薄 | 一句话都写不满的栏一定是空话 |
| 三栏重复 | 两两相似度 > 0.85 判重复 | 三栏是三个问题，不该同义反复 |
| 覆盖块 | < 40 字符的块跳过；标题、作者、venue、章节标题跳过 | 这些进 `meta`/`sections`，不进段落 |

## 五、逐字基准的维护规则

**可以改 `source.txt`**（改完必须重跑 `check.py`，并在 `meta.source_note` 留存说明）：

1. 页眉、页脚、页码、DOI 水印、投稿日期混进正文；
2. 跨行连字符被拆开（`inter-` + `face`），要接回 `interface`；
3. 两段之间被多插了空行，或两段被并成一块；
4. 图表标题、脚注被提取到了奇怪的位置；
5. 提取器把导航、参考文献列表混进来了（参考文献默认不收录）。

**不许改 `source.txt`**：

- 为了让某段 `en` 能通过校验而回改基准（这等于自己给自己出题再改答案）；
- 把译文或注释的措辞反写进基准；
- 为了让覆盖数好看而删掉基准里一段原文。

原则：基准是"原文长什么样"的存档，不是"让数据过关"的工具。数据写错了就改数据。

## 六、把基准换掉的时机

如果提取质量问题太多（例如 PDF 无文本层、HTML 版缺公式），不要硬修基准，换来源重来：

1. 优先找出版方 HTML 或 arXiv 的 HTML 版（`--url` 直接提）；
2. 其次找可复制的 Word/文本版；
3. 都没有时，才由人**誊录**并加 `--allow-transcribed`：
   - 此时 `verbatim` 错误降级为警告，覆盖与段落边界仍然报错；
   - `meta.source_note` 必须写"原文为人工誊录，未与 PDF 逐字核对"；
   - 交付说明里要重复这句话，让用户知道风险在哪。

绝不"凭印象转写全文"——那会让整个页面的可信度归零。

## 七、改完以后的动作链

```bash
python "<skill_dir>/scripts/autofill.py" --data "<dir>/data.json" --source "<dir>/source.txt"   # 把 "@@段号" 填回逐字原文
python "<skill_dir>/scripts/check.py"  "<dir>/data.json" --source "<dir>/source.txt" --write-figure-hashes  # 仅首次登记图
python "<skill_dir>/scripts/check.py"  "<dir>/data.json" --source "<dir>/source.txt"   # 0 error
python "<skill_dir>/scripts/build.py"  "<dir>/data.json" -o "<dir>/3_精读阅读页.html"
python "<skill_dir>/scripts/check.py"  "<dir>/data.json" --source "<dir>/source.txt"   # 构建后再跑一次
```

- **只改 `data.json`，不手改 `3_精读阅读页.html`**：页面是构建产物，手改会在下一次构建被覆盖；
- 构建不会因为警告失败，所以顺序无所谓，但交付前这一次 `check` 必须是 0 error；
- 改完数据后旧 HTML 就是过期的，必须重新构建，否则用户看到的是旧译文。

## 八、交付前清单

- [ ] `check.py --source` 结果 0 错误；
- [ ] `图片：M/M`（有图时），每张都记过哈希并核验通过；
- [ ] 每条警告都看过，保留的那些准备好一句话解释；
- [ ] 构建后重新跑过 `check`，HTML 生成时间比 `data.json` 新；
- [ ] 打开 `3_精读阅读页.html` 抽查三段：第一段、最长的一段、公式/图表/脚注段；
- [ ] 有图的段抽查一张，点开灯箱看 `1:1` 与原图下载是否正常；
- [ ] 确认页面里没有外链（`file://` 双击能开、断网能看）；用 `--figure-mode link` 构建时确认 `figures/` 齐全；
- [ ] 交付说明里写清：段数、节数、图数、校验结论、原文来源、以及**存疑点**（取不到原图的图、誊录风险、作者笔误）。
