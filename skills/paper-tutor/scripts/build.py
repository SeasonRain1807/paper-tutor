#!/usr/bin/env python3
"""Build 3_精读阅读页.html — a single-file, offline close-reading page — from data.json.

Usage:
    python build.py --data data.json --out 3_精读阅读页.html
    python build.py --data data.json --out 3_精读阅读页.html --title "自定义标题"

The output inlines templates/page/reading.css and templates/page/reading.js, references no
network resource, and works by double-clicking the file.
"""

from __future__ import annotations

import argparse
import base64
import html
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parent.parent
ASSETS = SKILL_DIR / "templates" / "page"

CSS_MARKER = "{{READING_CSS}}"
JS_MARKER = "{{READING_JS}}"


def esc(value: str) -> str:
    return html.escape(value, quote=True)


def text_html(value: str, preserve: bool = False) -> str:
    """Render original/translated text. Never rewrites wording."""
    if preserve:
        return f'<div class="txt pre">{esc(value)}</div>'
    chunks = [chunk for chunk in common.WS_RE.split(value) if chunk]
    if not chunks:
        return ""
    # Keep author paragraph breaks when the excerpt itself contains blank lines.
    parts = [part.strip() for part in value.split("\n\n") if part.strip()]
    if len(parts) > 1:
        return "\n".join(f'<p class="txt">{esc(common.norm_ws(part))}</p>' for part in parts)
    return f'<p class="txt">{esc(common.norm_ws(value))}</p>'


def render_terms(terms) -> str:
    if not terms:
        return ""
    items = []
    for term in terms:
        if not isinstance(term, dict):
            continue
        extra = ""
        if common.non_empty(term.get("note")):
            extra = f'<span class="t-note">{esc(term["note"])}</span>'
        items.append(
            '<li><span class="t-en">'
            + esc(term.get("en", ""))
            + '</span><span class="t-zh">'
            + esc(term.get("zh", ""))
            + "</span>"
            + extra
            + "</li>"
        )
    if not items:
        return ""
    return (
        '<div class="note-block terms"><h4>关键术语</h4><ul class="term-list">'
        + "".join(items)
        + "</ul></div>"
    )


def render_questions(questions) -> str:
    items = [esc(q) for q in (questions or []) if common.non_empty(q)]
    if not items:
        return ""
    return (
        '<div class="note-block questions"><h4>继续追问</h4><ol>'
        + "".join(f"<li>{item}</li>" for item in items)
        + "</ol></div>"
    )


def render_caveat(caveat) -> str:
    if not common.non_empty(caveat):
        return ""
    return f'<div class="note-block caveat"><h4>存疑 / 待核</h4><p>{esc(caveat)}</p></div>'


def figure_source(fig: dict, ctx: dict, pid: str, no: int) -> tuple[str, str]:
    """Return (src, sha256) for one figure.

    The image bytes are never decoded, resized, cropped or re-compressed:
    `inline` mode base64-encodes the file as-is, `link` mode copies the file
    byte for byte. Either way the page shows the original pixels.
    """
    base = ctx.get("base") or Path(".")
    mode = ctx.get("mode", "inline")
    raw_path = Path(fig["path"])
    path = raw_path if raw_path.is_absolute() else (base / raw_path)

    if not path.is_file():
        raise common.DataError(f"{pid} 的图片不存在：{path}")

    raw = path.read_bytes()
    sha = common.sha256_bytes(raw)
    recorded = str(fig.get("sha256") or "")
    if recorded and recorded != sha:
        print(
            f"警告：{pid} 的图片 {path.name} 与 data.json 记录的 sha256 不一致，"
            "说明文件已被改动（要求：不得更改图片任何信息）",
            file=sys.stderr,
        )
    if not raw:
        raise common.DataError(f"{pid} 的图片是空文件：{path}")

    if mode == "link":
        out_dir = (ctx.get("out_dir") or base) / "figures"
        out_dir.mkdir(parents=True, exist_ok=True)
        name = path.name
        target = out_dir / name
        if target.exists() and common.sha256_file(target) != sha:
            name = f"{path.stem}-{sha[:8]}{path.suffix}"
            target = out_dir / name
        if not target.exists():
            shutil.copyfile(path, target)
        if target.exists() and common.sha256_file(target) != sha:
            raise common.DataError(f"{pid} 的图片复制后字节不一致：{target}")
        ctx.setdefault("copied", []).append(target)
        return f"figures/{name}", sha

    mime = common.sniff_image_mime(raw, path)
    encoded = base64.b64encode(raw).decode("ascii")
    ctx["inline_bytes"] = ctx.get("inline_bytes", 0) + len(raw)
    return f"data:{mime};base64,{encoded}", sha


def render_figures(para: dict, ctx: dict) -> str:
    figures = common.figures_of(para)
    if not figures:
        return ""
    pid = para["id"]
    items = []
    for no, fig in enumerate(figures, 1):
        src, sha = figure_source(fig, ctx, pid, no)
        label = common.norm_ws(str(fig.get("label") or f"图 {no}"))
        caption = common.norm_ws(str(fig.get("caption") or ""))
        alt = common.norm_ws(str(fig.get("alt") or caption or label))
        name = Path(fig["path"]).name
        cap_html = ""
        if caption:
            cap_html = f'<span class="fig-cap">{esc(caption)}</span>'
        items.append(
            f"""              <figure class="fig" data-fig="{pid}-{no}">
                <a class="fig-zoom" href="#{pid}" data-zoom data-name="{esc(name)}" data-label="{esc(label)}" title="查看原图（字节不变）">
                  <img src="{esc(src)}" alt="{esc(alt)}" data-sha256="{sha}" data-name="{esc(name)}" loading="lazy" decoding="async" referrerpolicy="no-referrer">
                </a>
                <figcaption>
                  <span class="fig-label">{esc(label)}</span>
                  {cap_html}
                  <button type="button" class="fig-raw" data-download data-name="{esc(name)}" title="下载原图文件（未做任何处理）">原图</button>
                </figcaption>
              </figure>"""
        )
    return (
        '<div class="para-figs" aria-label="论文原图">\n'
        + "\n".join(items)
        + "\n            </div>"
    )


def render_para(para: dict, index: int, ctx: dict | None = None) -> str:
    pid = para["id"]
    kind = para.get("kind", "body")
    analysis = para["analysis"]
    label = para.get("label")
    kind_label = common.KIND_LABEL.get(kind, kind)
    chips = [f'<span class="chip kind">{kind_label}</span>']
    if common.non_empty(label) and common.norm_ws(label) != kind_label:
        chips.append(f'<span class="chip label">{esc(label)}</span>')
    fig_html = render_figures(para, ctx or {})
    if fig_html:
        chips.append(f'<span class="chip fig-chip">{len(common.figures_of(para))} 图</span>')
    left_class = "col-left has-fig" if fig_html else "col-left"

    note_parts = [
        f'<div class="note-block"><h4>这一段在讲什么</h4><p>{esc(common.norm_ws(analysis["summary"]))}</p></div>',
        f'<div class="note-block"><h4>承担什么作用</h4><p>{esc(common.norm_ws(analysis["function"]))}</p></div>',
        f'<div class="note-block"><h4>在论证结构中的位置</h4><p>{esc(common.norm_ws(analysis["position"]))}</p></div>',
        render_terms(analysis.get("terms")),
        render_questions(analysis.get("questions")),
        render_caveat(analysis.get("caveat")),
    ]
    note_html = "\n".join(part for part in note_parts if part)

    return f"""      <article class="para" id="{pid}" data-id="{pid}">
        <header class="para-head">
          <span class="pnum">{index}</span>
          {''.join(chips)}
          <a class="anchor" href="#{pid}" title="本段永久链接">#</a>
        </header>
        <div class="cols">
          <div class="{left_class}">
            {fig_html}
            <section class="pane pane-en" lang="en">
              <h3 class="pane-t">英文原文</h3>
              {text_html(para["en"], bool(para.get("preserve_breaks")))}
            </section>
            <section class="pane pane-zh" lang="zh-CN">
              <h3 class="pane-t">中文翻译</h3>
              {text_html(para["zh"], False)}
            </section>
          </div>
          <section class="pane pane-note" lang="zh-CN">
            <h3 class="pane-t">分析注释</h3>
            {note_html}
          </section>
        </div>
      </article>"""


def render_toc(data: dict) -> str:
    by_section: dict[str, list[dict]] = {}
    for para in data["paragraphs"]:
        by_section.setdefault(para["section"], []).append(para)
    blocks = []
    for section in data["sections"]:
        paras = by_section.get(section["id"], [])
        if not paras:
            continue
        links = []
        for para in paras:
            label = para.get("label") or common.display_width(para["zh"])[:18]
            links.append(
                f'<a class="toc-p" href="#{para["id"]}" data-target="{para["id"]}">'
                f'<span class="tn">{para["id"][1:]}</span><span class="tt">{esc(label)}</span></a>'
            )
        blocks.append(
            f"""        <div class="toc-sec">
          <a class="toc-h" href="#sec-{section['id']}">{esc(section['title_zh'])}</a>
          {''.join(links)}
        </div>"""
        )
    return "\n".join(blocks)


def render_argument_map(meta: dict) -> str:
    stages = []
    for no, stage in enumerate(meta.get("argument_map") or [], 1):
        refs = common.parse_para_refs(stage.get("paras", ""))
        chips = "".join(
            f'<a class="ref" href="#{ref}">{ref.upper()}</a>' for ref in dict.fromkeys(refs)
        ) or f'<span class="ref plain">{esc(stage.get("paras", ""))}</span>'
        note = ""
        if common.non_empty(stage.get("note")):
            note = f'<p class="map-note">{esc(common.norm_ws(stage["note"]))}</p>'
        stages.append(
            f"""      <li class="map-item">
        <div class="map-top"><span class="map-no">{no}</span><span class="map-stage">{esc(stage.get("stage", ""))}</span></div>
        <div class="map-refs">{chips}</div>
        {note}
      </li>"""
        )
    return "\n".join(stages)


def build_html(data: dict, css: str, js: str, subtitle: str, ctx: dict | None = None) -> str:
    meta = data["meta"]
    paragraphs = data["paragraphs"]
    en_words = sum(common.en_word_count(para["en"]) for para in paragraphs)
    zh_chars = sum(common.cjk_count(para["zh"]) for para in paragraphs)
    fig_count = common.count_figures(data)
    ctx = ctx or {}

    by_section: dict[str, list[dict]] = {}
    for para in paragraphs:
        by_section.setdefault(para["section"], []).append(para)

    index_of = {para["id"]: number for number, para in enumerate(paragraphs, 1)}
    sections_html = []
    for section in data["sections"]:
        paras = by_section.get(section["id"], [])
        if not paras:
            continue
        cards = "\n".join(
            render_para(para, index_of[para["id"]], ctx) for para in paras
        )
        sections_html.append(
            f"""    <section class="sec" id="sec-{section['id']}">
      <h2 class="sec-h"><span class="sec-zh">{esc(section['title_zh'])}</span><span class="sec-en">{esc(section['title_en'])}</span></h2>
{cards}
    </section>"""
        )

    authors = meta.get("authors", "")
    if isinstance(authors, (list, tuple)):
        authors = "、".join(common.norm_ws(str(a)) for a in authors if common.non_empty(str(a)))
    else:
        authors = common.norm_ws(str(authors or ""))
    meta_bits = [
        authors,
        common.norm_ws(str(meta.get("venue", "") or "")),
        common.norm_ws(str(meta.get("year", "") or "")),
    ]
    meta_line = " · ".join(bit for bit in meta_bits if bit)
    link = ""
    if common.non_empty(meta.get("doi_or_url")):
        url = meta["doi_or_url"].strip()
        href = url if url.startswith(("http://", "https://")) else f"https://doi.org/{url.lstrip('doi:').strip()}"
        link = f'<a class="src-link" href="{esc(href)}" target="_blank" rel="noopener">{esc(url)}</a>'

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    title_zh = html.escape(meta["title_zh"])
    title_en = html.escape(meta["title_en"])
    fig_stat = f"<li><b>{fig_count}</b> 图</li>" if fig_count else ""
    fig_foot = (
        "<p>图中为论文原图，按原始字节呈现：未裁剪、未重压缩、未叠加任何标注。</p>"
        if fig_count
        else ""
    )
    side_fig = f" · {fig_count} 图" if fig_count else ""

    return f"""<!DOCTYPE html>
<html lang="zh-CN" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="paper-tutor">
<title>精读 · {title_zh}</title>
<style>
{css}
</style>
</head>
<body>
<a class="skip" href="#paper-start">跳到正文</a>
<header class="topbar">
  <div class="topbar-main">
    <div class="brand"><span class="brand-mark">精读</span><span class="brand-sub">{esc(subtitle)}</span></div>
    <div class="titles">
      <div class="t-zh">{title_zh}</div>
      <div class="t-en" lang="en">{title_en}</div>
    </div>
    <div class="tools">
      <div class="stepper" role="group" aria-label="段落导航">
        <button type="button" data-act="prev" aria-label="上一段（←）" title="上一段（←）">↑</button>
        <span class="counter" aria-live="polite"><b data-cur>1</b><i>/</i><span data-total>{len(paragraphs)}</span></span>
        <button type="button" data-act="next" aria-label="下一段（→）" title="下一段（→）">↓</button>
      </div>
      <div class="toggles" role="group" aria-label="显示栏目">
        <label class="tgl"><input type="checkbox" data-pane="en" checked><span>原文</span></label>
        <label class="tgl"><input type="checkbox" data-pane="zh" checked><span>翻译</span></label>
        <label class="tgl"><input type="checkbox" data-pane="note" checked><span>注释</span></label>
      </div>
      <div class="buttons">
        <button type="button" data-act="font-down" aria-label="缩小字号" title="缩小字号">A−</button>
        <button type="button" data-act="font-up" aria-label="放大字号" title="放大字号">A+</button>
        <button type="button" data-act="theme" aria-label="切换深浅色" title="切换深浅色">◐</button>
      </div>
      <div class="wider">
        <button type="button" class="width-btn" data-act="width" aria-expanded="false" aria-controls="width-panel" aria-label="调整内容宽度" title="内容宽度（快捷键 [ ]）">⇔</button>
        <div class="width-panel" id="width-panel" data-width-panel role="group" aria-label="内容宽度">
          <div class="width-h"><span>内容宽度</span><b data-width-value>1120px</b></div>
          <input class="width-range" type="range" min="860" max="2200" step="20" value="1120" data-width-range aria-label="内容宽度滑块">
          <div class="width-scale"><span>860</span><span>1530</span><span>2200</span></div>
          <div class="width-presets">
            <button type="button" data-width="960">紧凑</button>
            <button type="button" data-width="1120">标准</button>
            <button type="button" data-width="1360">宽</button>
            <button type="button" data-width="1600">更宽</button>
            <button type="button" data-width="none">满宽</button>
          </div>
        </div>
      </div>
      <div class="search">
        <input type="search" data-search placeholder="检索原文 / 译文 / 注释…" aria-label="检索当前页面">
        <span class="search-count" data-search-count></span>
      </div>
      <button type="button" class="menu-btn" data-act="menu" aria-label="打开目录">☰</button>
    </div>
  </div>
  <div class="progress" aria-hidden="true"><span class="progress-bar" data-progress></span></div>
</header>

<div class="layout">
  <aside class="side" data-side>
    <div class="side-inner">
      <div class="side-title">目录</div>
      <nav class="toc" aria-label="段落目录">
{render_toc(data)}
      </nav>
      <div class="side-foot">共 {len(paragraphs)} 段 · {len(data['sections'])} 节{side_fig} · 单文件离线</div>
    </div>
  </aside>

  <main class="main" data-main>
    <div id="paper-start"></div>
    <section class="masthead">
      <p class="kicker">逐段精读 · 原文 / 翻译 / 注释</p>
      <h1 class="h1-zh">{title_zh}</h1>
      <p class="h1-en" lang="en">{title_en}</p>
      <p class="byline">{esc(meta_line)}</p>
      <p class="oneliner">{esc(common.norm_ws(meta["one_line"]))}</p>
      <ul class="stats">
        <li><b>{len(paragraphs)}</b> 段</li>
        <li><b>{en_words}</b> 英文词</li>
        <li><b>{zh_chars}</b> 译文字</li>
        {fig_stat}
      </ul>
      <p class="src-note">原文来源：{esc(common.norm_ws(meta["source_note"]))} {link}</p>
    </section>

    <section class="map-wrap">
      <h2 class="map-h">论证结构总览</h2>
      <ol class="map">
{render_argument_map(meta)}
      </ol>
      <p class="map-tip">点击 P 编号跳到对应段落；卡片左上角的数字是该段的段号，地址栏用 <code>#p9</code> 也可直接定位。</p>
    </section>

{chr(10).join(sections_html)}

    <footer class="page-foot">
      <p>本页由 <code>paper-tutor</code> skill 生成 · 生成时间 {stamp}</p>
      <p>原文逐字照录，译文逐句对应；注释为阅读辅助，不等于原作者观点。</p>
      {fig_foot}
      <p><a href="#paper-start">回到开头</a></p>
    </footer>
  </main>
</div>

<button type="button" class="to-top" data-act="top" aria-label="回到顶部" title="回到顶部">↑</button>
<script>
{js}
</script>
</body>
</html>
"""


def main() -> int:
    common.force_utf8_stdout()
    parser = argparse.ArgumentParser(description="data.json → 3_精读阅读页.html（单文件离线）")
    parser.add_argument("data_pos", nargs="?", metavar="data.json", help="data.json 路径（也可用 --data）")
    parser.add_argument("--data", help="data.json 路径")
    parser.add_argument("-o", "--out", default="3_精读阅读页.html", help="输出 HTML 路径（默认 3_精读阅读页.html）")
    parser.add_argument("--subtitle", default="论文精读", help="页眉副标题")
    parser.add_argument(
        "--figure-mode",
        choices=("inline", "link"),
        default="inline",
        help="inline=把原图字节内联进 HTML（默认，单文件仍可离线）；link=把原图原样复制到 figures/ 并相对引用",
    )
    args = parser.parse_args()

    target = args.data or args.data_pos
    if not target:
        parser.error("需要指定 data.json（位置参数或 --data）")
    data_path = Path(target)
    try:
        data = common.load_data(data_path)
    except common.DataError as exc:
        common.die(f"数据校验失败：\n{exc}")

    for asset, marker in ((ASSETS / "reading.css", CSS_MARKER), (ASSETS / "reading.js", JS_MARKER)):
        if not asset.is_file():
            common.die(f"缺少资源文件：{asset}")

    css = (ASSETS / "reading.css").read_text(encoding="utf-8")
    js = (ASSETS / "reading.js").read_text(encoding="utf-8")
    if CSS_MARKER in css or JS_MARKER in js:
        common.die("资源文件里不应包含占位符 {{READING_CSS}} / {{READING_JS}}")

    out_path = Path(args.out)
    ctx = {"base": data_path.resolve().parent, "mode": args.figure_mode, "out_dir": out_path.resolve().parent}
    page = build_html(data, css, js, args.subtitle, ctx)
    common.ensure_parent(out_path)
    out_path.write_text(page, encoding="utf-8", newline="\n")

    size_kb = out_path.stat().st_size / 1024
    fig_count = common.count_figures(data)
    bits = [f"{len(data['paragraphs'])} 段"]
    if fig_count:
        bits.append(f"{fig_count} 图原样内联" if args.figure_mode == "inline" else f"{fig_count} 图已原样复制")
    tokens = "，".join(bits + [f"{size_kb:.0f} KB", "单文件离线" if args.figure_mode == "inline" else "需与 figures/ 同存"])
    print(f"已生成 {out_path}（{tokens}）", file=sys.stdout)
    inline_bytes = ctx.get("inline_bytes", 0)
    if inline_bytes > 12 * 1024 * 1024:
        print(
            f"提示：内联图片共 {inline_bytes / 1048576:.1f} MB，单文件偏大；"
            "可用 --figure-mode link 改成外置 figures/ 目录。",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
