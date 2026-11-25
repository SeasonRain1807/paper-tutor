#!/usr/bin/env python3
"""Fill the `en` placeholders in data.json with the verbatim source text.

Why this exists: every paragraph must carry the paper's English text exactly,
but retyping it is the single largest block of repeated output in a run — in the
shipped demo (templates/精读示例) the English text is 64% of all authored
characters. Write `"en": "@@7"` (1-based paragraph number in source.txt) and let
this script splice the exact text back in.

Usage:
    python autofill.py --source <source.txt> --list
    python autofill.py --data <data.json> --source <source.txt>

`--list` only prints the numbered paragraph list of source.txt (the numbers to
use in the placeholders) and changes nothing; it needs no data.json.

Guards — the file is left untouched and the exit code is 2 when:
    * a placeholder number is out of range for source.txt,
    * two paragraphs claim the same number,
    * the same source paragraph is claimed twice.
After filling, `check.py` remains the authority on verbatim equality.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import common

PLACEHOLDER_RE = re.compile(r"^@@\s*(\d+)\s*$")
PREVIEW = 40


def source_blocks(raw: str) -> list[str]:
    """Blank-line separated blocks, whitespace-normalised.

    Must stay identical to check.py's source_blocks(): that is what makes the
    numbers here mean the same thing as the numbers the checker reports.
    """
    blocks = (common.norm_ws(block) for block in re.split(r"\n\s*\n", raw))
    return [block for block in blocks if block]


def preview(text: str) -> str:
    flat = common.norm_ws(text)
    return flat if len(flat) <= PREVIEW else flat[:PREVIEW] + "…"


def render(data: dict, path: Path) -> bytes:
    """Serialise data.json in the style it was written in.

    BOM and line endings are preserved from the file on disk: rewriting someone's
    data.json must not turn a small edit into a whole-file whitespace diff.
    """
    try:
        original = path.read_bytes()
    except OSError:
        original = b""
    newline = "\r\n" if b"\r\n" in original else "\n"
    text = json.dumps(data, ensure_ascii=False, indent=2).replace("\n", newline) + newline
    prefix = b"\xef\xbb\xbf" if original.startswith(b"\xef\xbb\xbf") else b""
    return prefix + text.encode("utf-8")


def parse_args(argv: list[str]) -> dict:
    options = {"data": "", "source": "", "list": False}
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg in ("-h", "--help"):
            print(__doc__.strip())
            raise SystemExit(0)
        if arg == "--list":
            options["list"] = True
            index += 1
            continue
        if arg in ("--data", "--source"):
            if index + 1 >= len(argv):
                common.die(f"{arg} 后面需要跟一个路径", 2)
            options[arg[2:]] = argv[index + 1]
            index += 2
            continue
        common.die(f"无法识别的参数：{arg}（用 --help 看用法）", 2)
    if not options["source"]:
        common.die(
            "用法：python autofill.py --source <source.txt> --list\n"
            "      python autofill.py --data <data.json> --source <source.txt>",
            2,
        )
    if not options["data"] and not options["list"]:
        common.die("填回原文需要 --data <data.json>（只想看清单就加 --list，可省略 --data）", 2)
    return options


def print_list(blocks: list[str]) -> None:
    print(f"source.txt 共 {len(blocks)} 个文本块（占位符写 @@序号）：")
    for number, block in enumerate(blocks, 1):
        print(f"  @@{number:<3} ({len(block):>5} 字符) {preview(block)}")


def main(argv: list[str] | None = None) -> int:
    common.force_utf8_stdout()
    options = parse_args(list(sys.argv[1:] if argv is None else argv))
    source_path = Path(options["source"])
    try:
        raw = source_path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        common.die(f"找不到源文件：{source_path}", 2)
    except OSError as exc:
        common.die(f"无法读取 {source_path}：{exc}", 2)

    blocks = source_blocks(raw)
    if not blocks:
        common.die(f"{source_path} 里没有可用的段落（按空行切段）", 2)

    if options["list"]:
        print_list(blocks)
        return 0

    data_path = Path(options["data"])
    try:
        data = common.read_json(data_path)
    except common.DataError as exc:
        common.die(str(exc), 2)

    paragraphs = data.get("paragraphs")
    if not isinstance(paragraphs, list) or not paragraphs:
        common.die(f"{data_path} 里没有 paragraphs 数组，先按 references/02 写好骨架", 2)

    claimed: dict[int, list[str]] = {}
    pending: list[tuple[dict, int, str]] = []
    errors: list[str] = []
    for index, para in enumerate(paragraphs, 1):
        if not isinstance(para, dict):
            errors.append(f"paragraphs[{index}] 不是对象")
            continue
        pid = str(para.get("id") or f"paragraphs[{index}]")
        value = para.get("en")
        text = value if isinstance(value, str) else ""
        match = PLACEHOLDER_RE.match(text.strip())
        if not match:
            if not text.strip():
                errors.append(f"{pid} 的 en 为空：要么写 \"@@段号\"，要么写逐字原文")
            continue
        number = int(match.group(1))
        if number < 1 or number > len(blocks):
            errors.append(
                f"{pid} 的 en 是 @@{number}，但 source.txt 只有 {len(blocks)} 个文本块"
                "（先跑 --list 看清单）"
            )
            continue
        claimed.setdefault(number, []).append(pid)
        pending.append((para, number, pid))

    for number in sorted(claimed):
        if len(claimed[number]) > 1:
            errors.append(f"@@{number} 被多段同时引用：{', '.join(claimed[number])}")

    if errors:
        print("未填回任何原文，data.json 没有改动：", file=sys.stderr)
        for message in errors:
            print(f"- {message}", file=sys.stderr)
        return 2

    if not pending:
        print("注意：整份 data.json 里没有占位符，什么都没有改。")
        return 0

    for para, number, _pid in pending:
        para["en"] = blocks[number - 1]

    try:
        data_path.write_bytes(render(data, data_path))
    except OSError as exc:
        common.die(f"无法写入 {data_path}：{exc}", 2)

    total = len(paragraphs)
    unclaimed = [n for n in range(1, len(blocks) + 1) if n not in claimed]
    print(
        f"已填回 {len(pending)}/{total} 段的逐字原文"
        f"（source.txt 共 {len(blocks)} 个文本块）→ {data_path}"
    )
    if unclaimed:
        listed = "、".join(f"@@{n}" for n in unclaimed[:6])
        more = " 等" if len(unclaimed) > 6 else ""
        print(
            f"提示：{len(unclaimed)} 个文本块没有被引用（{listed}{more}）。"
            "标题/作者/单位/参考文献这类块本来就该跳过；若是正文段落就是漏段，check.py 会报 coverage。"
        )
    print("下一步：python scripts/check.py --data <data.json> --source <source.txt>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
