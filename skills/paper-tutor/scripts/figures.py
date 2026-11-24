#!/usr/bin/env python3
"""Extract each figure of a PDF as ONE complete image, never as a slice of one.

Why this script exists
----------------------
A reader never sees "images", they see figures. The PDF file, however, often
stores one figure as several image XObjects placed edge to edge (a band, a tile,
a 2x2 grid: usually a compression artefact). Nobody reading the paper sees the
tiles: they see one complete picture with one caption. So the unit this script
emits is the figure, and only the figure:

    one figure number  ==  one complete image  ==  one caption

Consequences, by construction:
  * touching tiles are reassembled into a single picture, pixel by pixel, with
    no scaling and no resampling;
  * a lone tile is never emitted as a figure, so a figure cannot be cut in half;
  * the caption is the whole caption block, "(a) ... and (b) ..." included, and
    is never split per panel.

A figure stored as a single image keeps its original bytes, untouched. A figure
that had to be reassembled is written as a lossless PNG, and the manifest records
every input xref, its rect, and the paste offset, so the reassembly is auditable.

Usage
-----
    python figures.py probe   --pdf paper.pdf
    python figures.py extract --pdf paper.pdf --out figures/

probe only reports (pages, placements, clusters, captions, proposed names).
extract writes one file per figure plus figures/_manifest.json and prints a
paste-ready JSON block for data.json.

Dependencies: PyMuPDF (pip install pymupdf) to read the PDF, Pillow to reassemble
tiles. Both are checked up front; the script never guesses.

Exit codes: 0 ok, 2 cannot run, 3 ran but a figure could not be emitted
completely (the message says which one and why).
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common  # noqa: E402

MANIFEST_NAME = "_manifest.json"
DEFAULT_TOL = 1.5       # pt: gaps up to this still count as "one picture, tiled"
DEFAULT_MIN_AREA = 0.4  # % of the page: smaller bitmaps are logos / rules / icons
MIN_SIDE_PX = 96        # px: anything thinner than this is not a figure

CAPTION_RE = re.compile(r"^\s*((?:Fig(?:ure)?|FIGURE|图)\s*\.?\s*(\d+[a-z]?))\b")
TABLE_RE = re.compile(r"^\s*((?:Table|TABLE|表)\s*\.?\s*(\d+[a-z]?))\b", re.IGNORECASE)
CONT_RE = re.compile(r"^\s*(?:\(?[a-z]\)|and\s|\bcontinued\b|,)", re.IGNORECASE)


# --------------------------------------------------------------------------- #
# dependencies
# --------------------------------------------------------------------------- #


def load_fitz():
    try:
        import fitz  # type: ignore
    except ImportError:
        try:
            import pymupdf as fitz  # type: ignore
        except ImportError:
            common.die(
                "本机没有可用的 PDF 位图读取器（缺 PyMuPDF）。\n"
                "安装一次即可：\n"
                "    pip install pymupdf\n"
                "装好后重跑本脚本；不要退回截图，也不要凭印象拼图。"
            )
    return fitz


def load_pil():
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        common.die(
            "本机没有 Pillow，无法把被 PDF 拆开的图块拼回一张图。\n"
            "安装一次即可：\n    pip install pillow"
        )
    return Image


# --------------------------------------------------------------------------- #
# geometry
# --------------------------------------------------------------------------- #


def overlap(start_a: float, end_a: float, start_b: float, end_b: float) -> float:
    """Length of the intersection of two 1-D intervals (0 when disjoint)."""
    return max(0.0, min(end_a, end_b) - max(start_a, start_b))


def same_row(a: dict, b: dict) -> bool:
    """True when two placements sit side by side on one visual line."""
    span_a = a["rect"][3] - a["rect"][1]
    span_b = b["rect"][3] - b["rect"][1]
    return overlap(a["rect"][1], a["rect"][3], b["rect"][1], b["rect"][3]) >= 0.5 * min(span_a, span_b)


def touching(a: dict, b: dict, tol: float) -> bool:
    """True when two placements are adjacent parts of one continuous picture.

    They must share an edge (with overlap on the other axis) and be closer than
    tol points on the separated axis. Two different figures on a page always have
    a caption or a wider gap between them.
    """
    ax0, ay0, ax1, ay1 = a["rect"]
    bx0, by0, bx1, by1 = b["rect"]
    side_by_side = (
        overlap(ay0, ay1, by0, by1) > 0.6 * min(ay1 - ay0, by1 - by0)
        and (abs(ax1 - bx0) <= tol or abs(bx1 - ax0) <= tol)
    )
    stacked = (
        overlap(ax0, ax1, bx0, bx1) > 0.6 * min(ax1 - ax0, bx1 - bx0)
        and (abs(ay1 - by0) <= tol or abs(by1 - ay0) <= tol)
    )
    return side_by_side or stacked


def cluster(items: list[dict], tol: float) -> list[list[dict]]:
    """Group placements that belong to one picture (union-find over adjacency)."""
    parent = list(range(len(items)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if touching(items[i], items[j], tol):
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[rj] = ri
    groups: dict[int, list[dict]] = {}
    for index, item in enumerate(items):
        groups.setdefault(find(index), []).append(item)
    return [
        sorted(group, key=lambda it: (round(it["rect"][1], 1), it["rect"][0]))
        for group in groups.values()
    ]


def bbox_of(group: list[dict]) -> list[float]:
    return [
        min(item["rect"][0] for item in group),
        min(item["rect"][1] for item in group),
        max(item["rect"][2] for item in group),
        max(item["rect"][3] for item in group),
    ]


# --------------------------------------------------------------------------- #
# PDF reading
# --------------------------------------------------------------------------- #


def page_placements(page, min_area: float) -> tuple[list[dict], list[dict]]:
    """Image placements on one page, split into (kept, skipped-as-decoration)."""
    page_area = abs(page.rect.width * page.rect.height) or 1.0
    kept: list[dict] = []
    skipped: list[dict] = []
    try:
        infos = page.get_image_info(xrefs=True)
    except TypeError:  # older PyMuPDF without xrefs=
        infos = page.get_image_info()
    for info in infos:
        rect = [round(float(value), 2) for value in info["bbox"]]
        area = max(0.0, rect[2] - rect[0]) * max(0.0, rect[3] - rect[1])
        item = {
            "xref": int(info.get("xref") or 0),
            "px": [int(info["width"]), int(info["height"])],
            "rect": rect,
            "bpc": int(info.get("bpc") or 8),
            "colorspace": info.get("colorspace") or "",
        }
        if info.get("smask"):
            item["smask"] = int(info["smask"])
        reason = ""
        if not item["xref"]:
            reason = "没有可导出的 xref"
        elif area <= 0:
            reason = "面积为 0"
        elif area / page_area * 100 < min_area:
            reason = "面积只有页面的 %.2f%%" % (area / page_area * 100)
        elif min(item["px"]) < MIN_SIDE_PX:
            reason = "像素过小（%dx%d）" % (item["px"][0], item["px"][1])
        if reason:
            item["reason"] = reason
            skipped.append(item)
        else:
            kept.append(item)
    return kept, skipped


def decode_image(doc, fitz, Image, xref: int):
    """Return (PIL image in RGB, original bytes, container ext) for one xref."""
    info = doc.extract_image(xref)
    raw = info["image"]
    ext = (info.get("ext") or "bin").lower()
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
        return image.convert("RGB"), raw, ext
    except Exception:
        # Exotic codec (JPX, JBIG2, CMYK, ...): let MuPDF decode it instead.
        pix = fitz.Pixmap(doc, xref)
        if pix.colorspace is None or pix.colorspace.n > 3:
            pix = fitz.Pixmap(fitz.csRGB, pix)
        mode = "RGB" if pix.n == 3 else ("RGBA" if pix.n == 4 else "L")
        image = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
        return image.convert("RGB"), raw, ext


def assemble(group: list[dict], doc, page, fitz, Image, allow_render: bool) -> dict:
    """Reassemble one picture from its tiles.

    kind is "single" when the picture already was one image (its bytes are used
    as they are), "stitch" when tiles were pasted back together pixel for pixel,
    "render" when the tiling could not be undone and the page region was drawn
    instead, "unresolved" when even that was not allowed.
    """
    decoded = []
    for item in group:
        image, raw, ext = decode_image(doc, fitz, Image, item["xref"])
        decoded.append((item, image, raw, ext))

    if len(group) == 1:
        item, image, raw, ext = decoded[0]
        return {
            "image": image,
            "kind": "single",
            "raw": raw,
            "ext": ext,
            "bands": [{"xref": item["xref"], "px": item["px"], "rect": item["rect"], "offset": [0, 0]}],
            "note": "",
            "pixmap": None,
        }

    # Tiles that share a visual line form a row; rows are stacked top to bottom.
    rows: list[list[tuple]] = []
    for entry in sorted(decoded, key=lambda cell: (round(cell[0]["rect"][1], 1), cell[0]["rect"][0])):
        for row in rows:
            if same_row(row[0][0], entry[0]):
                row.append(entry)
                break
        else:
            rows.append([entry])
    for row in rows:
        row.sort(key=lambda cell: cell[0]["rect"][0])

    notes: list[str] = []
    placements: list[tuple] = []
    y = 0
    consistent = True
    for row in rows:
        heights = {cell[1].height for cell in row}
        if len(heights) != 1:
            consistent = False
            notes.append("同一行的图块像素高度不一致")
            break
        row_height = heights.pop()
        x = 0
        for cell in row:
            placements.append((cell, x, y))
            x += cell[1].width
        y += row_height
    widths = {sum(cell[1].width for cell in row) for row in rows}
    if consistent and len(widths) == 1:
        canvas = Image.new("RGB", (widths.pop(), y), "white")
        for cell, x, offset_y in placements:
            canvas.paste(cell[1], (x, offset_y))
        rect = bbox_of(group)
        scale_x = canvas.width / max(1e-6, rect[2] - rect[0])
        scale_y = canvas.height / max(1e-6, rect[3] - rect[1])
        drift = abs(scale_x - scale_y) / max(scale_x, scale_y)
        if drift > 0.04:
            notes.append("拼接后横竖比例与页面几何相差 %.1f%%，请目视确认" % (drift * 100))
        bands = [
            {
                "xref": cell[0]["xref"],
                "px": cell[0]["px"],
                "rect": cell[0]["rect"],
                "offset": [x, offset_y],
            }
            for cell, x, offset_y in placements
        ]
        return {
            "image": canvas,
            "kind": "stitch",
            "raw": None,
            "ext": "png",
            "bands": bands,
            "note": "；".join(notes),
            "pixmap": None,
        }

    # -- tiling that cannot be undone pixel by pixel ------------------------- #
    rect = bbox_of(group)
    if not allow_render:
        return {
            "image": None,
            "kind": "unresolved",
            "raw": None,
            "ext": "png",
            "bands": [{"xref": item["xref"], "px": item["px"], "rect": item["rect"]} for item in group],
            "note": "图块尺寸不成行/不成列，无法逐像素拼接；加 --allow-render 让脚本按页内区域渲染一次",
            "pixmap": None,
        }
    scales = [item["px"][0] / max(1e-6, item["rect"][2] - item["rect"][0]) for item in group]
    zoom = max(scales) if scales else 4.0
    pixmap = page.get_pixmap(clip=fitz.Rect(*rect), matrix=fitz.Matrix(zoom, zoom), alpha=False)
    return {
        "image": None,
        "kind": "render",
        "raw": None,
        "ext": "png",
        "bands": [{"xref": item["xref"], "px": item["px"], "rect": item["rect"]} for item in group],
        "note": "分带无法无损拼接，按页内区域渲染（完整，但不是原字节）",
        "pixmap": pixmap,
    }


# --------------------------------------------------------------------------- #
# captions
# --------------------------------------------------------------------------- #


STOP_LINE_RE = re.compile(
    r"^\s*(?:\d+\s*)?(?:Acknowledge?ments?|References|Bibliography|Keywords|"
    r"Author Contributions?|Funding|Conflict(?:s)? of Interest)\b",
    re.IGNORECASE,
)

BELOW = 0    # the normal case: the caption sits under its figure
INSIDE = 1   # the caption is printed over the picture (rare)
ABOVE = 2    # the caption sits above its picture (rare)


def block_text(block: dict) -> str:
    """All text of a dict-mode text block, normalized to one line."""
    lines = []
    for line in block.get("lines", []):
        lines.append("".join(span.get("text", "") for span in line.get("spans", [])))
    return common.norm_ws(" ".join(lines))


def line_text(line: dict) -> str:
    return " ".join("".join(span.get("text", "") for span in line.get("spans", [])).split())


def line_size(line: dict) -> float:
    sizes = [float(span.get("size") or 0.0) for span in line.get("spans", [])]
    return max(sizes) if sizes else 0.0


def caption_blocks(page) -> list[dict]:
    """Text blocks that begin a figure or table caption, with their own geometry.

    A PDF text block can hold more than the caption: typesetters often put the
    Acknowledgements or References straight after it in the same block. So only
    the caption's own lines are kept, and collection stops at a blank line, at a
    font-size change, or at a heading such as "Acknowledgements".
    """
    blocks = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        flat = block_text(block)
        if not flat:
            continue
        kind = "figure"
        match = CAPTION_RE.match(flat)
        if not match:
            match = TABLE_RE.match(flat)
            kind = "table" if match else ""
        if not match:
            continue

        kept: list[str] = []
        rect: list[float] | None = None
        base_size = 0.0
        for line in block.get("lines", []):
            text = line_text(line)
            size = line_size(line)
            if not text:
                break
            if STOP_LINE_RE.match(text):
                break
            continuation = bool(CONT_RE.match(text))
            if not kept:
                base_size = size
            elif not continuation and abs(size - base_size) > 0.3:
                # A "(b) ..." line is a panel label and may sit in another font;
                # any other size change means the caption has ended.
                break
            kept.append(text)
            box = [float(value) for value in line.get("bbox", block.get("bbox"))]
            if rect is None:
                rect = box
            else:
                rect = [min(rect[0], box[0]), min(rect[1], box[1]), max(rect[2], box[2]), max(rect[3], box[3])]
        if not kept or rect is None:
            continue
        blocks.append(
            {
                "label": common.norm_ws(match.group(1)),
                "number": match.group(2),
                "kind": kind,
                "rect": [round(value, 2) for value in rect],
                "text": common.norm_ws(" ".join(kept)),
                "size": round(base_size, 2),
            }
        )
    return blocks


def merge_caption(block: dict, page) -> dict:
    """Absorb continuation blocks so "(a) ..." and "(b) ..." stay one caption."""
    text = block["text"]
    rect = list(block["rect"])
    for candidate in page.get_text("dict")["blocks"]:
        if candidate.get("type") != 0:
            continue
        lines = candidate.get("lines") or []
        if not lines:
            continue
        first = line_text(lines[0])
        if not first or CAPTION_RE.match(first) or TABLE_RE.match(first):
            continue
        if abs(line_size(lines[0]) - block["size"]) > 0.3:
            continue
        if not (CONT_RE.match(first) or text.rstrip().endswith(",")):
            continue
        crect = [float(value) for value in candidate.get("bbox", rect)]
        vertical_gap = crect[1] - rect[3]
        shared = overlap(crect[0], crect[2], rect[0], rect[2])
        if -1 <= vertical_gap <= 6 and shared > 0.5 * min(crect[2] - crect[0], rect[2] - rect[0]):
            text = text + " " + block_text(candidate)
            rect = [min(rect[0], crect[0]), rect[1], max(rect[2], crect[2]), max(rect[3], crect[3])]
    return {**block, "text": text, "rect": [round(value, 2) for value in rect]}


def caption_candidates(rect: list[float], captions: list[dict]) -> list[tuple[int, float, int]]:
    """(position, gap, caption index) for captions that plausibly label this picture.

    In a tight two-column layout the figure printed after a caption sits as close
    to it as the figure it labels, so position outranks distance: a caption under
    the picture always beats a caption above it, however near that one is.
    """
    found = []
    for index, caption in enumerate(captions):
        crect = caption["rect"]
        shared = overlap(crect[0], crect[2], rect[0], rect[2])
        if shared < 0.3 * max(1.0, min(crect[2] - crect[0], rect[2] - rect[0])):
            continue
        if crect[1] >= rect[3] - 1:
            position, gap = BELOW, crect[1] - rect[3]
        elif crect[3] <= rect[1] + 1:
            position, gap = ABOVE, rect[1] - crect[3]
        else:
            position, gap = INSIDE, 0.0
        if gap > 160:
            continue
        found.append((position + (3 if caption["kind"] == "table" else 0), gap, index))
    return found


def assign_captions(rects: list[list[float]], captions: list[dict]) -> dict[int, dict]:
    """Give each picture the caption that labels it, one caption per picture."""
    pairs = []
    for rect_index, rect in enumerate(rects):
        for position, gap, caption_index in caption_candidates(rect, captions):
            pairs.append((position, gap, rect_index, caption_index))
    pairs.sort()
    used_pictures: set[int] = set()
    used_captions: set[int] = set()
    assigned: dict[int, dict] = {}
    for _position, _gap, rect_index, caption_index in pairs:
        if rect_index in used_pictures or caption_index in used_captions:
            continue
        assigned[rect_index] = captions[caption_index]
        used_pictures.add(rect_index)
        used_captions.add(caption_index)
    return assigned


# --------------------------------------------------------------------------- #
# driver
# --------------------------------------------------------------------------- #


def parse_pages(spec: str | None, total: int) -> list[int]:
    if not spec:
        return list(range(total))
    wanted: set[int] = set()
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            start, _, end = chunk.partition("-")
            wanted.update(range(int(start), int(end) + 1))
        else:
            wanted.add(int(chunk))
    return [index - 1 for index in sorted(wanted) if 1 <= index <= total]


def collect(doc, fitz, Image, pages: list[int], tol: float, min_area: float, allow_render: bool):
    """Read the document and return (pictures, skipped, warnings)."""
    pictures: list[dict] = []
    skipped: list[dict] = []
    warnings: list[str] = []
    for index in pages:
        page = doc[index]
        kept, dropped = page_placements(page, min_area)
        for item in dropped:
            item["page"] = index + 1
            skipped.append(item)
        captions = [merge_caption(block, page) for block in caption_blocks(page)]
        groups = cluster(kept, tol)
        rects = [bbox_of(group) for group in groups]
        assigned = assign_captions(rects, captions)
        for order, group in enumerate(groups):
            caption = assigned.get(order)
            result = assemble(group, doc, page, fitz, Image, allow_render)
            pictures.append(
                {
                    "page": index + 1,
                    "rect": rects[order],
                    "caption_block": caption,
                    "mid_x": page.rect.width / 2.0,
                    **result,
                }
            )
        if not kept and page.get_drawings():
            warnings.append(
                "第 %d 页没有位图，但有 %d 条矢量绘图：该页的图是矢量图，本脚本不处理（不要用截图冒充原图）"
                % (index + 1, len(page.get_drawings()))
            )
    # Reading order: page first, then the left column before the right one,
    # then top to bottom. PDF draw order jumps around and must not decide it.
    pictures.sort(
        key=lambda picture: (
            picture["page"],
            picture["rect"][0] > picture["mid_x"],
            round(picture["rect"][1], 1),
            picture["rect"][0],
        )
    )
    return pictures, skipped, warnings


def label_of(picture: dict, warnings: list[str]) -> tuple[str | None, str, str]:
    block = picture.get("caption_block")
    if not block:
        warnings.append(
            "第 %d 页的图（区域 %s）没找到图注：请人工确认它是 Fig. 几再改名"
            % (picture["page"], picture["rect"])
        )
        return None, "图（第 %d 页）" % picture["page"], ""
    return block["number"], block["label"], block["text"]


def target_name(number: str | None, page: int, seen: set[str], ext: str) -> str:
    stem = "fig%s" % number if number else "fig_p%d" % page
    name = "%s.%s" % (stem, ext)
    suffix = 2
    while name in seen:
        name = "%s_%d.%s" % (stem, suffix, ext)
        suffix += 1
    seen.add(name)
    return name


def describe(picture: dict) -> str:
    rect = picture["rect"]
    if picture["image"] is not None:
        width_px, height_px = picture["image"].size
    elif picture["pixmap"] is not None:
        width_px, height_px = picture["pixmap"].width, picture["pixmap"].height
    else:
        width_px, height_px = 0, 0
    dpi = (width_px / max(1e-6, rect[2] - rect[0]) * 72) if width_px else 0.0
    return "第 %d 页 · 区域 (%s)-(%s) pt · %dx%d px · 约 %.0f dpi" % (
        picture["page"], rect[0], rect[1], width_px, height_px, dpi,
    )


def run_probe(args) -> int:
    fitz = load_fitz()
    Image = load_pil()
    path = Path(args.pdf)
    if not path.is_file():
        common.die("找不到 PDF：%s" % path)
    doc = fitz.open(str(path))
    pages = parse_pages(args.pages, doc.page_count)
    pictures, skipped, warnings = collect(doc, fitz, Image, pages, args.tol, args.min_area, False)

    payload = {
        "pdf": str(path),
        "pages": doc.page_count,
        "figures": [],
        "skipped": skipped,
        "warnings": [],
    }
    for index, picture in enumerate(pictures, 1):
        number, label, caption = label_of(picture, warnings)
        entry = {
            "index": index,
            "page": picture["page"],
            "number": number,
            "label": label,
            "caption": caption,
            "rect": picture["rect"],
            "composed": picture["kind"],
            "bands": [
                {"xref": band["xref"], "px": band["px"], "rect": band["rect"]}
                for band in picture["bands"]
            ],
            "note": picture["note"],
        }
        payload["figures"].append(entry)
        if args.json:
            continue
        print("[%d] %s  %s" % (index, label, describe(picture)))
        print("      方式：%s，%d 块" % (picture["kind"], len(entry["bands"])))
        for band in entry["bands"]:
            print("      xref=%s %dx%d rect=%s" % (band["xref"], band["px"][0], band["px"][1], band["rect"]))
        print("      图注：%s" % (common.display_width(caption) if caption else "（未找到）"))
        if picture["note"]:
            print("      注意：%s" % picture["note"])

    payload["warnings"] = warnings
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if skipped:
        print("")
        print("忽略的小位图 %d 个（logo / 线条 / 图标）：" % len(skipped))
        for item in skipped[:8]:
            print("  第 %d 页 xref=%d %dx%d · %s" % (item["page"], item["xref"], item["px"][0], item["px"][1], item["reason"]))
    for warning in warnings:
        print("警告：%s" % warning)
    print("")
    print("共识别 %d 张完整图（按图号成组，不是图块数）。extract 会把每张图写成一个文件。" % len(pictures))
    return 0


def source_line(entry: dict) -> str:
    xrefs = "+".join(str(band["xref"]) for band in entry["bands"])
    if entry["composed"] == "single":
        return "论文 %s，PDF 第 %d 页位图 xref=%s 原始字节导出（未裁剪、未重存）" % (
            entry["label"], entry["page"], xrefs,
        )
    if entry["composed"] == "render":
        return "论文 %s，PDF 第 %d 页区域按原分辨率渲染（分带无法无损拼接：完整，但不是原字节）" % (
            entry["label"], entry["page"],
        )
    return (
        "论文 %s，PDF 第 %d 页位图 xref=%s 共 %d 块无缝拼接为一张（无缩放、无重采样、无重叠），"
        "PNG 无损；未裁剪、未重压缩"
        % (entry["label"], entry["page"], xrefs, len(entry["bands"]))
    )


def run_extract(args) -> int:
    fitz = load_fitz()
    Image = load_pil()
    path = Path(args.pdf)
    if not path.is_file():
        common.die("找不到 PDF：%s" % path)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(path))
    pages = parse_pages(args.pages, doc.page_count)
    pictures, skipped, warnings = collect(doc, fitz, Image, pages, args.tol, args.min_area, args.allow_render)

    manifest = {
        "generator": "paper-tutor/figures.py",
        "pdf": {"path": str(path), "pages": doc.page_count, "bytes": path.stat().st_size},
        "figures": [],
        "skipped": skipped,
        "warnings": [],
    }
    snippets = []
    unresolved = 0
    written: set[str] = set()

    for index, picture in enumerate(pictures, 1):
        number, label, caption = label_of(picture, warnings)
        kind = picture["kind"]
        entry = {
            "index": index,
            "page": picture["page"],
            "number": number,
            "label": label,
            "caption": caption,
            "rect": picture["rect"],
            "composed": kind,
            "bands": [
                {
                    "xref": band["xref"],
                    "px": band["px"],
                    "rect": band["rect"],
                    **({"offset": band["offset"]} if band.get("offset") is not None else {}),
                }
                for band in picture["bands"]
            ],
            "note": picture["note"],
        }
        if kind == "unresolved":
            unresolved += 1
            warnings.append("第 %d 页的图无法完整导出：%s" % (picture["page"], picture["note"]))
            manifest["figures"].append(entry)
            print("未能导出：第 %d 页 %s（%s）" % (picture["page"], label, picture["note"]))
            continue

        name = target_name(number, picture["page"], written, picture["ext"])
        target = out_dir / name
        if kind == "single":
            target.write_bytes(picture["raw"])
        elif kind == "render":
            picture["pixmap"].save(str(target))
        else:
            picture["image"].save(str(target), format="PNG", optimize=True)
        raw = target.read_bytes()
        with Image.open(io.BytesIO(raw)) as probe:
            width_px, height_px = probe.size
        entry.update(
            {
                "file": name,
                "path": "%s/%s" % (out_dir.name, name),
                "sha256": common.sha256_bytes(raw),
                "bytes": len(raw),
                "px": [width_px, height_px],
            }
        )
        manifest["figures"].append(entry)
        snippets.append(
            {
                "path": entry["path"],
                "label": label,
                "caption": caption,
                "sha256": entry["sha256"],
                "source": source_line(entry),
            }
        )
        print("已写出 %s  %dx%d px  （%s，%d 块）  %s" % (name, width_px, height_px, kind, len(entry["bands"]), label))

    manifest["warnings"] = warnings
    manifest_path = Path(args.manifest) if args.manifest else (out_dir / MANIFEST_NAME)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    if args.json:
        print(json.dumps({"manifest": str(manifest_path), "figures": manifest["figures"], "warnings": warnings}, ensure_ascii=False, indent=2))
        return 3 if unresolved else 0

    print("")
    print("清单：%s（每张图的 xref、rect、sha256、拼接偏移都在里面）" % manifest_path)
    if snippets:
        print("")
        print("把下面这些条目贴进 data.json 对应段落的 figures 数组。alt 请自己补一整句，描述整张图在说什么，不要写 (a)/(b) 分栏：")
        print(json.dumps(snippets, ensure_ascii=False, indent=2))
    for warning in warnings:
        print("警告：%s" % warning)
    return 3 if unresolved else 0


def main() -> int:
    common.force_utf8_stdout()
    parser = argparse.ArgumentParser(description="把 PDF 里的一张图导出成一张完整图片（被拆开的图块会自动拼回）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    def shared(target: argparse.ArgumentParser) -> None:
        target.add_argument("--pdf", required=True, help="论文 PDF 路径")
        target.add_argument("--pages", help="只处理这些页，如 1-3 或 2,4（默认全部）")
        target.add_argument(
            "--tol",
            type=float,
            default=DEFAULT_TOL,
            help="判定“同属一张图”的最大间隙，单位 pt（默认 %s）" % DEFAULT_TOL,
        )
        target.add_argument(
            "--min-area",
            type=float,
            default=DEFAULT_MIN_AREA,
            help="小于页面这个百分比的位图视为装饰（默认 %s）" % DEFAULT_MIN_AREA,
        )
        target.add_argument("--json", action="store_true", help="输出机器可读结果")

    probe = sub.add_parser("probe", help="只报告：有哪些图、各由哪些图块组成、候选图注")
    shared(probe)
    probe.set_defaults(func=run_probe)

    extract = sub.add_parser("extract", help="一张图一个文件，并写 figures/_manifest.json")
    shared(extract)
    extract.add_argument("--out", default="figures", help="输出目录（默认 figures/）")
    extract.add_argument("--manifest", help="清单路径（默认 <out>/_manifest.json）")
    extract.add_argument(
        "--allow-render",
        action="store_true",
        help="实在无法逐像素拼接时，允许按页内区域渲染一次（完整，但不是原字节；清单会标注）",
    )
    extract.set_defaults(func=run_extract)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
