from __future__ import annotations

import re
from collections import Counter
from datetime import date, timedelta

from backend.services.schedule_service.academic_calendar_models import CalendarOverrides
from backend.services.schedule_service.log_utils import logger

_YMD_RE = re.compile(r"(?P<y>20\d{2})[./\-](?P<m>\d{1,2})[./\-](?P<d>\d{1,2})")
_YMD_CN_RE = re.compile(r"(?P<y>20\d{2})年(?P<m>\d{1,2})月(?P<d>\d{1,2})日")
_MD_CN_RE = re.compile(r"(?P<m>\d{1,2})月(?P<d>\d{1,2})日")
_MD_LIST_CN_RE = re.compile(r"(?P<m>\d{1,2})月(?P<ds>\d{1,2}(?:[、,，]\d{1,2})+)日")
_RANGE_CN_RE = re.compile(
    r"(?P<m1>\d{1,2})月(?P<d1>\d{1,2})日(?:至|到|—|–|-|~)(?:(?P<m2>\d{1,2})月)?(?P<d2>\d{1,2})日"
)
_MOVE_RE = re.compile(
    r"(?P<src>\d{1,2}月\d{1,2}日).*?(?:调至|调整至|顺延至|改为|补到|补上|补课于|补课在|补课至|安排至)(?P<dst>\d{1,2}月\d{1,2}日)"
)
_CLASS_START_RE = re.compile(r"(?P<m>\d{1,2})月(?P<d>\d{1,2})日?(?:本科生|研究生)?上课")
_MAKEUP_WEEKDAY_RE = re.compile(
    r"(?P<m>\d{1,2})月(?P<d>\d{1,2})日上(?:单周|双周)?周(?P<w>[一二三四五六日天])的课"
)
_HOLIDAY_KEYWORDS = (
    "停课",
    "不上课",
    "放假",
    "休假",
    "补休",
    "劳动节",
    "清明节",
    "端午节",
    "中秋节",
    "国庆节",
    "元旦",
    "春节",
)
_WEEKDAY_MAP = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}


def _norm(s: str) -> str:
    s = (s or "").replace("\u3000", " ").replace("\xa0", " ").replace(" ", "")
    s = re.sub(r"[\x00-\x1f]+", "", s)
    return s


def _infer_default_year(text: str) -> int:
    years: list[int] = []
    for m in re.finditer(r"20\d{2}", text):
        try:
            years.append(int(m.group(0)))
        except Exception:
            continue
    if not years:
        return date.today().year
    c = Counter(years)
    return c.most_common(1)[0][0]


def _mk_date(y: int, m: int, d: int) -> date | None:
    try:
        return date(int(y), int(m), int(d))
    except Exception:
        return None


def _expand_range(y: int, m1: int, d1: int, m2: int, d2: int) -> list[date]:
    a = _mk_date(y, m1, d1)
    b = _mk_date(y, m2, d2)
    if not a or not b:
        return []
    if b < a:
        return []
    days: list[date] = []
    cur = a
    while cur <= b:
        days.append(cur)
        cur = cur + timedelta(days=1)
    return days


def parse_calendar_overrides(
    text: str,
    *,
    source_url: str | None = None,
    source_pdf_url: str | None = None,
    source_pdf_path: str | None = None,
    extracted_pages: int | None = None,
) -> CalendarOverrides:
    raw = text or ""
    s = _norm(raw)
    default_year = _infer_default_year(s)
    lines = [_norm(line) for line in raw.splitlines() if _norm(line)]
    week1_monday = _infer_week1_monday(lines, default_year)

    cancel_days: set[date] = set()
    move_rules: list[tuple[date, date]] = []
    explicit_holidays: set[date] = set()

    for line in lines:
        for m in _YMD_RE.finditer(line):
            y, mo, da = int(m.group("y")), int(m.group("m")), int(m.group("d"))
            d0 = _mk_date(y, mo, da)
            if d0 and _is_cancel_context(line, m.start(), m.end()):
                cancel_days.add(d0)
                explicit_holidays.add(d0)

        for m in _YMD_CN_RE.finditer(line):
            y, mo, da = int(m.group("y")), int(m.group("m")), int(m.group("d"))
            d0 = _mk_date(y, mo, da)
            if d0 and _is_cancel_context(line, m.start(), m.end()):
                cancel_days.add(d0)
                explicit_holidays.add(d0)

        for m in _MD_LIST_CN_RE.finditer(line):
            mo = int(m.group("m"))
            ds = re.split(r"[、,，]", m.group("ds"))
            if not _is_cancel_context(line, m.start(), m.end()):
                continue
            for d_str in ds:
                try:
                    da = int(d_str)
                except Exception:
                    continue
                d0 = _mk_date(default_year, mo, da)
                if d0:
                    cancel_days.add(d0)
                    explicit_holidays.add(d0)

        for m in _RANGE_CN_RE.finditer(line):
            mo1 = int(m.group("m1"))
            da1 = int(m.group("d1"))
            mo2 = int(m.group("m2") or mo1)
            da2 = int(m.group("d2"))
            if not _is_cancel_context(line, m.start(), m.end()):
                continue
            for d0 in _expand_range(default_year, mo1, da1, mo2, da2):
                cancel_days.add(d0)
                explicit_holidays.add(d0)

    for line in lines:
        if not any(k in line for k in _HOLIDAY_KEYWORDS):
            continue
        line_dates = _extract_line_dates(line, default_year)
        if not line_dates and "清明节" in line:
            partial = re.search(r"(?P<d>\d{1,2})日清明节", line)
            if partial:
                d0 = _mk_date(default_year, 4, int(partial.group("d")))
                if d0:
                    line_dates.append(d0)
        for d0 in line_dates:
            cancel_days.add(d0)
            explicit_holidays.add(d0)

    for m in _MOVE_RE.finditer(s):
        src_md = m.group("src")
        dst_md = m.group("dst")
        src = _parse_md(default_year, src_md)
        dst = _parse_md(default_year, dst_md)
        if src and dst:
            move_rules.append((src, dst))

    for line in lines:
        move = _parse_makeup_weekday_line(line, default_year, cancel_days)
        if move is not None:
            src, dst = move
            cancel_days.add(src)
            move_rules.append((src, dst))

    _apply_term_start_cancellations(lines, default_year, cancel_days)
    _apply_substitute_holidays(explicit_holidays, cancel_days)
    _expand_bridge_holidays(explicit_holidays, move_rules, cancel_days)

    cancel_days, move_rules = _dedupe_and_sanitize(cancel_days, move_rules)

    logger.info(
        "calendar.parse: cancel_days=%d move_rules=%d year=%d",
        len(cancel_days),
        len(move_rules),
        default_year,
    )

    return CalendarOverrides(
        cancel_days=cancel_days,
        move_rules=move_rules,
        week1_monday=week1_monday,
        source_url=source_url,
        source_pdf_url=source_pdf_url,
        source_pdf_path=source_pdf_path,
        extracted_pages=extracted_pages,
    )


def _parse_md(default_year: int, s: str) -> date | None:
    m = _MD_CN_RE.search(s)
    if not m:
        return None
    mo = int(m.group("m"))
    da = int(m.group("d"))
    return _mk_date(default_year, mo, da)


def _is_cancel_context(text: str, start: int, end: int) -> bool:
    window = text[max(0, start - 24) : min(len(text), end + 24)]
    return any(
        k in window
        for k in (
            "停课",
            "不上课",
            "放假",
            "休假",
            "法定节假日",
            "假期",
            "补休",
            "劳动节",
            "清明节",
            "端午节",
            "中秋节",
            "国庆节",
            "元旦",
            "春节",
        )
    )


def _extract_line_dates(line: str, default_year: int) -> list[date]:
    out: list[date] = []
    for m in _YMD_CN_RE.finditer(line):
        d0 = _mk_date(int(m.group("y")), int(m.group("m")), int(m.group("d")))
        if d0:
            out.append(d0)
    for m in _MD_LIST_CN_RE.finditer(line):
        mo = int(m.group("m"))
        for d_str in re.split(r"[、,，]", m.group("ds")):
            try:
                da = int(d_str)
            except Exception:
                continue
            d0 = _mk_date(default_year, mo, da)
            if d0:
                out.append(d0)
    for m in _RANGE_CN_RE.finditer(line):
        mo1 = int(m.group("m1"))
        da1 = int(m.group("d1"))
        mo2 = int(m.group("m2") or mo1)
        da2 = int(m.group("d2"))
        out.extend(_expand_range(default_year, mo1, da1, mo2, da2))
    for m in _MD_CN_RE.finditer(line):
        d0 = _mk_date(default_year, int(m.group("m")), int(m.group("d")))
        if d0:
            out.append(d0)
    deduped: list[date] = []
    seen: set[date] = set()
    for d0 in out:
        if d0 in seen:
            continue
        seen.add(d0)
        deduped.append(d0)
    return deduped


def _parse_makeup_weekday_line(
    line: str, default_year: int, cancel_days: set[date]
) -> tuple[date, date] | None:
    m = _MAKEUP_WEEKDAY_RE.search(line)
    if not m:
        return None
    dst = _mk_date(default_year, int(m.group("m")), int(m.group("d")))
    if not dst:
        return None
    target_weekday = _WEEKDAY_MAP.get(m.group("w"))
    if target_weekday is None:
        return None
    candidates = [
        d
        for d in cancel_days
        if d < dst and d.weekday() == target_weekday and (dst - d).days <= 21
    ]
    if candidates:
        return (max(candidates), dst)
    delta = (dst.weekday() - target_weekday) % 7
    delta = delta or 7
    src = dst - timedelta(days=delta)
    return (src, dst)


def _apply_term_start_cancellations(
    lines: list[str], default_year: int, cancel_days: set[date]
) -> None:
    monday = _infer_week1_monday(lines, default_year)
    if monday is None:
        return
    starts = _extract_class_start_days(lines, default_year)
    if not starts:
        return
    start = min(starts)
    cur = monday
    while cur < start:
        if cur.weekday() < 5:
            cancel_days.add(cur)
        cur = cur + timedelta(days=1)


def _extract_class_start_days(lines: list[str], default_year: int) -> list[date]:
    starts: list[date] = []
    for line in lines:
        m = _CLASS_START_RE.search(line)
        if not m:
            continue
        d0 = _mk_date(default_year, int(m.group("m")), int(m.group("d")))
        if d0:
            starts.append(d0)
    return starts


def _infer_week1_monday(lines: list[str], default_year: int) -> date | None:
    starts = _extract_class_start_days(lines, default_year)
    if not starts:
        return None
    start = min(starts)
    return start - timedelta(days=start.weekday())


def _apply_substitute_holidays(
    explicit_holidays: set[date], cancel_days: set[date]
) -> None:
    for d0 in explicit_holidays:
        if d0.weekday() == 6:
            cancel_days.add(d0 + timedelta(days=1))


def _expand_bridge_holidays(
    explicit_holidays: set[date],
    move_rules: list[tuple[date, date]],
    cancel_days: set[date],
) -> None:
    for src, _ in move_rules:
        anchors = [d for d in explicit_holidays if 0 <= (src - d).days <= 4]
        if not anchors:
            continue
        start = min(anchors)
        cur = start
        while cur <= src:
            if cur.weekday() < 5:
                cancel_days.add(cur)
            cur = cur + timedelta(days=1)


def _dedupe_and_sanitize(
    cancel_days: set[date], move_rules: list[tuple[date, date]]
) -> tuple[set[date], list[tuple[date, date]]]:
    cleaned_moves: list[tuple[date, date]] = []
    seen: set[tuple[date, date]] = set()
    for src, dst in move_rules:
        if src == dst:
            continue
        key = (src, dst)
        if key in seen:
            continue
        seen.add(key)
        cleaned_moves.append(key)

    override_days = {dst for _, dst in cleaned_moves}
    cleaned_cancel = {d for d in cancel_days if d not in override_days}
    return cleaned_cancel, cleaned_moves
