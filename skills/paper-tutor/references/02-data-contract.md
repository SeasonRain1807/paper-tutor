# data.json 数据契约

`build.py` 与 `check.py` 共用这一份契约。字段缺失或类型错误时构建器直接失败并报出行号/段落 id，不会产出半成品页面。

## 顶层

```json
{
  "meta": { ... },
  "sections": [ ... ],
  "paragraphs": [ ... ]
}
```

## meta

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `title_en` | string | 是 | 论文英文标题，逐字照录（大小写、标点按原文） |
| `title_zh` | string | 是 | 标题中译 |
| `authors` | string[] | 否 | 按原文顺序；`"et al."` 保留 |
| `venue` | string | 否 | 期刊/会议/预印本平台，如 `NeurIPS 2024`、`arXiv preprint` |
| `year` | string | 否 | 四位年份，作为字符串避免被改写 |
| `doi_or_url` | string | 否 | DOI 或稳定链接；页面里作为可点击链接 |
| `one_line` | string | 是 | 全文一句话结论，中文，40–80 字 |
| `argument_map` | object[] | 是 | 论证链，见下 |
| `source_note` | string | 是 | 来源与范围说明：来源类型、版本、是否节选、有无誊录、有无未提取的图表 |
| `generated_at` | string | 否 | 构建时自动写入，不用手填 |

`argument_map` 每项：

```json
{"stage": "研究缺口", "paras": "P4–P6", "note": "现有方法只在小规模图上验证，缺少跨域证据"}
```

- `stage`：环节名，建议使用 `背景 / 问题 / 缺口 / 方法 / 证据 / 讨论 / 结论` 一类词，5–9 项。
- `paras`：覆盖的段落编号，用 `P` + 序号，范围用 `–`。编号必须在 `paragraphs` 里真实存在，`check.py` 会校验。
- `note`：为什么这个环节成立，一两句话，不要复述段落标题。

## sections

```json
{"id": "s1", "title_en": "3 Method", "title_zh": "3 方法"}
```

- `id`：`^[a-z][a-z0-9_-]*$`，全篇唯一。
- `title_en`：与 `source.txt` 中的标题行逐字一致。
- 顺序即页面顺序。没有编号的章节（Abstract、References）也照常建 section。

## paragraphs

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | string | 是 | `p1`、`p2`… 连续递增，与页面顺序一致 |
| `section` | string | 是 | 必须是 `sections[].id` 之一 |
| `kind` | string | 是 | `body` / `abstract` / `caption` / `equation` / `footnote` / `quote` / `reference` |
| `label` | string | 否 | 中文角色标签，2–8 字，如 `研究缺口`、`方法概述`、`实验设置` |
| `en` | string | 是 | 原文，逐字；仅允许把排版换行合并为空格。**不要手抄**：先写占位符 `"@@段号"`，再用 `scripts/autofill.py` 填回（见文末） |
| `zh` | string | 是 | 逐句中文翻译 |
| `preserve_breaks` | bool | 否 | 为 `true` 时保留 `en` 中的换行（公式、代码、诗歌），默认合并为空格 |
| `analysis` | object | 是 | 见下 |
| `figures` | object[] | 否 | 这段文字讲到的论文插图；出现即在该段左侧显示原图，见下 |

### analysis

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `summary` | string | 是 | 这段讲了什么：陈述了哪些事实、主张或证据。建议 80–200 字 |
| `function` | string | 是 | 这段起什么作用：给出功能性判断，并说明依据 |
| `position` | string | 是 | 在全文论证结构中的位置：承接什么、引出什么、处于哪个环节 |
| `terms` | object[] | 否 | `{"en": "...", "zh": "..."}`，本段关键术语 |
| `questions` | string[] | 否 | 读完该段值得追问的问题，1–3 条 |
| `caveat` | string | 否 | 存疑、疑似笔误、图表未能提取等提示 |

`summary` / `function` / `position` 三栏是页面的三个区块，缺一不可；三栏内容不许互相复制。

### figures

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `path` | string | 是 | 相对 `data.json` 所在目录的路径（推荐放 `figures/`），扩展名必须是 `.png/.jpg/.jpeg/.gif/.webp/.bmp/.avif/.svg` |
| `label` | string | 否 | 面上显示的图号，如 `Figure 3`、`图 3`；省略时显示 `图 N`。**只写图号**，不写 `Fig. 5(a)` 这类子图号 |
| `caption` | string | 否 | 图注。原文有图注时照录；也可写一句中文说明，但不要与 `kind: "caption"` 的段落重复 |
| `alt` | string | 否 | 读屏与图未加载时的替代文字，一句话说清这张图画了什么 |
| `source` | string | 否 | 图从哪来：`论文 Figure 3，取自 arXiv HTML`、`用户提供的导出图`、`docx 内嵌 media/image3.png` |
| `sha256` | string | 否 | 64 位小写十六进制。**不要手写**，用 `check.py --write-figure-hashes` 写入 |
| `note` | string | 否 | 这张图与文字的关系提示（如"图中虚线是本文方法"） |

约束：`sha256` 一旦记录，图片字节再变就是错误（`figure-hash`）——这正是"不改变图片任何信息"的机器保证。`label` 与 `caption` 全缺会给 `figure-unlabeled` 警告。

**一条 `figures[]` = 一张完整图 + 一条完整图注。** 图在 PDF 里被排版拆成多条位图带时（(a)(b) 两个子图各占一条），要先拼回整张再登记；`caption` 写整条（含 (a)(b)），不要拆成 `Fig. 5(a) …` / `Fig. 5(b) …` 两条。`scripts/figures.py extract` 会生成 `figures/_manifest.json`（每张图的整条图注与各分带像素尺寸），`check.py` 用它核对：文件尺寸等于某条分带 → `figure-band`；`caption` 只是整条图注的前缀 → `figure-caption-truncated`；`label` 带 `(a)`/`(b)` → `figure-panel-label`；同一图号登记了两条 → `figure-split`。

图不参与"原文逐字"校验：`source.txt` 是文字基准，图是伴随材料。

## 最小可用示例

```json
{
  "meta": {
    "title_en": "Sparse Attention Revisited",
    "title_zh": "重访稀疏注意力",
    "one_line": "在同等算力下，结构化的稀疏模式优于学习得到的稀疏模式。",
    "argument_map": [{"stage": "缺口", "paras": "P2–P3", "note": "缺少同算力下的受控比较"}],
    "source_note": "arXiv:2401.00001 v2 HTML 全文，正文完整"
  },
  "sections": [{"id": "s1", "title_en": "1 Introduction", "title_zh": "1 引言"}],
  "paragraphs": [{
    "id": "p1", "section": "s1", "kind": "body", "label": "问题引入",
    "en": "Transformers scale quadratically with sequence length.",
    "zh": "Transformer 的计算量随序列长度呈二次增长。",
    "analysis": {
      "summary": "指出 Transformer 的二次复杂度是长序列建模的根本障碍。",
      "function": "以公认事实开场，把读者带到待解决的问题上，为后文的稀疏化动机铺路。",
      "position": "引言第一段，处于从背景到问题的过渡位置，尚未涉及作者方案。"
    }
  }]
}
```

## 校验规则（构建与检查共用）

- `paragraphs` 非空；`id` 唯一且按 `p<数字>` 递增。
- `section` 必须存在；`sections[].id` 唯一。
- `kind` 必须在枚举内。
- `en` / `zh` / `analysis.summary` / `analysis.function` / `analysis.position` 非空且去空白后长度 ≥ 12 字符。
- `en` 与 `zh` 不允许相同（漏译的典型症状）。
- `argument_map[].paras` 引用的编号必须存在。
- `figures[].path` 非空、扩展名在允许列表内；`sha256` 若存在必须是 64 位小写十六进制。
- 图片文件本身：存在、能识别出图片格式、与记录的 `sha256` 一致（三者分别对应 `figure-missing` / `figure-type` / `figure-hash`）。
- 图片完整性：与 `figures/_manifest.json` 比对，分带文件、(a)(b) 拆分、截断图注分别报 `figure-band` / `figure-panel-label` / `figure-split` / `figure-caption-truncated`；`label` 与 `caption` 图号不一致给 `figure-label-mismatch` 警告。

## 写作约定

- 全部字符串使用 UTF-8，不加 BOM；`build.py` 也接受 BOM。
- 数组字段即使只有一项也用数组。
- 不要塞入 HTML 标签；页面会转义。需要强调时在注释里用中文标点组织，不要用 `<b>`。
- 数学符号原样保留（`α`、`ℝ`、`O(n²)`），不要转成 `alpha` 之类的拼写。

## 用 autofill 填回 en

`en` 是整份数据里最大的一块重复输出（示例里占全部自撰字符的 64%）。写的时候全部用占位符，最后一次性填回：

```powershell
python "<skill_dir>/scripts/autofill.py" --source "<dir>/source.txt" --list   # 打印 source.txt 的段落清单（不用 data.json）
python "<skill_dir>/scripts/autofill.py" --data "<dir>/data.json" --source "<dir>/source.txt"          # 把 "@@7" 换成第 7 块的逐字原文
```

- 段号是 `source.txt` **按空行切出来的块序号**（1 起），与 `check.py` 的切法完全一致；标题、作者、参考文献这些块也有编号，只是不会被引用。
- 占位符必须整格匹配 `@@数字`；已经写了真实原文的段落会被跳过，所以可以边写边填。
- 段号越界、两段抢同一个段号、`en` 留空，都会整批拒绝并打印原因，不会写出半成品。
- 填完仍要跑 `check.py`：逐字是否命中以它为准。
