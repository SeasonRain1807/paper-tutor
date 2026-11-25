#!/usr/bin/env python3
"""Extract the reading-order text of a paper into source.txt.

This is the "verbatim baseline": whatever this script writes becomes the text
that every paragraph's `en` is checked against, so it must contain the paper's
words and nothing added by us. No markdown decoration, no page numbers, no
running heads, no translator notes.

Usage:
    python extract.py --input paper.html --out source.txt
    python extract.py --input paper.pdf  --out source.txt
    python extract.py --input paper.docx --out source.txt
    python extract.py --url https://arxiv.org/html/2401.00001 --out source.txt

Supported: .txt .md .html .htm .xhtml .pdf .docx .xml (JATS). PDF needs either
the `pypdf` module or the `pdftotext` binary; if neither exists the script says
so instead of guessing. Scanned PDFs without a text layer are reported, not OCRed.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import unicodedata
import urllib.request
from pathlib import Path

BLOCK_TAGS = ("p", "h1", "h2", "h3", "h4", "h5", "h6", "figcaption", "blockquote", "li", "dd")
HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5", "h6")
HEADING_STYLE_RE = re.compile(r"^(heading|title)\s*\d*$", re.IGNORECASE)
SECTION_LIKE_RE = re.compile(
    r"^(?:\d+(?:\.\d+)*\.?\s+\S|abstract\b|introduction\b|related work\b|background\b|"
    r"method(?:s|ology)?\b|approach\b|experiment(?:s)?\b|result(?:s)?\b|evaluation\b|"
    r"discussion\b|conclusion(?:s)?\b|limitations?\b|references\b|appendix\b)",
    re.IGNORECASE,
)
JUNK_PATTERNS = (
    re.compile(r"^(?:page\s*)?\d{1,4}(?:\s*(?:/|of)\s*\d{1,4})?$", re.IGNORECASE),
    re.compile(r"^(?:preprint|under review|accepted|published|camera[- ]ready)\b.*$", re.IGNORECASE),
    re.compile(r"^(?:arxiv|doi|https?://|\u00a9|©|copyright)\b.*$", re.IGNORECASE),
    re.compile(r"^(?:downloaded from|all rights reserved|see discussions?|citation)\b.*$", re.IGNORECASE),
    re.compile(r"^[\s\-–—_=·•.]+$"),
)
NAV_CLASS_HINTS = ("nav", "menu", "sidebar", "footer", "header", "share", "cookie", "banner", "breadcrumb", "toolbar", "skip")
DROP_XPATH = (
    ".//script",
    ".//style",
    ".//noscript",
    ".//nav",
    ".//header",
    ".//footer",
    ".//form",
    ".//svg",
    ".//button",
    ".//select",
    ".//iframe",
    ".//*[contains(@class,'ltx_page_nav')]",
    ".//*[contains(@class,'ltx_page_footer')]",
    ".//*[contains(@class,'ltx_page_header')]",
    ".//*[contains(@class,'ltx_abstract') and not(.//p)]",
)

USER_AGENT = "Mozilla/5.0 (compatible; paper-tutor/1.0; +https://example.invalid)"


# --------------------------------------------------------------------------- #
# text helpers
# --------------------------------------------------------------------------- #


def clean_line(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\u00ad", "").replace("\u200b", "").replace("\ufeff", "")
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    return text.strip()


def join_wrapped(lines: list[str]) -> str:
    """Join hard-wrapped lines, repairing hyphenated line breaks."""
    out = ""
    for line in lines:
        line = clean_line(line)
        if not line:
            continue
        if not out:
            out = line
            continue
        if out.endswith("-") and line[:1].islower():
            out = out[:-1] + line
        else:
            out += " " + line
    return out.strip()


def is_junk(text: str) -> bool:
    flat = text.strip()
    if not flat:
        return True
    return any(pattern.match(flat) for pattern in JUNK_PATTERNS)


def looks_like_heading(text: str, explicit: bool) -> bool:
    if explicit:
        return True
    flat = clean_line(text)
    if not flat or len(flat) > 110 or flat.endswith((".", ",", ";", ":")) and len(flat) > 60:
        return False
    words = flat.split()
    if len(words) > 14:
        return False
    if SECTION_LIKE_RE.match(flat):
        return True
    return flat.isupper() and len(words) <= 10


def strip_markdown_light(text: str) -> str:
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s{0,3}>\s?", "", text, flags=re.MULTILINE)
    text = re.sub(r"(\*\*|__)(.+?)\1", r"\2", text)
    text = re.sub(r"(?<![\w*])(\*|_)(?!\s)(.+?)(?<!\s)\1(?![\w*])", r"\2", text)
    text = re.sub(r"`{1,3}([^`]*)`{1,3}", r"\1", text)
    return text


def dedupe_running_heads(blocks: list[tuple[str, bool, int]]) -> list[tuple[str, bool, int]]:
    """Drop short blocks repeated 3+ times (running heads, journal names)."""
    counts: dict[str, int] = {}
    for text, heading, _ in blocks:
        if not heading and len(text) <= 90:
            counts[text] = counts.get(text, 0) + 1
    return [block for block in blocks if not (counts.get(block[0], 0) >= 3 and not block[1] and len(block[0]) <= 90)]


# --------------------------------------------------------------------------- #
# extractors: each returns [(text, is_heading, level)]
# --------------------------------------------------------------------------- #


def extract_plain(text: str) -> list[tuple[str, bool, int]]:
    blocks: list[tuple[str, bool, int]] = []
    for chunk in re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\r", "\n")):
        flat = join_wrapped(chunk.split("\n"))
        if flat and not is_junk(flat):
            blocks.append((flat, looks_like_heading(flat, False), 0))
    return blocks


def extract_html(raw: str) -> list[tuple[str, bool, int]]:
    try:
        from lxml import html as lxml_html
    except ImportError:  # pragma: no cover
        raise SystemExit(
            "缺少 lxml，无法解析 HTML。请改用 python-docx 可读的 .docx，或先用浏览器把页面另存为 .html 后重试。"
        )

    doc = lxml_html.fromstring(raw)
    for xpath in DROP_XPATH:
        for node in doc.xpath(xpath):
            node.drop_tree()

    root = None
    for candidate in (
        "//*[contains(@class,'ltx_document')]",
        "//article",
        "//main",
        "//*[@role='main']",
        "//*[@id='content']",
        "//*[@id='main']",
    ):
        found = doc.xpath(candidate)
        if found:
            root = found[0]
            break
    if root is None:
        root = doc.body if doc.body is not None else doc

    math_nodes = root.xpath(".//*[local-name()='math']")
    for node in math_nodes:
        alt = node.get("alttext") or node.get("aria-label") or ""
        replacement = f"${alt.strip()}$" if alt.strip() else (node.text_content() or "")
        node.clear()
        node.text = replacement

    nodes = []
    for node in root.iter():
        tag = node.tag if isinstance(node.tag, str) else ""
        if tag in BLOCK_TAGS:
            if node.getparent() is not None and any(
                isinstance(anc.tag, str) and anc.tag in BLOCK_TAGS for anc in node.iterancestors()
                if anc is not root
            ):
                continue
            nodes.append(node)

    blocks: list[tuple[str, bool, int]] = []
    for node in nodes:
        classes = (node.get("class") or "").lower()
        if any(hint in classes for hint in NAV_CLASS_HINTS):
            continue
        text = join_wrapped((node.text_content() or "").split("\n"))
        if not text or is_junk(text):
            continue
        tag = node.tag if isinstance(node.tag, str) else ""
        heading = tag in HEADING_TAGS
        level = int(tag[1]) if heading and tag[1:].isdigit() else 0
        blocks.append((text, heading or looks_like_heading(text, False), level))
    return blocks


def extract_docx(path: Path) -> list[tuple[str, bool, int]]:
    try:
        import docx  # python-docx
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError:  # pragma: no cover
        raise SystemExit("缺少 python-docx，无法读取 .docx。")
    document = docx.Document(str(path))
    blocks: list[tuple[str, bool, int]] = []
    # Walk the body in document order so tables stay where the author put them.
    for child in document.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            paragraph = Paragraph(child, document)
            text = join_wrapped(paragraph.text.split("\n"))
            if not text or is_junk(text):
                continue
            style = (paragraph.style.name or "") if paragraph.style is not None else ""
            heading = bool(HEADING_STYLE_RE.match(style.strip()))
            level = 0
            match = re.search(r"(\d)", style)
            if heading and match:
                level = int(match.group(1))
            blocks.append((text, heading or looks_like_heading(text, False), level))
        elif tag == "tbl":
            table = Table(child, document)
            for row in table.rows:
                cells = [join_wrapped(cell.text.split("\n")) for cell in row.cells]
                cells = [cell for cell in cells if cell and not is_junk(cell)]
                if cells:
                    blocks.append((" | ".join(dict.fromkeys(cells)), False, 0))
    return blocks


def extract_pdf(path: Path) -> list[tuple[str, bool, int]]:
    text = ""
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(path))
        pages = [(page.extract_text() or "") for page in reader.pages]
        text = "\n\n".join(pages)
    except ImportError:
        binary = shutil.which("pdftotext")
        if binary:
            result = subprocess.run(
                [binary, "-layout", "-enc", "UTF-8", str(path), "-"],
                capture_output=True,
                check=False,
            )
            text = result.stdout.decode("utf-8", errors="replace")
        else:
            raise SystemExit(
                "本机没有可用的 PDF 文本层提取器（缺 pypdf 模块，也缺 pdftotext）。\n"
                "可选做法：\n"
                "  0) 装一次 pypdf，装进当前这个解释器（之后所有会话都不用再装）：\n"
                '     "' + sys.executable + '" -m pip install "pypdf>=5,<7"\n'
                "     或 python scripts/deps.py --install（只装缺的）。不要 --target 到论文目录里。\n"
                "  1) 让用户提供该论文的 HTML / arXiv abs 页 / 出版社网页链接；\n"
                "  2) 让用户提供 Word 或纯文本版本；\n"
                "  3) 用户手动复制正文存为 .txt；\n"
                "不要凭印象转写全文。"
            )

    if len(text.strip()) < 200:
        raise SystemExit(
            "这份 PDF 几乎没有可提取的文本层（很可能是扫描件或纯图片）。\n"
            "请让用户提供 HTML/Word/文本版本；不要默认对 PDF 做 OCR，也不要凭记忆转写。"
        )

    blocks: list[tuple[str, bool, int]] = []
    current: list[str] = []

    def flush() -> None:
        nonlocal current
        if current:
            flat = join_wrapped(current)
            if flat and not is_junk(flat):
                blocks.append((flat, looks_like_heading(flat, False), 0))
            current = []

    for raw_line in text.replace("\r\n", "\n").split("\n"):
        line = clean_line(raw_line)
        if not line:
            flush()
            continue
        if is_junk(line):
            continue
        if looks_like_heading(line, False) and not current:
            blocks.append((line, True, 0))
            continue
        if current:
            previous = current[-1]
            if previous.endswith((".", "?", "!", "。", "！", "？")) and re.match(r"^(?:[A-Z0-9\u4e00-\u9fff\"“(])", line):
                flush()
                current.append(line)
                continue
        current.append(line)
    flush()
    return blocks


def extract_jats(raw: str) -> list[tuple[str, bool, int]]:
    try:
        from lxml import etree
    except ImportError:  # pragma: no cover
        raise SystemExit("缺少 lxml，无法解析 JATS XML。")
    parser = etree.XMLParser(recover=True, remove_comments=True)
    root = etree.fromstring(raw.encode("utf-8"), parser)
    blocks: list[tuple[str, bool, int]] = []
    for element in root.iter():
        tag = etree.QName(element).localname if isinstance(element.tag, str) else ""
        if tag not in ("p", "title", "label", "caption"):
            continue
        text = join_wrapped(("".join(element.itertext())).split("\n"))
        if not text or is_junk(text):
            continue
        heading = tag == "title"
        blocks.append((text, heading, 1 if heading else 0))
    return blocks


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #


def fetch_url(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.8"})
    with urllib.request.urlopen(request, timeout=45) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        payload = response.read()
    for candidate in (charset, "utf-8", "gb18030", "latin-1"):
        try:
            return payload.decode(candidate)
        except (UnicodeDecodeError, LookupError):
            continue
    return payload.decode("utf-8", errors="replace")


def normalize_blocks(blocks: list[tuple[str, bool, int]]) -> list[tuple[str, bool, int]]:
    merged: list[tuple[str, bool, int]] = []
    for text, heading, level in blocks:
        if merged and not heading and not merged[-1][1]:
            previous = merged[-1][0]
            if previous.endswith((",", ";", ":", "(", "–", "-", "/")) or text[:1].islower():
                merged[-1] = (f"{previous} {text}", False, merged[-1][2])
                continue
        merged.append((text, heading, level))
    return dedupe_running_heads(merged)


def render_blocks(blocks: list[tuple[str, bool, int]]) -> str:
    out: list[str] = []
    for index, (text, heading, _level) in enumerate(blocks):
        if index and heading:
            out.append("")
        out.append(text)
        out.append("")
    joined = "\n".join(out).strip()
    joined = re.sub(r"\n{3,}", "\n\n", joined)
    return joined + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="把论文转成纯文本 source.txt（逐字基准）")
    parser.add_argument("input_pos", nargs="?", metavar="input", help="本地文件（也可用 --input）")
    parser.add_argument("--input", help="本地文件：.html .htm .txt .md .pdf .docx .xml")
    parser.add_argument("--url", help="论文网页 URL（arXiv HTML、出版社页面等）")
    parser.add_argument("-o", "--out", required=True, help="输出文本路径，通常为 source.txt")
    args = parser.parse_args()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError, OSError):
            pass

    if not (args.input or args.input_pos) and not args.url:
        parser.error("需要给出本地文件（位置参数或 --input）或 --url 之一")

    if args.url:
        try:
            raw = fetch_url(args.url)
        except Exception as exc:  # noqa: BLE001
            raise SystemExit(f"抓取 {args.url} 失败：{exc}\n可让用户把页面另存为 .html 后使用 --input。")
        blocks = extract_html(raw)
        origin = args.url
    else:
        path = Path(args.input or args.input_pos)
        if not path.is_file():
            raise SystemExit(f"找不到文件：{path}")
        suffix = path.suffix.lower()
        if suffix in (".html", ".htm", ".xhtml"):
            blocks = extract_html(path.read_text(encoding="utf-8", errors="replace"))
        elif suffix in (".txt", ".md", ".markdown"):
            text = path.read_text(encoding="utf-8-sig", errors="replace")
            if suffix != ".txt":
                text = strip_markdown_light(text)
            blocks = extract_plain(text)
        elif suffix == ".pdf":
            blocks = extract_pdf(path)
        elif suffix == ".docx":
            blocks = extract_docx(path)
        elif suffix in (".xml", ".jats"):
            blocks = extract_jats(path.read_text(encoding="utf-8", errors="replace"))
        else:
            raise SystemExit(f"不认识的扩展名 {suffix!r}；支持 .html .htm .txt .md .pdf .docx .xml")
        origin = str(path)

    blocks = normalize_blocks(blocks)
    if not blocks:
        raise SystemExit("没有提取到任何正文。请检查输入文件，或让用户提供 HTML/文本版本。")

    text = render_blocks(blocks)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8", newline="\n")

    headings = sum(1 for _text, heading, _level in blocks if heading)
    chars = len(text)
    print(f"来源：{origin}")
    print(f"已写出 {out_path}：{len(blocks)} 个文本块（其中 {headings} 个疑似标题），{chars} 字符")
    print("下一步：人工核对 source.txt —— 删掉页眉页脚/作者单位/致谢等不需要精读的部分，再按段切分生成 data.json。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
