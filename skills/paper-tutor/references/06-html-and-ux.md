# 页面与交互：`3_精读阅读页.html` 是怎么长出来的

`build.py` 把 `data.json` 渲染成一页 HTML，再把 `templates/page/reading.css` 与 `templates/page/reading.js` **整段内联**进去。产物是一个独立文件：没有外链、没有网络请求、没有字体下载，`file://` 双击能开，断网能看，发邮件能发。这不是风格偏好，是硬约束——用户常常在离线环境或公司内网里读论文。

改内容只改 `data.json`，然后重新构建。手改 HTML 会在下次构建时被覆盖，而且会绕过 `check.py` 的闸门。

## 一、布局：左侧上下、右侧注释

每段一张卡片，卡片内两列：

```
┌───────────────────────────────┬──────────────────────┐
│ 英文原文（逐字，serif，两端对齐）│                      │
│                               │   分析注释            │
├───────────────────────────────┤   这一段在讲什么      │
│ 中文翻译（逐句，无衬线，1.95 行高）│   承担什么作用        │
│                               │   在论证结构中的位置  │
└───────────────────────────────┴──────────────────────┘
```

- 左列 `grid-template-rows: auto 1fr`：原文按内容自然高度，译文吃掉剩余高度，两张面板底边对齐，中间不留空档。
- 右列注释与整个卡片等高，读原文时注释一直在视野里，不需要来回滚动。
- 三块面板靠**位置**对齐（同一张卡片 = 同一段），不靠超链接或悬停联动——这是"三对齐"的实现方式，也是长段落里最不容易迷失的做法。

## 二、DOM 骨架

```html
<a class="skip" href="#paper-start">跳到正文</a>
<header class="topbar">
  <div class="brand">精读 / 论文精读</div>
  <div class="titles"> 中文标题 / 英文标题 </div>
  <div class="tools">
    <div class="stepper">↑ <b data-cur>1</b><i>/</i><span data-total>12</span> ↓</div>
    <div class="toggles">原文 翻译 注释（三个复选框）</div>
    <div class="buttons">A− A+ 主题</div>
    <div class="wider">⇔（内容宽度面板：滑块 + 紧凑/标准/宽/更宽/满宽）</div>
    <div class="search"><input data-search> <span data-search-count></span></div>
    <button class="menu-btn" data-act="menu">☰</button>   <!-- 窄屏才显示 -->
  </div>
</header>
<div class="progress"><span class="progress-bar" data-progress></span></div>

<div class="layout">
  <aside class="side" data-side>
    <div class="side-title">目录</div>
    <nav class="toc">
      <div class="toc-sec">
        <a class="toc-h" href="#sec-s1">1 引言</a>
        <a class="toc-p" href="#p2"><span class="tn">2</span><span class="tt">研究缺口</span></a>
      </div>
    </nav>
  </aside>

  <main class="main" data-main>
    <section class="masthead">
      <p class="kicker">逐段精读 · 原文 / 翻译 / 注释</p>
      <h1 class="h1-zh">…</h1><p class="h1-en">…</p>
      <p class="byline">作者 · 期刊 · 年份</p>
      <p class="oneliner">一句话主张</p>
      <ul class="stats">12 段 / 889 英文词 / 1421 译文字</ul>
      <p class="src-note">原文来源：…</p>
    </section>

    <section class="map-wrap">
      <h2 class="map-h">论证结构总览</h2>
      <ol class="map">
        <li class="map-item">
          <div class="map-top"><span class="map-no">1</span><span class="map-stage">摘要</span></div>
          <div class="map-refs"><a class="ref" href="#p1">P1</a></div>
          <p class="map-note">题干</p>
        </li>
      </ol>
      <p class="map-tip">点击 P 编号跳到对应段落…</p>
    </section>

    <section class="sec" id="sec-s1">
      <h2 class="sec-h"><span class="sec-zh">1 引言</span><span class="sec-en">1 Introduction</span></h2>
      <article class="para" id="p2" data-id="p2">
        <header class="para-head">
          <span class="pnum">2</span>
          <span class="chip kind">正文</span>
          <span class="chip label">研究缺口</span>
          <a class="anchor" href="#p2">#</a>
        </header>
        <div class="cols">
          <div class="col-left has-fig">
            <div class="para-figs" aria-label="论文原图">
              <figure class="fig" data-fig="p7-1">
                <a class="fig-zoom" href="#p7" data-zoom data-name="figures/fig3.png" data-label="Figure 3">
                  <img src="data:image/png;base64,…" alt="…" data-sha256="…" data-name="figures/fig3.png" loading="lazy" decoding="async">
                </a>
                <figcaption>
                  <span class="fig-label">Figure 3</span>
                  <span class="fig-cap">图注…</span>
                  <button type="button" class="fig-raw" data-download data-name="figures/fig3.png">原图</button>
                </figcaption>
              </figure>
            </div>
            <section class="pane pane-en" lang="en"><h3 class="pane-t">英文原文</h3>…</section>
            <section class="pane pane-zh" lang="zh-CN"><h3 class="pane-t">中文翻译</h3>…</section>
          </div>
          <section class="pane pane-note" lang="zh-CN">
            <h3 class="pane-t">分析注释</h3>
            <div class="note-block"><h4>这一段在讲什么</h4><p>…</p></div>
            <div class="note-block"><h4>承担什么作用</h4><p>…</p></div>
            <div class="note-block"><h4>在论证结构中的位置</h4><p>…</p></div>
            <div class="note-block terms"><h4>关键术语</h4><ul class="term-list">…</ul></div>
            <div class="note-block questions"><h4>继续追问</h4><ol>…</ol></div>
            <div class="note-block caveat"><h4>存疑 / 待核</h4><p>…</p></div>
          </section>
        </div>
      </article>
    </section>
  </main>
</div>
<footer class="page-foot">…生成说明…</footer>
<button class="to-top" data-act="top">↑</button>
```

`terms`、`questions`、`caveat` 三个块只在对应字段存在时输出，缺字段不会留空壳。`para-figs` 只在段落有 `figures` 时输出，此时 `.col-left` 加 `has-fig`，左列由两行变三行（图 / 原文 / 译文），段落头部多一个 `N 图` chip。

## 二点五、图片区与灯箱

图片是**原文件的字节**，页面只负责摆放：

| 环节 | 做法 |
|---|---|
| 摆位 | `.para-figs` 在 `.col-left` 顶部、原文之上；宽度跟左列，`img { width:100%; height:auto }` 只是 CSS 等比缩放，文件不变 |
| 图注 | `figcaption` 一行：图号（粗体）+ `caption` + 右侧 `原图` 按钮；无图注时只显示图号 |
| 放大 | 点图开灯箱：`适应窗口` / `1:1` / `下载原图` / `关闭(Esc)`；标题栏显示 `图号 · sha256 前 12 位 · 宽×高 px · 原始字节，未做任何处理` |
| 下载 | `data:` URI 走 `fetch → blob → <a download>`，拿到的是与原文件逐字节相同的副本 |
| 深色 | 只换容器底色（`--fig-bg`），图片本身不滤镜、不反色 |
| 打印 | 图跟随卡片、`break-inside: avoid`；`原图` 按钮与灯箱不打印 |

灯箱打开时左右方向键不再翻段，`Esc` 先关灯箱再退出检索（见"交互清单"）。

## 三、正文的三种排法

| `kind` | 排法 | 说明 |
|---|---|---|
| `body`、`abstract`、`caption`、`footnote`、`quote`、`reference` | 按空行拆成若干 `<p class="txt">`，空白归一 | 与原文段落外观一致 |
| `equation` | `<div class="txt pre">`，保留换行与缩进 | 公式行不能被折叠，否则上下标和换行语义会丢 |

`preserve_breaks: true` 对任意 `kind` 都生效，用于原文本身靠换行表达结构的地方（多行公式、代码块、诗歌体引文）。

## 三点五、内容宽度（可调）

正文栏宽度由 CSS 变量 `--content-w` 统一控制：`.masthead`、`.map-wrap`、`.sec`、`.page-foot` 都是 `max-width: var(--content-w, 1120px)`。改这一个变量，标题区、论证地图、段落卡片、页脚同时变宽，卡片内部左右两列（原文译文 / 注释）按比例跟着变宽，所以"块与块之间"的宽度始终一致。

| 项 | 规则 |
|---|---|
| 默认值 | `1120px`（`:root` 里声明，与早期固定版式一致；宽屏显示器上偏窄，可现场调） |
| 可调范围 | 860–2200px，步长 20px；另有"满宽"= `--content-w: none`（吃满正文区，无上限） |
| 入口 | 工具栏 `⇔` 按钮弹出小面板：滑块 + 当前值 + 五档预设（紧凑 960 / 标准 1120 / 宽 1360 / 更宽 1600 / 满宽） |
| 快捷键 | `[` 收窄一档、`]` 加宽一档；`Esc` 关面板 |
| 关闭面板 | 点面板外任意处 / 再点 `⇔` / `Esc` |
| 持久化 | 拖动滑块时只应用不落盘，松手（`change`）或点预设才写入 `pcr.width`；下次打开自动恢复 |
| 打印 | 打印时强制 `max-width: none`，不受当前设置影响 |

加宽只作用于内容栏；左侧目录固定 268px 不变，所以正文实际可用宽度 = 视口 − 268px（< 1180px 时目录变抽屉，即整个视口）。设置值大于可用宽度时自然被视口约束，不会出现横向滚动条。

## 四、响应式与打印

| 宽度 | 行为 |
|---|---|
| ≥ 1180px | 左侧固定目录（268px，独立滚动）+ 右侧正文；卡片两列 |
| < 1180px | 目录变抽屉（`☰` 打开，带遮罩，`Esc` 关闭）；卡片仍两列 |
| < 900px | 目录抽屉继续；卡片单列堆叠：原文 → 译文 → 注释 |
| < 620px | 隐藏副标题、字号/主题按钮与 `⇔` 宽度按钮，搜索框收窄到 96px，把空间留给正文 |

打印（`Ctrl+P`）：强制展开所有段落、隐藏工具栏与抽屉、卡片避免跨页断裂、去掉阴影与背景色以省墨。打印出来是"原文 + 译文 + 注释"的三段式讲义。

## 五、交互清单

| 功能 | 操作 | 说明 |
|---|---|---|
| 上/下段落 | 工具栏 ↑ ↓ | 每次跳一段，计数器与目录高亮同步；到首段再按 ↑、末段再按 ↓ 时停住不动 |
| 键盘导航 | `←` `→`、`j` `k` | 上一段 / 下一段 |
| 首末段 | `Home` `End` | |
| 检索 | 点搜索框或按 `/` | 130ms 防抖，匹配原文、译文、注释全文；计数显示为"命中/总段数"（如 `3/12`，无命中为 `0/12`），并自动跳到第一个命中段 |
| 退出检索 | `Esc` | 清空过滤并还原全部段落 |
| 栏目开关 | 原文 / 翻译 / 注释 复选框 | 只留译文对照读、或只看原文练翻译 |
| 字号 | `A−` `A+` | 13–21px，步长 0.5；只改正文，不改工具栏 |
| 主题 | ◐ 按钮 | 浅色 / 深色；首次访问跟随系统 `prefers-color-scheme` |
| 内容宽度 | ⇔ 按钮 / 滑块 / 五档预设 | 860–2200px 或满宽；改 `--content-w`，标题、地图、卡片、页脚同步变宽；面板打开时点外部或 `Esc` 关闭 |
| 宽度快捷键 | `[` `]` | 每次 20px 收窄 / 加宽，越界自动夹住 |
| 目录跳转 | 点目录项 / 论证地图里的 P 编号 | 平滑滚动到该段并高亮闪烁一次 |
| 深链 | 地址栏 `#p7` | 打开即定位到第 7 段，便于把某段发给别人 |
| 看原图 | 点段落左侧的图 | 开灯箱；`适应窗口` / `1:1`（原始像素，可滚动看细节）/ `下载原图`（逐字节相同）/ `关闭` |
| 关灯箱 | `Esc` 或右上角关闭 | 灯箱打开时方向键不翻段，先关灯箱 |
| 回到顶部 | 右下角 ↑ | 滚动超过约 520px 后出现 |

## 六、状态持久化（localStorage，前缀 `pcr.`）

| 键 | 值 | 作用 |
|---|---|---|
| `pcr.theme` | `light` / `dark` | 主题 |
| `pcr.font` | 数字（默认 15.5） | 字号 |
| `pcr.width` | 数字（默认 1120）或字符串 `none` | 内容栏宽度上限；`none` = 满宽 |
| `pcr.pane.en` / `pcr.pane.zh` / `pcr.pane.note` | `true` / `false` | 栏目显隐 |

用户下次打开同一篇或另一篇精读页时，偏好保留。键名带 `pcr.` 前缀，避免与其他页面冲突。

## 七、降级与可访问性

- **没有 JS 也能读**：所有内容都在 HTML 里，栏目默认全展开，图片照样显示（`img` 是静态标签）；只有导航、检索、主题、灯箱这些增强功能失效。
- **键盘可达**：工具栏按钮都是原生 `button`，`Esc` 关闭抽屉、灯箱与检索，`/` 聚焦搜索（不是 `Ctrl+F`，避免和浏览器冲突）；图片可 Tab 聚焦、回车打开灯箱。
- **语义**：正文用 `lang="en"` / `lang="zh-CN"` 标注，屏幕阅读器会切换语音；段落用 `article + header`，目录用 `nav`。
- **动效**：`prefers-reduced-motion: reduce` 时关闭平滑滚动与闪烁。
- **深色**：所有颜色走 CSS 变量，深色下正文背景、卡片、注释、术语表都各自有对比度足够的底色。

## 八、体积与超长论文

- 12 段约 75 KB（含内联 CSS/JS，约 25 KB 固定开销）。
- 每段增量大致 = 原文 + 译文 + 注释，通常 3–6 KB；100 段约 500 KB，浏览器打开无压力。
- **图片会显著改变体积**：`--figure-mode inline` 下 HTML ≈ 文字体积 + 图片总字节 × 1.34（base64）。两张 2× 分辨率示意图（约 190 KB）把 12 段页面从 75 KB 推到 334 KB；图再多就该换 `--figure-mode link`（同一份数据只 85 KB，图另存 `figures/`）。`build.py` 在内联总量超过 ~12 MB 时提示切换。
- 超过 150 段时不要硬塞一页：按章节拆成多个 HTML，或用 `sections` 分组后分批构建，避免首屏渲染与滚动性能下降（单文件仍是首选，拆分只在实测卡顿时做）。
