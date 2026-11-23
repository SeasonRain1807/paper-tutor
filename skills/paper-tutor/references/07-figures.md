# 论文原图：判断、取材、字节不变

论文的图常常是论证的主战场：趋势、对比、结构图、示意图。读者在逐段精读时最需要的，恰恰是"读这一段时那张图就在旁边"。这份文档管三件事：

1. 哪一段该挂图、挂哪张；
2. 原图从哪里取，怎么取才算"原图"；
3. 取到之后怎么证明没动过。

配套的红线只有一句：**图片以原始字节呈现，不裁剪、不重压缩、不转格式、不叠标注**。

---

## 1. 什么时候必须挂图

看这一段文字是否**在讲图本身**。满足任一条就挂：

- 显式引用：`Figure 3 shows…`、`as Fig. 2 indicates`、`the dashed curve in Figure 4`、`Table 2` 之外的图引用（表格走 `caption` 段，不挂图）。
- 在解释图的构成：描述坐标轴、图例、分栏、颜色编码、实验组与对照组的排布。
- 在从图里读结论：`accuracy rises steeply beyond 32k tokens`、`the gap widens with depth`——这些数字来自图，读者不看到图就无法核对。
- 图是方法的一部分：网络结构图、流程图、装置示意图、试剂合成路线。

不挂的情况：

- 只在文献综述里提一句"先前工作报告了类似的趋势"，没有具体到某张图。
- 图注本身：图注按 `kind: "caption"` 单独成段，图与图注不重复搬两遍。
- 同一张图被连续多段讨论：挂到**第一次详细展开**它的那段，其余段在注释里写"见 P7 的 Figure 3"。同一张图重复出现五次只会把页面撑长。

一张图挂在哪段，由"读者读到这段时需要看到它"决定，不由"图出现在 PDF 的哪一页"决定。

---

## 2. 原图从哪里取

优先级从高到低：**论文自带的图片文件 > 网页里的图片资源 > 文档内嵌媒体 > PDF 内嵌位图**。截图永远排最后，且不能算"原图"。

### 2.1 用户直接给了图片

最省事。原样复制进 `figures/`，**保留原文件名**（`fig3_scaling.png` 比 `figure3.png` 更能自证来源），不要用看图软件"另存为"——那一步往往就重编码了。

```powershell
New-Item -ItemType Directory -Force "<论文短名>/figures"
Copy-Item "<用户给的图>" "<论文短名>/figures/"
```

### 2.2 arXiv / 出版社 HTML

网页里的 `<img>` 通常指向上传的原图（arXiv 的 `https://arxiv.org/html/2401.00001v2/x3.png` 这类）。要点：

- 取 `src` 指向的文件本身，不要取缩略图（带 `_thumb`、`-small`、`width=` 的往往是降采样版）。
- 有些站点用 `<picture>` + `srcset` 给多档分辨率：取 `srcset` 里最大的一档。
- 图在 `<figure>` 里时，`<figcaption>` 就是图注，抄进 `figures[].caption`。
- 取不到（防盗链、需要登录）就退到下一个来源，不要拿网页截图充数。

### 2.3 Word / `.docx`

`.docx` 是 zip，图片在 `word/media/` 里，文件名通常是 `image1.png`、`image2.emf`：

```powershell
Copy-Item "<稿件>.docx" "$env:TEMP\paper.zip" -Force
Expand-Archive "$env:TEMP\paper.zip" -DestinationPath "$env:TEMP\paper_docx" -Force
Get-ChildItem "$env:TEMP\paper_docx\word\media"
```

按正文里图的出现顺序对应 `image1`、`image2`…；顺序对不上时用 `document.xml` 里 `<a:blip r:embed="rIdN">` 的先后关系核对 `word/_rels/document.xml.rels`。`.emf`/`.wmf` 是矢量格式，浏览器不一定能显示，见第 4 节。

### 2.4 PDF

PDF 里的图是嵌在位图或矢量对象里的，本机没有可靠的位图导出工具（见 `references/01-source-extraction.md` 的工具现状）。两条路：

- `pypdf` 能列出页面上的图片对象并导出（`page.images`），导出的是 PDF 内嵌的原始位图，可用；但矢量图（大多数折线图、示意图）导不出来。
- 导不出来时，**不要用截图冒充原图**：该段不挂 `figures`，在 `analysis.caveat` 写"图 X 未能取到原图，需对照原文查看"，并在交付说明里点出来。

### 2.5 只有扫描件 / 截图

同 2.4 的最后一条：不挂，写进 `caveat`。若用户明确提供了自己截的图并说"就用这个"，可以挂，但要在 `figures[].source` 里写明"用户提供的截图（非出版方原图）"，并在页面上保留这句说明——读者有权知道自己在看什么。

---

## 3. 登记与哈希

图放进 `figures/` 之后，在对应段落的 `figures` 数组里登记：

```json
"figures": [
  {
    "path": "figures/fig3_scaling.png",
    "label": "Figure 3",
    "caption": "Scaling behavior of the three sparse patterns.",
    "alt": "三条曲线随序列长度增长的准确率变化，结构化稀疏在高长度处最高。",
    "source": "论文 Figure 3，取自 arXiv HTML 原图"
  }
]
```

然后记录字节指纹：

```powershell
python "<skill_dir>/scripts/check.py" "<论文短名>/data.json" --source "<论文短名>/source.txt" --write-figure-hashes
```

输出 `已把 N 张图的 sha256 / 字节数写回 …`。此后每次 `check.py` 都会重新计算并比对：对不上就是 `figure-hash` 错误，页面也不该交付。

`--write-figure-hashes` 只在两种情况用：**首次登记**，或**用户明确要求换图**（换了才算新基准）。平时不要跑，否则"改动被悄悄接受"，哈希就失去了证明力。

---

## 4. 什么算"改了图"

下面这些都算，都会被 `figure-hash` 抓住：

| 操作 | 为什么算改动 |
|---|---|
| 用画图工具加箭头、红框、"重点在这里" | 叠加了原始文件里没有的像素 |
| 裁剪掉空白边 | 尺寸变了，像素集合变了 |
| 另存为 JPEG / 降到 8-bit / 缩放 | 重编码，像素值发生变化 |
| 用 OCR 或矢量化工具"重绘"成清晰版 | 完全另一张图 |
| 加水印、加页码 | 同上 |

**不算**改动的做法（页面层实现，文件不动）：

- 页面上按容器宽度等比缩放显示——CSS 缩放不碰文件；
- 点击放大到 1:1 看细节；
- 深色模式下给图片容器加底色（图本身的像素没变）；
- 下载原图（页面把原始字节还给用户）。

`.emf` / `.wmf` 这类浏览器显示不了的矢量格式，正确做法是**不放进页面**（或放原文件但不显示，标注"需用 Word/Visio 打开"），而不是转成 PNG 顶替原图；确实需要可视图时，把转换件另存为 `figures/fig3_scaling.view.png`，在 `figures[].note` 里说明"`.view.png` 是为显示生成的转换件，原图为 `fig3_scaling.emf`"。

---

## 5. 页面上的表现

- 图固定在该段卡片**左栏顶部**，原文之上。读者从上往下读就是"图 → 原文 → 译文"，右侧注释与图并排。
- 段落头部出现 `N 图` 标签，方便扫读时定位有图的段。
- 点图开灯箱：`适应窗口` / `1:1` / `下载原图` / `关闭(Esc)`。灯箱标题栏显示 `图号 · sha256 前 12 位 · 宽×高 · 原始字节，未做任何处理`——这行字是给读者的凭据，也提醒后续维护者别去改图。
- 灯箱打开时，键盘左右键不再翻段；`Esc` 先关灯箱。
- 打印时图片跟随卡片、不跨页断裂，`原图` 按钮与灯箱不打印。

### 体积

默认 `--figure-mode inline`：图片字节以 base64 内联，`3_精读阅读页.html` 仍是**单文件**，双击就能开，发给别人不会丢图。代价是体积约等于图片总和的 1.34 倍。

- 经验阈值：内联总量超过 ~12 MB 时 `build.py` 会提示改用 `--figure-mode link`。
- `--figure-mode link`：把原图**逐字节复制**到输出目录的 `figures/`，页面用相对路径引用。HTML 只有几十 KB，但交付时 `3_精读阅读页.html` 与 `figures/` 必须一起移动；复制后脚本会再比对一次字节，确保复制过程没出岔子。
- 两种模式都不改图片内容，只是"装进去"还是"放在旁边"。

---

## 6. 校验与修复

| finding | 含义 | 怎么修 |
|---|---|---|
| `figure-missing` | `path` 指向的文件不存在 | 把原图放到 `figures/` 下，或改成正确相对路径 |
| `figure-type` | 文件内容不是可识别的图片 | 检查是不是下成了 HTML 错误页、或扩展名写错 |
| `figure-hash` | 字节与记录不一致 | 从原始来源**重新取一份**原图覆盖；确属有意换图时，才重跑 `--write-figure-hashes` |
| `figure-unrecorded` | 还没有哈希记录 | 跑一次 `--write-figure-hashes` |
| `figure-unlabeled` | 既无 `label` 也无 `caption` | 补 `label: "Figure 3"` 或一句 `caption` |
| `figure-outside` | 图在 `data.json` 目录之外 | 复制进 `figures/`，避免交付时丢图 |
| `figure-unused` | `figures/` 里有没被引用的图 | 挂到对应段落，或删除，免得交付一堆无用文件 |

`check.py` 的总体输出里有一行 `图片：N/M 张已按记录字节核验（sha256）`。`N < M` 说明有图没通过核验，别只看"0 error"就交付——先确认每一张都记过哈希。

---

## 7. 交付前清单

- [ ] 每张被正文讲到的图都挂到了正确段落（不是页数最近的那段）
- [ ] `figures/` 里没有未引用的图片，`path` 都在 `data.json` 目录内
- [ ] `check.py` 输出 `图片：M/M`，且 0 error
- [ ] `--figure-mode link` 构建时，`figures/` 与 HTML 一起交付，并在说明里点明
- [ ] 取不到原图的图，已写进 `analysis.caveat` 并在交付说明里列出
- [ ] 没有为了"好看"动过任何一张图
