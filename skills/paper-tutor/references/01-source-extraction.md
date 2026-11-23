# 来源提取与段落重建

一切校验都以 `source.txt` 为基准，所以这一步的产出质量决定后面所有环节。宁可多花十分钟核对，也不要带着错误的段落边界往下走。

## 支持的来源

| 来源 | 命令 | 备注 |
|---|---|---|
| 纯文本 / Markdown | `python "<skill_dir>/scripts/extract.py" paper.md -o out/source.txt` | 最可靠；空行即段落 |
| HTML（已下载） | `python "<skill_dir>/scripts/extract.py" paper.html -o out/source.txt` | 用 lxml 取 `<article>/<main>` 下的 `p/li/h1-h3/figcaption/blockquote` |
| 网页 URL | 先下载再提取：`python "<skill_dir>/scripts/extract.py" --url "https://arxiv.org/abs/2401.00001" -o out/source.txt` | 需要网络；arXiv 的 abs 页只有摘要，正文要取 HTML 全文页 |
| Word | `python "<skill_dir>/scripts/extract.py" paper.docx -o out/source.txt` | 依赖 `python-docx` |
| PDF | `python "<skill_dir>/scripts/extract.py" paper.pdf -o out/source.txt` | 依赖 `pypdf` 或 `pdftotext`；没有就按下面的降级处理 |

## HTML 提取要点

1. 优先区域：`article`、`main`、`[role=main]`、`.article-body`、`#article-body`、`.ltx_page_main`（LaTeXML）。
2. 明确删除：`nav`、`aside`、`footer`、`header`、`.references-tools`、`.citations`、`script`、`style`、表单、分享按钮。
3. 段落顺序按 DOM 顺序；`h1–h4` 作为章节标题行单独成行，与正文之间空一行。
4. 图表标题常在 `figcaption` / `.caption` 里，保留并标注（提取器会写成 `Figure N: ...` 一行）。
5. 数学若为 MathML，取 `alttext` 或文本内容；若为 `img` 公式，标注 `[公式图片：需人工誊录]` —— 这类段落必须在 `meta.source_note` 中声明。

## PDF 提取的现实

双栏论文按视觉顺序排版，文本层顺序常常错乱；跨栏、跨页的段落会被切断；连字符断词、脚注混入正文、页眉页码插入句中都可能出现。因此：

1. 只有在**单栏、带文本层**的情况下直接采信自动提取结果。
2. 双栏论文：提取后必须逐段对照 PDF 页面核对，尤其是段落开头/结尾和公式附近。
3. 没有文本层（扫描件、纯图 PDF）：**不自动转写**。请用户提供 HTML 版或文本；用户坚持时按下面的"誊录规则"处理。
4. 提取失败时给出的诊断信息要具体：是库缺失、是加密、还是零文本层。

### 誊录规则（仅在用户坚持时）

- 逐页看图誊录，一段一段核对，不做任何拼写"修正"。
- 在 `data.json` 的 `meta.source_note` 写明："原文为人工誊录，未经自动校验"，并把 `check.py` 的 `--allow-transcribed` 打开。
- 公式、上下标、希腊字母必须核对；不确定的符号在注释里标"存疑"，不要猜。

## 段落重建规则

`extract.py` 按以下顺序处理，人工核对时按同样规则检查：

1. **空行分界**：连续空行 = 段落边界。
2. **行内断词**：行尾 `-` 且下一行以小写字母开头 → 合并为同一词（`atten- tion` → `attention`）。行尾无连字符而句子未结束 → 用空格连接。
3. **丢弃页眉页脚**：整行匹配 `^\s*\d{1,3}\s*$`（纯页码）、`^Page \d+`、期刊名 + 卷期页、DOI 水印行。
4. **保留章节标题**：`^(\d+(\.\d+)*)\s+\S` 或全大写短行 → 作为标题行，单独成行。
5. **不合并相邻段**：两段之间只要有一个空行就分开；不要因为上段末尾没有句号就合并。
6. **公式块**：整行以 `$`、`\[`、`\begin{` 开始或明显是独立编号公式 → 单独成段。

## 提取后的自检清单

- [ ] 段落数与该节目测段数一致（误差应为 0）。
- [ ] 第一段与最后一段完整（最容易丢首行和尾行）。
- [ ] 每个章节标题都出现，且顺序正确。
- [ ] 引用编号（`[12]`、`(Smith et al., 2020)`）没有被吃掉或错位。
- [ ] 数字、百分比、单位与原文一致。
- [ ] 没有残留 `Figure 1` 之类的交叉引用被替换成空。
- [ ] 页码、页眉、水印已清除。
- [ ] `meta.source_note` 写清来源、版本（arXiv v1/v2）、是否节选、是否有誊录部分。

## 常见故障

| 现象 | 原因 | 处理 |
|---|---|---|
| 全文只有 1 段 | HTML 只有一个大 `div`，或被错误地取了 `<body>` 全文 | 手工按空行重建；或指定选择器 |
| 段落顺序错乱 | 双栏 PDF | 对照页面重排，或改用 HTML 版 |
| 公式变成乱码 | 文本层缺字形（`fi`、`α` 丢失） | 从原文截图誊录该公式，并在注释中标明 |
| 参考文献混入正文 | HTML 提取区域过大 | 删除 `references` 区块，并在 `source_note` 说明 |
| 大量重复段落 | 页面有"引用预览"重复块 | 按文本去重，只保留首次出现 |
