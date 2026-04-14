from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class SemanticChunk:
    text: str
    section_path: tuple[str, ...]


_CHAPTER_RE = re.compile(r"^第[一二三四五六七八九十百千万零0-9]+[编篇章]\b")
_SECTION_RE = re.compile(r"^第[一二三四五六七八九十百千万零0-9]+节\b")
_NUM_HEADING_RE = re.compile(r"^(?P<num>\d+(?:\.\d+){0,5})\s+")
_CN_ENUM_RE = re.compile(r"^[一二三四五六七八九十]+、")
_CN_PAREN_ENUM_RE = re.compile(r"^（[一二三四五六七八九十]+）")


def semantic_chunk_text(
    text: str,
    *,
    target_size: int = 1200,
    hard_max_size: int = 1600,
    overlap: int = 150,
) -> list[SemanticChunk]:
    s = _normalize_text(text)
    if not s:
        return []

    blocks = _split_blocks(s)
    sections = _group_blocks_by_headings(blocks)

    out: list[SemanticChunk] = []
    for section_path, section_text in sections:
        out.extend(
            _chunk_section(
                section_text,
                section_path=section_path,
                target_size=target_size,
                hard_max_size=hard_max_size,
                overlap=overlap,
            )
        )
    return out


def _normalize_text(text: str) -> str:
    s = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    s = "\n".join(line.rstrip() for line in s.split("\n"))
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _split_blocks(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return parts


def _is_heading_block(block: str) -> bool:
    if "\n" in block:
        return False
    line = block.strip()
    if not line:
        return False
    if len(line) > 120:
        return False
    if _CHAPTER_RE.match(line) or _SECTION_RE.match(line) or _NUM_HEADING_RE.match(line):
        return True
    if _CN_ENUM_RE.match(line) or _CN_PAREN_ENUM_RE.match(line):
        return True
    if _looks_like_all_caps_heading(line):
        return True
    return False


def _heading_level(line: str) -> int:
    if _CHAPTER_RE.match(line):
        return 1
    if _SECTION_RE.match(line):
        return 2
    m = _NUM_HEADING_RE.match(line)
    if m:
        dots = m.group("num").count(".")
        return min(1 + dots, 6)
    if _CN_ENUM_RE.match(line):
        return 2
    if _CN_PAREN_ENUM_RE.match(line):
        return 3
    if _looks_like_all_caps_heading(line):
        return 2
    return 1


def _looks_like_all_caps_heading(line: str) -> bool:
    letters = [c for c in line if "A" <= c <= "Z" or "a" <= c <= "z"]
    if len(letters) < 6:
        return False
    upper = sum(1 for c in letters if "A" <= c <= "Z")
    if upper / len(letters) < 0.85:
        return False
    if any(ch in line for ch in (".", "。", "?", "？", "!", "！", ";", "；")):
        return False
    return True


def _update_section_path(path: list[str], *, level: int, heading: str) -> list[str]:
    level = max(1, int(level))
    if len(path) >= level:
        path = path[: level - 1]
    while len(path) < level - 1:
        path.append("")
    if len(path) == level - 1:
        path.append(heading)
    else:
        path[level - 1] = heading
    path = [p for p in path if p]
    return path


def _group_blocks_by_headings(blocks: list[str]) -> list[tuple[tuple[str, ...], str]]:
    sections: list[tuple[tuple[str, ...], str]] = []
    path: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf
        t = _normalize_text("\n\n".join(buf))
        if t:
            sections.append((tuple(path), t))
        buf = []

    for block in blocks:
        if _is_heading_block(block):
            flush()
            heading = block.strip()
            path = _update_section_path(path, level=_heading_level(heading), heading=heading)
            continue
        buf.append(block)

    flush()
    return sections


def _split_sentences(text: str) -> list[str]:
    s = _normalize_text(text)
    if not s:
        return []
    parts = re.split(r"(?<=[。！？!?；;])\s*", s)
    out: list[str] = []
    for p in parts:
        p = p.strip()
        if p:
            out.append(p)
    return out


def _chunk_section(
    text: str,
    *,
    section_path: tuple[str, ...],
    target_size: int,
    hard_max_size: int,
    overlap: int,
) -> list[SemanticChunk]:
    s = _normalize_text(text)
    if not s:
        return []
    if len(s) <= hard_max_size:
        return [SemanticChunk(text=s, section_path=section_path)]

    sentences = _split_sentences(s)
    if not sentences:
        return [SemanticChunk(text=s[:hard_max_size], section_path=section_path)]

    tail_len = min(max(0, int(overlap)), max(1, hard_max_size // 2))
    chunks: list[str] = []
    buf: list[str] = []
    size = 0
    prev_tail = ""
    content_added = False

    def append_chunk_text(t: str) -> None:
        nonlocal prev_tail
        t = _normalize_text(t)
        if not t:
            return
        chunks.append(t)
        prev_tail = t[-tail_len:] if tail_len > 0 else ""

    def flush() -> None:
        nonlocal buf, size, prev_tail, content_added
        t = _normalize_text("".join(buf))
        if t and content_added:
            append_chunk_text(t)
        buf = []
        size = 0
        content_added = False

        if prev_tail:
            buf.append(prev_tail)
            buf.append("\n")
            size = len(prev_tail) + 1

    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue

        if len(sent) > hard_max_size:
            if buf and content_added:
                flush()
            elif buf:
                buf = []
                size = 0
                content_added = False
            for i in range(0, len(sent), hard_max_size):
                part = sent[i : i + hard_max_size].strip()
                if part:
                    append_chunk_text(part)
            buf = []
            size = 0
            content_added = False
            if prev_tail:
                buf = [prev_tail, "\n"]
                size = len(prev_tail) + 1
            continue

        if size + len(sent) > hard_max_size and buf:
            flush()

        buf.append(sent)
        size += len(sent)
        content_added = True

        if size >= target_size:
            flush()

    if buf and content_added:
        flush()

    return [SemanticChunk(text=c, section_path=section_path) for c in chunks]
