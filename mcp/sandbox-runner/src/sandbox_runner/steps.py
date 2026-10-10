"""ハンズオン本文(README.md)から手順を取り出す。

検証担当が本文のコマンドを書き写さずにそのまま実行できるよう、手順ごとのコードブロックに ID を振る。
ID は `<区分>-<番号>#<ブロック番号>`(例: `step-12#1`)。区分は prep(事前準備)/ step(手順)/ cleanup(後片付け)。
「確認ポイント」より前の bash ブロックは操作(action)、後ろの bash ブロックは確認(check)とする。
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

SECTIONS = {"事前準備": "prep", "手順": "step", "後片付け": "cleanup"}
SHELL_LANGS = {"bash", "sh", "shell", "zsh", "console"}
HEADING = re.compile(r"^(#{2,6})\s+(.*?)\s*$")
FENCE = re.compile(r"^(\s*)(`{3,}|~{3,})\s*([\w+-]*)")
STEP_NO = re.compile(r"^手順\s*(\d+)\s*(?:\((発展)\))?\s*[::]\s*(.*)$")
PREP_NO = re.compile(r"^(\d+)\.\s*(.*)$")
CHECK = re.compile(r"\*\*確認ポイント\*\*")


@dataclass
class Block:
    id: str
    role: str  # action | check
    lang: str
    code: str


@dataclass
class Step:
    id: str
    section: str
    title: str
    optional: bool = False
    blocks: list[Block] = field(default_factory=list)
    checks: list[str] = field(default_factory=list)
    expected: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def parse(markdown: str) -> list[Step]:
    steps: list[Step] = []
    section: str | None = None
    current: Step | None = None
    seen_check = False
    cleanup_no = 0
    lines = markdown.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        fence = FENCE.match(line)
        if fence:
            marker, lang = fence.group(2), fence.group(3).lower()
            body: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith(marker):
                body.append(lines[i])
                i += 1
            i += 1
            if current is None:
                continue
            code = "\n".join(body).rstrip("\n")
            if lang in SHELL_LANGS:
                n = len(current.blocks) + 1
                current.blocks.append(Block(f"{current.id}#{n}", "check" if seen_check else "action", lang, code))
            elif seen_check:
                current.expected.append(code)
            continue

        heading = HEADING.match(line)
        if heading:
            level, text = len(heading.group(1)), heading.group(2)
            if level == 2:
                section = SECTIONS.get(text)
                current = None
            elif section:
                step = _new_step(section, level, text, cleanup_no)
                if step:
                    if section == "cleanup":
                        cleanup_no += 1
                    current, seen_check = step, False
                    steps.append(step)
            i += 1
            continue

        if current is not None and CHECK.search(line):
            seen_check = True
            current.checks.append(_paragraph(lines, i))
        i += 1
    return [s for s in steps if s.blocks or s.checks]


def _new_step(section: str, level: int, text: str, cleanup_no: int) -> Step | None:
    title = text.strip("`")
    if section == "step":
        m = STEP_NO.match(text)
        if not m:
            return None  # 「### 1. キューを作成する」のような章見出し
        return Step(f"step-{m.group(1)}", section, m.group(3), optional=bool(m.group(2)))
    if section == "prep":
        m = PREP_NO.match(text)
        return Step(f"prep-{m.group(1)}", section, m.group(2)) if m else None
    if level == 3:
        return Step(f"cleanup-{cleanup_no + 1}", section, title)
    return None


def _paragraph(lines: list[str], start: int) -> str:
    out = []
    for line in lines[start:]:
        if not line.strip() or FENCE.match(line):
            break
        out.append(line.strip())
    return " ".join(out)


def find_block(steps: list[Step], block_id: str) -> tuple[Step, Block]:
    for s in steps:
        for b in s.blocks:
            if b.id == block_id:
                return s, b
    raise KeyError(block_id)
