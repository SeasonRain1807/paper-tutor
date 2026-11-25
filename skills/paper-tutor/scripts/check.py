#!/usr/bin/env python3
"""Quality gate for a close-reading data.json.

Checks, in order of severity:
  1. structure     — every paragraph has en / zh / three analysis fields
  2. verbatim      — every `en` must appear in source.txt, whitespace-normalized
  3. coverage      — every source paragraph must be represented by some `en`
  4. translation   — zh must exist, be Chinese, and not look merged or padded
  5. analysis      — the three note fields must be distinct and substantive
  6. argument map  — stage references must point at real paragraphs

Usage:
    python check.py --data data.json --source source.txt
    python check.py --data data.json --source source.txt --json
    python check.py --data data.json --allow-transcribed   # en is a transcription

Exit code 0 = no errors (warnings allowed), 1 = errors, 2 = cannot run.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402

LATIN_ONLY_RE = re.compile(r"^[A-Za-z0-9\s\W]+$")
PLACEHOLDER_RE = re.compile(r"^@@\s*\d+\s*$")  # en 还没被 autofill.py 填回


class Finding:
    def __init__(self, level: str, code: str, message: str, para: str = "", detail: str = ""):
        self.level = level  # error | warn | note
        self.code = code
        self.message = message
        self.para = para
        self.detail = detail

    def as_dict(self) -> dict:
        return {
            "level": self.level,
            "code": self.code,
            "para": self.para,
            "message": self.message,
            "detail": self.detail,
        }


def best_window(haystack: str, needle: str, width: int = 60) -> tuple[float, str, int]:
    """Return (similarity, closest source window, start index) for a missing paragraph."""
    matcher = difflib.SequenceMatcher(None, haystack, needle, autojunk=False)
    match = matcher.find_longest_match(0, len(haystack), 0, len(needle))
    start = max(0, match.a - width // 2)
    window = haystack[start : start + max(width, len(needle) + 40)]
    ratio = difflib.SequenceMatcher(None, window, needle, autojunk=False).ratio()
    return ratio, window, start


def first_divergence(source: str, en: str) -> tuple[int, str, str]:
    """Index of the first differing character between the source span and the data text."""
    limit = min(len(source), len(en))
    for index in range(limit):
        if source[index] != en[index]:
            lo = max(0, index - 40)
            hi = min(len(source), index + 60)
            return index, source[lo:hi], en[lo:hi]
    if len(source) > limit:
        return limit, source[max(0, limit - 40) : limit + 60], ""
    return limit, "", en[max(0, limit - 40) : limit + 60]


def align_diff(source_norm: str, en: str) -> tuple[int, str, str]:
    """Locate en in the source by a short anchor, then diff from that point.

    Anchors shrink from 60 to 12 characters so a single edited word does not hide
    the whole paragraph. Returns (absolute_index, source_slice, data_slice).
    """
    for size, skip in ((60, 0), (40, 0), (28, 8), (20, 16), (14, 24), (10, 32)):
        anchor = en[skip : skip + size]
        if len(anchor) < 8:
            continue
        at = source_norm.find(anchor)
        if at == -1:
            continue
        begin = max(0, at - skip)
        span = source_norm[begin : begin + len(en) + 60]
        index, src_slice, en_slice = first_divergence(span, en)
        return begin + index, src_slice, en_slice
    return -1, "", ""


def source_blocks(source_raw: str) -> list[str]:
    """Blank-line separated blocks of the source, whitespace-normalised."""
    blocks = (common.norm_ws(block) for block in re.split(r"\n\s*\n", source_raw))
    return [block for block in blocks if block]


def locate(blocks_norm: list[str], source_norm: str, en: str) -> tuple[int, int]:
    """Find en in the source.

    Returns (block_index, offset): block_index >= 0 when the text sits inside a
    single source block; block_index == -1 with offset >= 0 when it only matches
    the concatenation (i.e. it spans two blocks); (-1, -1) when absent.
    """
    for index, block in enumerate(blocks_norm):
        at = block.find(en)
        if at != -1:
            return index, at
    return -1, source_norm.find(en)


def check_paragraph_against_source(
    para: dict,
    blocks_norm: list[str],
    source_norm: str,
    findings: list[Finding],
    transcribed: bool,
) -> int:
    """Return 1 when the paragraph text was found verbatim in the source."""
    pid = para["id"]
    en = common.norm_ws(para["en"])
    if not en:
        return 0
    if PLACEHOLDER_RE.match(en):
        findings.append(
            Finding(
                "warn" if transcribed else "error",
                "verbatim",
                f"{pid} 的 en 还是占位符 {en}：先跑 scripts/autofill.py 把逐字原文填回去",
                pid,
                'autofill.py --data <data.json> --source <source.txt> 会把所有 "@@段号" 换成 source.txt 的原文。',
            )
        )
        return 0
    block_index, offset = locate(blocks_norm, source_norm, en)
    if block_index != -1:
        return 1

    # Text exists in the source but only by joining two blocks: either the data
    # merged two paragraphs, or the source split one paragraph at a stray blank line.
    if offset != -1:
        keep = para.get("kind") == "equation" or para.get("preserve_breaks")
        if keep:
            return 1
        level = "warn" if transcribed else "error"
        findings.append(
            Finding(
                level,
                "para-span",
                f"{pid} 的原文在 source 里横跨两个文本块——要么你把两段并成了一段，要么 source.txt 在该段中间多了一个空行",
                pid,
                f"这一段在 source 第 {offset} 字符附近；先确认原文的段落边界，再改 data.json 或 source.txt。",
            )
        )
        return 0

    ratio, window, start = best_window(source_norm, en)
    level = "warn" if transcribed else "error"
    if transcribed:
        note = "转写模式下不计为错误，但请人工核对下面两处文字"
    else:
        note = "数据中的 en 与原文不一致：可能被改写、删节、或跨段合并"
    findings.append(
        Finding(
            level,
            "verbatim",
            f"{pid} 的原文在 source 中找不到（最相似只有 {ratio:.0%}）——{note}",
            pid,
            f"source 第 {start} 字符附近：{common.display_width(window)}",
        )
    )
    if ratio >= 0.55:
        where, src_slice, en_slice = align_diff(source_norm, en)
        if where >= 0:
            findings.append(
                Finding(
                    "note",
                    "verbatim-diff",
                    f"{pid} 首个差异在 source 第 {where} 字符附近（数据里改了措辞、标点或数字）",
                    pid,
                    f"原文……{common.display_width(src_slice)}…… / 数据……{common.display_width(en_slice)}……",
                )
            )
    return 0


def check_paragraph_borders(
    data: dict, blocks_norm: list[str], source_norm: str, findings: list[Finding]
) -> None:
    """Catch one original paragraph split into two data entries."""
    owners: dict[int, list[str]] = {}
    for para in data.get("paragraphs") or []:
        if para.get("kind") not in ("body", "abstract") or para.get("preserve_breaks"):
            continue
        en = common.norm_ws(para.get("en") or "")
        if not en:
            continue
        block_index, _ = locate(blocks_norm, source_norm, en)
        if block_index != -1:
            owners.setdefault(block_index, []).append(para["id"])
    for block_index, pids in owners.items():
        if len(pids) < 2:
            continue
        findings.append(
            Finding(
                "error",
                "para-split",
                f"{'、'.join(pids)} 都对应原文的同一段——要么你把一段拆成了两段，要么 source.txt 把原文本来的两段并成了一块",
                pids[0],
                f"该块开头：{common.display_width(blocks_norm[block_index])}",
            )
        )


def check_coverage(data: dict, blocks: list[str], findings: list[Finding]) -> tuple[int, int]:
    en_all = common.norm_ws(" ".join(common.norm_ws(para["en"]) for para in data["paragraphs"]))
    meta = data.get("meta") or {}
    authors = meta.get("authors", "")
    if isinstance(authors, (list, tuple)):
        authors = " ".join(str(a) for a in authors)
    front_matter = common.norm_ws(
        " ".join(
            [
                str(meta.get("title_en", "")),
                str(authors or ""),
                str(meta.get("affiliation", "")),
                str(meta.get("venue", "")),
                " ".join(section.get("title_en", "") for section in data["sections"]),
            ]
        )
    ).lower()
    # When a source block merges front-matter pieces (e.g. authors + affiliation on
    # one block), no single meta field contains the whole block. Accept the block if
    # it only consists of known front-matter pieces (>=40 chars each) in order.
    front_pieces = [
        common.norm_ws(str(meta.get("title_en", "") or "")).lower(),
        common.norm_ws(str(authors or "")).lower(),
        common.norm_ws(str(meta.get("affiliation", "") or "")).lower(),
        common.norm_ws(str(meta.get("venue", "") or "")).lower(),
    ]
    raw_authors = meta.get("authors", "")
    if isinstance(raw_authors, (list, tuple)):
        front_pieces.extend(common.norm_ws(str(a)).lower() for a in raw_authors)
    front_pieces = [piece for piece in front_pieces if piece]

    def is_front_matter(flat: str) -> bool:
        text = flat.lower()
        if text in front_matter:
            return True
        i = 0
        matched = 0
        while i < len(text):
            while i < len(text) and text[i] in " ,;.":
                i += 1
            if i >= len(text):
                break
            rest = text[i:]
            hit = next((piece for piece in front_pieces if rest.startswith(piece)), None)
            if hit is None:
                return False
            i += len(hit)
            matched += 1
        return matched > 0

    missing = []
    considered = 0
    for flat in blocks:
        if len(flat) < 40:
            continue
        if is_front_matter(flat):
            # title, authors, affiliation, venue or a section heading — not a reading paragraph
            continue
        considered += 1
        if flat not in en_all:
            missing.append(flat)
    for block in missing[:6]:
        findings.append(
            Finding(
                "error",
                "coverage",
                f"原文中有一段没有出现在 data.json 里（{len(block)} 字符）：{common.display_width(block)}",
                "",
                "若这段是标题、页码或参考文献，请确认它已被有意排除；否则就是漏段。",
            )
        )
    if len(missing) > 6:
        findings.append(
            Finding("error", "coverage", f"另有 {len(missing) - 6} 段原文未被收录（仅列出前 6 段）")
        )
    return considered - len(missing), considered


def check_translation(para: dict, findings: list[Finding]) -> None:
    pid = para["id"]
    en, zh = para["en"], para["zh"]
    en_words = common.en_word_count(en)
    zh_chars = common.cjk_count(zh)

    if zh_chars == 0:
        findings.append(Finding("error", "zh-missing", f"{pid} 的译文没有任何中文", pid))
        return
    if LATIN_ONLY_RE.match(zh.strip()) and en_words > 3:
        findings.append(Finding("error", "zh-not-chinese", f"{pid} 的译文看起来仍是英文原文", pid))

    if en_words >= 12:
        ratio = zh_chars / en_words
        if ratio < 0.72:
            findings.append(
                Finding(
                    "warn",
                    "zh-short",
                    f"{pid} 译文偏短（{zh_chars} 个汉字 / {en_words} 个英文词 = {ratio:.2f}，常见约 1.2–2.2）",
                    pid,
                    "可能漏译了一整句或半句，请对照原文逐句核一遍。",
                )
            )
        elif ratio > 2.6:
            findings.append(
                Finding(
                    "warn",
                    "zh-long",
                    f"{pid} 译文偏长（{zh_chars} 个汉字 / {en_words} 个英文词 = {ratio:.2f}）",
                    pid,
                    "可能掺入了原文没有的内容，翻译不应补充解释。",
                )
            )

    en_sent = common.en_sentences(en)
    zh_sent = common.zh_sentences(zh)
    if en_sent >= 2 and zh_sent * 2 < en_sent:
        findings.append(
            Finding(
                "warn",
                "zh-merged",
                f"{pid} 英文 {en_sent} 句，译文只有 {zh_sent} 句，疑似把多句并成一句或漏译",
                pid,
            )
        )
    elif zh_sent > en_sent * 3 + 2:
        findings.append(
            Finding("warn", "zh-split", f"{pid} 英文 {en_sent} 句，译文 {zh_sent} 句，断句过碎", pid)
        )


def check_analysis(para: dict, findings: list[Finding]) -> None:
    pid = para["id"]
    analysis = para["analysis"]
    fields = {key: common.norm_ws(analysis[key]) for key in common.REQUIRED_NOTE_FIELDS}
    for key, value in fields.items():
        if len(value) < 24:
            findings.append(
                Finding(
                    "warn",
                    "note-thin",
                    f"{pid} 的 analysis.{key} 只有 {len(value)} 字符，过于单薄",
                    pid,
                    "注释要能独立说清“讲了什么 / 起什么作用 / 处于什么位置”，不能只写标签。",
                )
            )
    labels = list(fields)
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            left, right = fields[labels[i]], fields[labels[j]]
            if not left or not right:
                continue
            ratio = difflib.SequenceMatcher(None, left, right, autojunk=False).ratio()
            if ratio > 0.85:
                findings.append(
                    Finding(
                        "error",
                        "note-duplicate",
                        f"{pid} 的 {labels[i]} 与 {labels[j]} 内容几乎相同（相似度 {ratio:.0%}）",
                        pid,
                        "三者问题不同：讲了什么=内容，起什么作用=功能，什么位置=论证链条，请分开写。",
                    )
                )
    terms = analysis.get("terms") or []
    for term in terms:
        if common.non_empty(term.get("en")) and common.non_empty(term.get("zh")):
            if common.norm_ws(term["en"]).lower() == common.norm_ws(term["zh"]).lower():
                findings.append(
                    Finding("warn", "term-untranslated", f"{pid} 的术语 {term['en']!r} 未翻译", pid)
                )


def check_figures(
    data: dict,
    base_dir: Path | None,
    findings: list[Finding],
    write_hashes: bool = False,
    data_path: Path | None = None,
    sizes: dict[str, tuple[int, int] | None] | None = None,
) -> tuple[int, int]:
    """Audit the `figures` attachments: exist, are images, and are byte-identical.

    "不得更改图片任何信息" is only checkable against a recorded hash, so the
    first run writes `sha256` back into data.json (--write-figure-hashes) and
    every later run proves the bytes are still the paper's own.
    """
    total = 0
    verified = 0
    recorded: set[Path] = set()
    base = base_dir or Path(".")

    for para in data["paragraphs"]:
        pid = para.get("id", "?")
        for no, fig in enumerate(common.figures_of(para), 1):
            total += 1
            raw_path = Path(str(fig["path"]))
            path = raw_path if raw_path.is_absolute() else (base / raw_path)
            label = common.norm_ws(str(fig.get("label") or f"图 {no}"))

            if not path.suffix.lower().endswith(common.IMAGE_EXTS):
                findings.append(
                    Finding("error", "figure-type", f"{pid} 的 {label} 不是图片文件：{raw_path}", pid)
                )
                continue
            if not path.is_file():
                findings.append(
                    Finding(
                        "error",
                        "figure-missing",
                        f"{pid} 的 {label} 找不到文件：{path}",
                        pid,
                        "把原图放到 data.json 同目录的 figures/ 下，或用相对路径指向已有文件。",
                    )
                )
                continue

            recorded.add(path.resolve())
            raw = path.read_bytes()
            if sizes is not None:
                sizes[str(path.resolve())] = common.image_size(raw)
            mime = common.sniff_image_mime(raw, path)
            if mime == "application/octet-stream":
                findings.append(
                    Finding(
                        "error",
                        "figure-type",
                        f"{pid} 的 {label} 内容不是可识别的图片（扩展名 {path.suffix}）",
                        pid,
                        "常见原因：把网页另存为 .png、或文件被截断。请用论文的原始图片文件。",
                    )
                )
                continue

            sha = common.sha256_bytes(raw)
            stored = str(fig.get("sha256") or "")
            if write_hashes:
                fig["sha256"] = sha
                fig["bytes"] = len(raw)
            if stored:
                if stored == sha:
                    verified += 1
                else:
                    findings.append(
                        Finding(
                            "error",
                            "figure-hash",
                            f"{pid} 的 {label} 与记录的 sha256 不一致：图片被改动过",
                            pid,
                            f"记录 {stored[:12]}… 实际 {sha[:12]}…；要求原图字节不变（不裁剪、不重压缩、不叠标注）。",
                        )
                    )
            elif write_hashes:
                verified += 1
            else:
                findings.append(
                    Finding(
                        "note",
                        "figure-unrecorded",
                        f"{pid} 的 {label} 还没有 sha256 记录，无法证明图片未被改动",
                        pid,
                        "运行 check.py --write-figure-hashes 记录一次；之后每次校验都会比对。",
                    )
                )

            if not common.non_empty(fig.get("label")) and not common.non_empty(fig.get("caption")):
                findings.append(
                    Finding(
                        "warn",
                        "figure-unlabeled",
                        f"{pid} 的图片既没有 label 也没有 caption，读者无法判断这是论文的哪张图",
                        pid,
                        "至少写 label（如 'Figure 2'）或 caption（原图标题照抄）。",
                    )
                )

            try:
                path.resolve().relative_to(base.resolve())
            except ValueError:
                findings.append(
                    Finding(
                        "warn",
                        "figure-outside",
                        f"{pid} 的 {label} 位于 data.json 目录之外：{path}",
                        pid,
                        "交付时容易漏掉；建议复制到 <data.json 所在目录>/figures/ 再引用。",
                    )
                )

    # images that sit in figures/ but no paragraph uses
    fig_dir = base / "figures"
    if fig_dir.is_dir():
        for candidate in sorted(fig_dir.iterdir()):
            if not candidate.is_file() or candidate.suffix.lower() not in common.IMAGE_EXTS:
                continue
            if candidate.resolve() not in recorded:
                findings.append(
                    Finding(
                        "note",
                        "figure-unused",
                        f"figures/{candidate.name} 没有被任何段落引用",
                        "",
                        "如果正文确实讲到了它，就挂到对应段落的 figures 上；否则删掉以免误交付。",
                    )
                )

    if write_hashes and data_path is not None and total:
        data_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        print(f"已把 {total} 张图的 sha256 / 字节数写回 {data_path}")

    return total, verified


FIGURE_NO_RE = re.compile(r"^\s*(?:fig(?:ure)?s?\s*\.?\s*|图\s*)(\d+)", re.IGNORECASE)
PANEL_LABEL_RE = re.compile(r"[（(]\s*[a-z]\s*[)）]", re.IGNORECASE)


def manifest_figures(base: Path) -> dict[str, dict]:
    """Figure entries of figures/_manifest.json (written by scripts/figures.py)."""
    path = base / "figures" / "_manifest.json"
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    entries: dict[str, dict] = {}
    for figure in raw.get("figures") or []:
        if not isinstance(figure, dict):
            continue
        number = str(figure.get("number") or "")
        if number:
            entries[number] = figure
    return entries


def figure_number(text: str) -> str:
    match = FIGURE_NO_RE.match(text or "")
    return match.group(1) if match else ""


def figure_pixels(
    base: Path, fig: dict, sizes: dict[str, tuple[int, int] | None] | None = None
) -> tuple[int, int] | None:
    raw_path = Path(str(fig.get("path") or ""))
    path = raw_path if raw_path.is_absolute() else (base / raw_path)
    key = str(path.resolve())
    if sizes is not None and key in sizes:
        return sizes[key]
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    return common.image_size(raw)


def check_figure_integrity(
    data: dict,
    base_dir: Path | None,
    findings: list[Finding],
    sizes: dict[str, tuple[int, int] | None] | None = None,
) -> None:
    """One figure number = one complete image = one complete caption.

    A two-column PDF often stores a single figure as several bitmap bands. Export
    one band and the figure arrives cut in half, with its caption split into
    "Fig. 5(a) ..." and "Fig. 5(b) ...". Both are errors. The complete captions and
    the band sizes come from figures/_manifest.json (scripts/figures.py extract).
    """
    base = base_dir or Path(".")
    manifest = manifest_figures(base)
    seen: dict[str, str] = {}

    for para in data["paragraphs"]:
        pid = para.get("id", "?")
        for fig in common.figures_of(para):
            label = common.norm_ws(str(fig.get("label") or ""))
            caption = common.norm_ws(str(fig.get("caption") or ""))

            if PANEL_LABEL_RE.search(label):
                findings.append(
                    Finding(
                        "error",
                        "figure-panel-label",
                        f"{pid} 的图号写成了 {label}：子图号不该出现在 label 里",
                        pid,
                        "label 只写 Fig. 5；把 (a)(b) 各画了什么放回 caption，图只挂一张完整的。",
                    )
                )

            label_no = figure_number(label)
            caption_no = figure_number(caption)
            if label_no and caption_no and label_no != caption_no:
                findings.append(
                    Finding(
                        "warn",
                        "figure-label-mismatch",
                        f"{pid} 的图号 {label} 与图注开头的 Fig. {caption_no} 对不上",
                        pid,
                        "核对这张图到底配哪条图注；两栏排版里题注归属最容易错位一格。",
                    )
                )

            number = label_no or caption_no
            if number:
                if number in seen:
                    findings.append(
                        Finding(
                            "error",
                            "figure-split",
                            f"图 {number} 在 {seen[number]} 和 {pid} 各登记了一次",
                            pid,
                            "一个图号只登记一条 figures[]：合并到第一次详细展开它的那一段。",
                        )
                    )
                else:
                    seen[number] = pid

            entry = manifest.get(number) if number else None
            if not entry:
                continue

            full = common.norm_ws(str(entry.get("caption") or ""))
            if full and caption and len(caption) + 15 < len(full) and full.startswith(caption):
                findings.append(
                    Finding(
                        "error",
                        "figure-caption-truncated",
                        f"{pid} 的 {label or '图 ' + number} 图注只是整条图注的前缀，后半截丢了：{caption}",
                        pid,
                        f"整条图注是：{full}",
                    )
                )

            size = figure_pixels(base, fig, sizes)
            if size:
                bands = [tuple(band.get("px") or ()) for band in entry.get("bands") or []]
                if len(bands) > 1 and size in bands:
                    findings.append(
                        Finding(
                            "error",
                            "figure-band",
                            f"{pid} 的 {label or '图 ' + number} 只是整张图的一条分带：{size[0]}x{size[1]} px",
                            pid,
                            f"整张图是 {entry.get('px')} px（由 {len(bands)} 条分带拼成）；"
                            "用 figures.py extract 重取整张，不要把图拦腰切断。",
                        )
                    )


def check_sections(data: dict, source_norm: str, findings: list[Finding]) -> None:
    for section in data["sections"]:
        title = common.norm_ws(section["title_en"])
        if len(title) < 4:
            continue
        if title.lower() not in source_norm.lower():
            findings.append(
                Finding(
                    "warn",
                    "section-title",
                    f"章节标题 {title!r} 在 source 中找不到",
                    "",
                    f"section {section['id']} 的 title_en 应尽量照抄原文标题。",
                )
            )


def run(
    data: dict,
    source_text: str | None,
    transcribed: bool,
    base_dir: Path | None = None,
    write_hashes: bool = False,
    data_path: Path | None = None,
) -> tuple[list[Finding], dict]:
    findings: list[Finding] = []
    stats: dict = {"paragraphs": len(data["paragraphs"]), "verified": 0, "source_blocks": 0}

    for error in common.validate(data):
        findings.append(Finding("error", "schema", error))

    # 同一张图只读一次：check_figures 拿到字节后把像素尺寸留在 figure_sizes 里，
    # check_figure_integrity 直接复用，不再把每个图片文件读第二遍。
    figure_sizes: dict[str, tuple[int, int] | None] = {}
    stats["figures"], stats["figures_verified"] = check_figures(
        data, base_dir, findings, write_hashes, data_path, figure_sizes
    )
    check_figure_integrity(data, base_dir, findings, figure_sizes)

    for para in data["paragraphs"]:
        if para.get("kind") != "reference":
            check_translation(para, findings)
        check_analysis(para, findings)

    if source_text is not None:
        source_norm = common.norm_ws(source_text)
        if not source_norm:
            findings.append(Finding("error", "source-empty", "source 文件是空的，无法做逐字校验"))
        else:
            blocks = source_blocks(source_text)
            for para in data["paragraphs"]:
                stats["verified"] += check_paragraph_against_source(
                    para, blocks, source_norm, findings, transcribed
                )
            check_paragraph_borders(data, blocks, source_norm, findings)
            covered, considered = check_coverage(data, blocks, findings)
            stats["covered"] = covered
            stats["source_blocks"] = considered
            if considered and covered < considered:
                findings.append(
                    Finding(
                        "note",
                        "coverage-summary",
                        f"原文段落覆盖 {covered}/{considered}；未覆盖的段落可能是有意排除的图表标题或参考文献",
                    )
                )
            check_sections(data, source_norm, findings)
    else:
        findings.append(
            Finding(
                "warn",
                "no-source",
                "没有提供 --source，逐字与覆盖校验全部跳过——没有它，「原文逐字照录」这条约束等于没有验证",
                "",
                "补上 source.txt 后重跑：check.py data.json --source source.txt",
            )
        )
    return findings, stats


def render(findings: list[Finding], stats: dict, data: dict, source_label: str, color: bool) -> None:
    def paint(code: str, text: str) -> str:
        if not color:
            return text
        return f"\x1b[{code}m{text}\x1b[0m"

    errors = [item for item in findings if item.level == "error"]
    warns = [item for item in findings if item.level == "warn"]
    notes = [item for item in findings if item.level == "note"]

    print(f"数据：{stats['paragraphs']} 段 / {len(data['sections'])} 节")
    print(f"基准：{source_label}")
    if "covered" in stats:
        print(f"覆盖：{stats['covered']}/{stats['source_blocks']} 段原文已收录，{stats['verified']}/{stats['paragraphs']} 段原文逐字命中")
    else:
        print("逐字校验：未提供 --source，已跳过（强烈建议补上）")
    if stats.get("figures"):
        print(f"图片：{stats['figures_verified']}/{stats['figures']} 张已按记录字节核验（sha256）")
    print("")

    for item in errors:
        head = paint("31;1", "错误") + (f" [{'/'.join(filter(None, [item.para, item.code]))}]" if item.code else "")
        print(f"{head} {item.message}")
        if item.detail:
            print(f"      {item.detail}")
    for item in warns:
        print(paint("33;1", "警告") + f" [{item.code}] {item.message}")
        if item.detail:
            print(f"      {item.detail}")
    for item in notes:
        print(paint("36", "提示") + f" [{item.code}] {item.message}")
        if item.detail:
            print(f"      {item.detail}")

    if errors or warns or notes:
        print("")
    verdict = "通过" if not errors else "未通过"
    line = f"结论：{paint('32;1' if not errors else '31;1', verdict)} — 错误 {len(errors)}，警告 {len(warns)}，提示 {len(notes)}"
    print(line)
    if errors:
        print("先修错误项再生成 HTML；警告项请逐条判断是否真的需要改。")


def main() -> int:
    parser = argparse.ArgumentParser(description="逐段数据质量校验（逐字、覆盖、译文、注释）")
    parser.add_argument("data_pos", nargs="?", metavar="data.json", help="data.json 路径（也可用 --data）")
    parser.add_argument("--data", help="data.json 路径")
    parser.add_argument("--source", help="source.txt（或原文文件）路径，用于逐字与覆盖校验")
    parser.add_argument(
        "--allow-transcribed",
        action="store_true",
        help="原文缺失、en 是自己转写的文本时使用：逐字不一致降级为警告",
    )
    parser.add_argument("--json", action="store_true", help="输出机器可读结果")
    parser.add_argument(
        "--write-figure-hashes",
        action="store_true",
        help="把每张图的 sha256 / 字节数写回 data.json（第一次挂图时跑一次，之后靠它证明图片未被改动）",
    )
    args = parser.parse_args()

    target = args.data or args.data_pos
    if not target:
        parser.error("需要指定 data.json（位置参数或 --data）")
    data_path = Path(target)
    common.force_utf8_stdout()
    try:
        data = common.read_json(data_path)
    except common.DataError as exc:
        common.die(f"读取失败：{exc}")

    source_text = None
    source_label = "（未提供）"
    if args.source:
        source_path = Path(args.source)
        try:
            source_text = source_path.read_text(encoding="utf-8-sig")
        except FileNotFoundError:
            common.die(f"找不到 source 文件：{source_path}")
        except OSError as exc:
            common.die(f"无法读取 {source_path}：{exc}")
        source_label = f"{source_path.name}（{len(source_text)} 字符）"

    findings, stats = run(
        data,
        source_text,
        args.allow_transcribed,
        base_dir=data_path.resolve().parent,
        write_hashes=args.write_figure_hashes,
        data_path=data_path,
    )
    errors = [item for item in findings if item.level == "error"]

    if args.json:
        print(
            json.dumps(
                {
                    "ok": not errors,
                    "stats": stats,
                    "findings": [item.as_dict() for item in findings],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        render(findings, stats, data, source_label, sys.stdout.isatty() or bool(__import__("os").environ.get("FORCE_COLOR")))

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
