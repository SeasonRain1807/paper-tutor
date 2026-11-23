"""Shared helpers for the paper-tutor close-reading scripts.

Kept dependency-free (standard library only) so the skill runs in any
Python 3.10+ environment the session provides.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

KINDS = ("body", "abstract", "caption", "equation", "footnote", "quote", "reference")

KIND_LABEL = {
    "body": "正文",
    "abstract": "摘要",
    "caption": "图表标题",
    "equation": "公式",
    "footnote": "脚注",
    "quote": "引文",
    "reference": "文献",
}

REQUIRED_META = ("title_en", "title_zh", "one_line", "argument_map", "source_note")
REQUIRED_NOTE_FIELDS = ("summary", "function", "position")

# Figures embedded in a paragraph. `path` is required; everything else is
# optional metadata that must never be baked into the image itself.
FIGURE_KEYS = ("path", "label", "caption", "alt", "sha256", "source", "note")

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".avif", ".svg")

MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".avif": "image/avif",
    ".svg": "image/svg+xml",
}

WS_RE = re.compile(r"\s+")
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
SENT_ZH_RE = re.compile(r"[。！？…]+")
SENT_EN_RE = re.compile(r"(?<!\b[A-Z])(?<!\bet al)(?<!\be\.g)(?<!\bi\.e)(?<!\bvs)(?<!\bFig)(?<!\bNo)(?<!\bDr)(?<!\bcf)(?<!\bal)[.!?](?=\s|$)")


class DataError(Exception):
    """Raised when data.json cannot be parsed or fails structural validation."""


def read_json(path: Path) -> dict:
    """Read a JSON file, tolerating a UTF-8 BOM."""
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raise DataError(f"找不到数据文件：{path}")
    except OSError as exc:
        raise DataError(f"无法读取 {path}：{exc}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DataError(
            f"{path} 不是合法 JSON：第 {exc.lineno} 行第 {exc.colno} 列，{exc.msg}"
        )
    if not isinstance(data, dict):
        raise DataError(f"{path} 的顶层必须是对象（{{...}}），实际是 {type(data).__name__}")
    return data


def norm_ws(text: str) -> str:
    """Collapse all whitespace runs to one space and strip.

    Used for verbatim comparison so that reflowing a paragraph does not count
    as editing it. Wording, punctuation and casing are untouched.
    """
    return WS_RE.sub(" ", text.replace("\u00a0", " ")).strip()


def non_empty(value) -> bool:
    return isinstance(value, str) and value.strip() != ""


def validate(data: dict, *, strict: bool = True) -> list[str]:
    """Structural validation shared by the builder and the checker."""
    errors: list[str] = []
    meta = data.get("meta")
    if not isinstance(meta, dict):
        errors.append("meta 缺失或不是对象")
        meta = {}
    for key in REQUIRED_META:
        if key == "argument_map":
            if not isinstance(meta.get(key), list) or not meta.get(key):
                errors.append("meta.argument_map 必须是非空数组")
        elif not non_empty(meta.get(key)):
            errors.append(f"meta.{key} 缺失或为空")

    sections = data.get("sections")
    section_ids: list[str] = []
    if not isinstance(sections, list) or not sections:
        errors.append("sections 必须是非空数组")
        sections = []
    for index, section in enumerate(sections, 1):
        if not isinstance(section, dict):
            errors.append(f"sections[{index}] 不是对象")
            continue
        sid = section.get("id")
        if not non_empty(sid):
            errors.append(f"sections[{index}].id 缺失")
        elif not re.fullmatch(r"[a-z][a-z0-9_-]*", sid):
            errors.append(f"sections[{index}].id {sid!r} 必须是 kebab/snake 形式的小写 id")
        else:
            section_ids.append(sid)
        if not non_empty(section.get("title_en")):
            errors.append(f"sections[{index}].title_en 缺失")
        if not non_empty(section.get("title_zh")):
            errors.append(f"sections[{index}].title_zh 缺失")
    duplicated = {sid for sid in section_ids if section_ids.count(sid) > 1}
    for sid in sorted(duplicated):
        errors.append(f"sections 中 id {sid!r} 重复")

    paragraphs = data.get("paragraphs")
    if not isinstance(paragraphs, list) or not paragraphs:
        errors.append("paragraphs 必须是非空数组")
        paragraphs = []

    seen_ids: set[str] = set()
    for index, para in enumerate(paragraphs, 1):
        where = f"paragraphs[{index}]"
        if not isinstance(para, dict):
            errors.append(f"{where} 不是对象")
            continue
        pid = para.get("id")
        if not non_empty(pid):
            errors.append(f"{where}.id 缺失")
        elif not re.fullmatch(r"p\d+", pid):
            errors.append(f"{where}.id {pid!r} 必须形如 p1、p2")
        elif pid in seen_ids:
            errors.append(f"段落 id {pid!r} 重复")
        else:
            seen_ids.add(pid)
        if para.get("section") not in section_ids:
            errors.append(f"{where}（{pid}）的 section {para.get('section')!r} 不在 sections 中")
        kind = para.get("kind")
        if kind not in KINDS:
            errors.append(f"{where}（{pid}）的 kind {kind!r} 必须是 {', '.join(KINDS)} 之一")
        for field in ("en", "zh"):
            if not non_empty(para.get(field)):
                errors.append(f"{where}（{pid}）的 {field} 为空")
        analysis = para.get("analysis")
        if not isinstance(analysis, dict):
            errors.append(f"{where}（{pid}）的 analysis 缺失或不是对象")
            continue
        for field in REQUIRED_NOTE_FIELDS:
            if not non_empty(analysis.get(field)):
                errors.append(f"{where}（{pid}）的 analysis.{field} 为空")
        terms = analysis.get("terms")
        if terms is not None:
            if not isinstance(terms, list):
                errors.append(f"{where}（{pid}）的 analysis.terms 必须是数组")
            else:
                for item in terms:
                    if not isinstance(item, dict) or not non_empty(item.get("en")) or not non_empty(item.get("zh")):
                        errors.append(f"{where}（{pid}）的 analysis.terms 每项都要有 en 和 zh")
        questions = analysis.get("questions")
        if questions is not None and not isinstance(questions, list):
            errors.append(f"{where}（{pid}）的 analysis.questions 必须是数组")

        figures = para.get("figures")
        if figures is not None:
            if not isinstance(figures, list):
                errors.append(f"{where}（{pid}）的 figures 必须是数组")
            else:
                for fno, fig in enumerate(figures, 1):
                    fwhere = f"{where}（{pid}）.figures[{fno}]"
                    if not isinstance(fig, dict):
                        errors.append(f"{fwhere} 不是对象")
                        continue
                    if not non_empty(fig.get("path")):
                        errors.append(f"{fwhere}.path 缺失（必须给出图片文件路径）")
                    elif not str(fig["path"]).lower().endswith(IMAGE_EXTS):
                        errors.append(
                            f"{fwhere}.path {fig['path']!r} 的扩展名必须是 {', '.join(IMAGE_EXTS)} 之一"
                        )
                    for key in ("label", "caption", "alt", "source", "note"):
                        if fig.get(key) is not None and not isinstance(fig.get(key), str):
                            errors.append(f"{fwhere}.{key} 必须是字符串")
                    sha = fig.get("sha256")
                    if sha is not None and not re.fullmatch(r"[0-9a-f]{64}", str(sha)):
                        errors.append(f"{fwhere}.sha256 必须是 64 位小写十六进制")

    # argument_map paragraph references
    by_id = {para.get("id") for para in paragraphs if isinstance(para, dict)}
    for index, stage in enumerate(meta.get("argument_map") or [], 1):
        if not isinstance(stage, dict):
            errors.append(f"meta.argument_map[{index}] 不是对象")
            continue
        if not non_empty(stage.get("stage")):
            errors.append(f"meta.argument_map[{index}].stage 缺失")
        paras = stage.get("paras")
        if not non_empty(paras):
            errors.append(f"meta.argument_map[{index}].paras 缺失")
            continue
        for ref in parse_para_refs(paras):
            if ref not in by_id:
                errors.append(f"meta.argument_map[{index}].paras 引用了不存在的段落 {ref}")

    if strict and not errors:
        order = [int(para["id"][1:]) for para in paragraphs]
        if order != list(range(1, len(order) + 1)):
            errors.append("paragraphs 的 id 必须从 p1 开始连续递增，当前为 " + ", ".join(f"p{n}" for n in order[:12]))
    return errors


def parse_para_refs(text: str) -> list[str]:
    """Expand 'P4–P6' / 'P4-P6' / 'P9' into ['p4', 'p5', 'p6']."""
    refs: list[str] = []
    for match in re.finditer(r"[Pp]\s*(\d+)(?:\s*[–\-~—]\s*[Pp]?\s*(\d+))?", text):
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else start
        if end < start:
            start, end = end, start
        if end - start > 400:
            end = start + 400
        refs.extend(f"p{n}" for n in range(start, end + 1))
    return refs


def cjk_count(text: str) -> int:
    return len(CJK_RE.findall(text))


def en_word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'’\-]*", text))


def en_sentences(text: str) -> int:
    return max(1, len(SENT_EN_RE.findall(text)))


def zh_sentences(text: str) -> int:
    return max(1, len(SENT_ZH_RE.findall(text)))


def load_data(path: Path) -> dict:
    """Read and structurally validate a data.json, raising DataError."""
    data = read_json(path)
    errors = validate(data)
    if errors:
        raise DataError("\n".join(errors))
    return data


def die(message: str, code: int = 2) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def display_width(text: str) -> str:
    """A short preview for reports."""
    flat = norm_ws(text)
    return flat if len(flat) <= 90 else flat[:90] + "…"


def force_utf8_stdout() -> None:
    """Print Chinese reliably on Windows consoles that default to GBK."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError, OSError):
            pass


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sniff_image_mime(raw: bytes, path: Path) -> str:
    """Identify the real container by magic bytes; fall back to the extension.

    Never used to convert or re-encode: it only decides the `data:` MIME type
    so the browser decodes the untouched bytes.
    """
    head = raw[:16]
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(b"BM"):
        return "image/bmp"
    stripped = raw[:256].lstrip()
    if stripped.startswith(b"<svg") or stripped.startswith(b"<?xml"):
        return "image/svg+xml"
    if head[4:12] in (b"ftypavif", b"ftypavis"):
        return "image/avif"
    return MIME_BY_EXT.get(path.suffix.lower(), "application/octet-stream")


def figures_of(para: dict) -> list[dict]:
    """Figures attached to a paragraph, tolerating a missing key."""
    figures = para.get("figures")
    if not isinstance(figures, list):
        return []
    return [fig for fig in figures if isinstance(fig, dict) and non_empty(fig.get("path"))]


def count_figures(data: dict) -> int:
    return sum(len(figures_of(para)) for para in data.get("paragraphs") or [] if isinstance(para, dict))

