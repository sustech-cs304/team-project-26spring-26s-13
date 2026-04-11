import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal

import httpx

from .academic_calendar_provider import get_calendar_overrides
from .constants import (
    ACADEMIC_SYSTEM_BASE,
    CourseOccurrence,
    _SUSTECH_CLASS_PERIODS,
    _TIS_WEEK1_MONDAY,
    _cas_login,
    _ensure_file_logging,
    _request_with_retry,
    logger,
)

def _test5_file_path() -> Path:
    root = Path(__file__).resolve().parents[3]
    return root / "test" / "result" / "test5.txt"


def _preview_obj(obj: object, limit: int = 8000) -> str:
    if obj is None:
        return ""
    if isinstance(obj, str):
        s = obj
    else:
        try:
            s = json.dumps(obj, ensure_ascii=False, default=str)
        except Exception:
            s = str(obj)
    if len(s) > limit:
        return s[:limit] + "..."
    return s


def _tis_needs_auth_response(resp: httpx.Response) -> bool:
    if resp.status_code == 401:
        return True

    u = str(resp.url)
    if "/authentication/require" in u:
        return True
    if "cas.sustech.edu.cn" in u or "/cas/login" in u:
        return True

    ct = (resp.headers.get("content-type") or "").lower()

    if "application/json" in ct:
        try:
            txt = resp.text or ""
        except Exception:
            txt = ""
        if "身份认证" in txt or "需要身份认证" in txt or "登录" in txt:
            return True

    if ct.startswith("text/html"):
        try:
            snippet = (resp.text or "").lower()
        except Exception:
            snippet = ""
        if "cas" in snippet and ("login" in snippet or "统一身份认证" in snippet):
            return True

    return False


def _tis_dump_test5(
    *,
    reason: str,
    r_term: httpx.Response | None,
    term_payload: object | None,
    r_kb: httpx.Response | None,
    kb_payload: object | None,
    meetings_count: int,
) -> None:
    try:
        path = _test5_file_path()
        path.parent.mkdir(parents=True, exist_ok=True)

        lines: list[str] = []
        lines.append(f"reason={reason}")
        lines.append(f"meetings_count={meetings_count}")

        if r_term is not None:
            lines.append(f"term.status={r_term.status_code}")
            lines.append(f"term.url={str(r_term.url)}")
            lines.append(f"term.content_type={r_term.headers.get('content-type','')}")

        if r_kb is not None:
            lines.append(f"kb.status={r_kb.status_code}")
            lines.append(f"kb.url={str(r_kb.url)}")
            lines.append(f"kb.content_type={r_kb.headers.get('content-type','')}")

        if isinstance(kb_payload, dict):
            lines.append(f"kb_payload.type=dict keys={sorted(list(kb_payload.keys()))[:80]}")
        elif isinstance(kb_payload, list):
            lines.append(f"kb_payload.type=list len={len(kb_payload)}")
        else:
            lines.append(f"kb_payload.type={type(kb_payload).__name__}")

        interesting = 0
        samples: list[dict[str, object]] = []
        for d in _tis_iter_dicts(kb_payload):
            if not isinstance(d, dict):
                continue
            if not any(k in d for k in ("SKSJ", "SKSJ_EN", "KEY", "ZC", "KSJC", "JSJC", "RWH")):
                continue
            interesting += 1
            if len(samples) < 8:
                samples.append(
                    {
                        k: d.get(k)
                        for k in ("RWH", "KEY", "XB", "KSJC", "JSJC", "ZC", "SKSJ", "SKSJ_EN")
                        if k in d
                    }
                )

        lines.append(f"kb.interesting_dicts={interesting}")
        for i, s in enumerate(samples):
            lines.append(f"kb.sample[{i}]={_preview_obj(s, 2000)}")

        if term_payload is not None:
            lines.append("term.payload.preview=" + _preview_obj(term_payload, 2500))
        if kb_payload is not None:
            lines.append("kb.payload.preview=" + _preview_obj(kb_payload, 2500))

        path.write_text("\n".join(lines), encoding="utf-8")
    except Exception:
        logger.exception("tis.dump_test5 failed")


def _tis_iter_dicts(obj: object):
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _tis_iter_dicts(v)
        return

    if isinstance(obj, list):
        for item in obj:
            yield from _tis_iter_dicts(item)
        return

    if isinstance(obj, str):
        s = obj.strip()
        if s.startswith("{") or s.startswith("["):
            try:
                parsed = json.loads(s)
            except Exception:
                return
            yield from _tis_iter_dicts(parsed)


def _tis_extract_xn_xq(payload: object) -> tuple[str, str] | None:
    if isinstance(payload, dict):
        xn = payload.get("xn") or payload.get("XN") or payload.get("xndm") or payload.get("XNDM")
        xq = payload.get("xq") or payload.get("XQ") or payload.get("xqdm") or payload.get("XQDM")
        if isinstance(xn, str) and isinstance(xq, (str, int)) and xn.strip():
            return xn.strip(), str(xq).strip()

    text = str(payload or "")
    m = re.search(r"\b(20\d{2}-20\d{2})\b", text)
    if not m:
        return None
    xn = m.group(1)
    m2 = re.search(r"\b(xq|XQ|xqdm|XQDM)\s*[:=]\s*['\"]?(1|2)['\"]?\b", text)
    if m2:
        return xn, m2.group(2)
    return None


def _tis_parse_weekday(v: object) -> int | None:
    if isinstance(v, int) and 1 <= v <= 7:
        return v
    if isinstance(v, str):
        s = v.strip()
        if s.isdigit():
            n = int(s)
            if 1 <= n <= 7:
                return n
        m = re.search(r"(?:星期|周)([一二三四五六日天])", s)
        if m:
            mp = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7}
            return mp.get(m.group(1))
        if len(s) == 1 and s in "一二三四五六日天":
            mp = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7}
            return mp.get(s)
    return None


def _tis_parse_sections(v: object) -> tuple[int, int] | None:
    if isinstance(v, (tuple, list)) and len(v) == 2:
        try:
            a = int(v[0])
            b = int(v[1])
            if 1 <= a <= b <= 16:
                return a, b
        except Exception:
            return None

    if isinstance(v, int) and 1 <= v <= 16:
        return v, v

    if isinstance(v, str):
        s = v.strip()

        m = re.search(r"(\d{1,2})\s*[-~]\s*(\d{1,2})(?:\s*节)?", s)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if 1 <= a <= b <= 16:
                return a, b

        m = re.search(r"(\d{1,2})\s*[,，、]\s*(\d{1,2})", s)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if 1 <= a <= b <= 16:
                return a, b

        m = re.search(r"(\d{1,2})", s)
        if m:
            a = int(m.group(1))
            if 1 <= a <= 16:
                return a, a

    return None


def _tis_parse_weeks(v: object) -> list[int]:
    if isinstance(v, list):
        out: list[int] = []
        for item in v:
            try:
                n = int(str(item).strip())
            except Exception:
                continue
            if 1 <= n <= 40:
                out.append(n)
        return sorted(set(out))

    if isinstance(v, int) and 1 <= v <= 40:
        return [v]

    if not isinstance(v, str):
        return []

    s = v.strip()
    odd_only = "单" in s
    even_only = "双" in s

    m = re.search(r"(\d{1,2})\s*[-~]\s*(\d{1,2})(?:\s*周)?", s)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        nums = list(range(min(a, b), max(a, b) + 1))
    else:
        nums = [int(x) for x in re.findall(r"(\d{1,2})", s)]

    if odd_only:
        nums = [n for n in nums if n % 2 == 1]
    if even_only:
        nums = [n for n in nums if n % 2 == 0]

    nums = [n for n in nums if 1 <= n <= 40]
    return sorted(set(nums))


def _tis_parse_zc_bitset(v: object) -> list[int]:
    if not isinstance(v, str):
        return []

    s = v.strip()
    if not s or any(ch not in "01" for ch in s):
        return []

    out: list[int] = []
    for i, ch in enumerate(s):
        if ch != "1":
            continue
        if i <= 0:
            continue
        if 1 <= i <= 40:
            out.append(i)

    return out


def _tis_dt(day0: datetime, hhmm: str) -> datetime:
    hh, mm = hhmm.split(":", 1)
    return datetime(day0.year, day0.month, day0.day, int(hh), int(mm))


def _tis_extract_meetings(payload: object) -> list[dict[str, object]]:
    meetings: list[dict[str, object]] = []

    for d in _tis_iter_dicts(payload):
        if not isinstance(d, dict):
            continue

        desc_src = d.get("SKSJ") or d.get("SKSJ_EN")

        course_name = (
            d.get("kcmc")
            or d.get("KCMC")
            or d.get("course")
            or d.get("courseName")
            or d.get("name")
            or d.get("title")
        )
        teacher = d.get("jsxm") or d.get("JSXM") or d.get("teacher") or d.get("instructor")
        location = d.get("cdmc") or d.get("CDMC") or d.get("room") or d.get("location")

        weekday = None
        for k in ("xq", "XQ", "xqj", "XQJ", "weekday", "dayOfWeek", "xqjmc", "weekDay"):
            if k in d:
                weekday = _tis_parse_weekday(d.get(k))
                if weekday:
                    break

        if not weekday:
            key = d.get("KEY") or d.get("key")
            if isinstance(key, str):
                m = re.search(r"xq([1-7])", key)
                if m:
                    weekday = int(m.group(1))

        sections = None
        if ("ksjc" in d and "jsjc" in d) or ("KSJC" in d and "JSJC" in d):
            sections = _tis_parse_sections((d.get("ksjc") or d.get("KSJC"), d.get("jsjc") or d.get("JSJC")))

        if not sections:
            for k in ("jcs", "JCS", "jc", "JC", "qzjc", "QZJC"):
                if k in d:
                    sections = _tis_parse_sections(d.get(k))
                    if sections:
                        break

        weeks = _tis_parse_zc_bitset(d.get("ZC") or d.get("zc"))
        if not weeks:
            for k in ("zcs", "ZCS", "weeks", "week", "kkzc", "KKZC", "weekRange"):
                if k in d:
                    weeks = _tis_parse_weeks(d.get(k))
                    if weeks:
                        break

        desc = ""
        if isinstance(desc_src, str) and ("周" in desc_src and "节" in desc_src):
            desc = desc_src
        else:
            for v in d.values():
                if isinstance(v, str) and ("周" in v and "节" in v):
                    desc = v
                    break

        if desc and (not course_name or not weekday or not sections or not weeks):
            txt = desc
            if not course_name:
                course_name = txt.split("[", 1)[0].strip() or course_name
            if not teacher:
                m = re.search(r"\[([^\[\]]+)\]", txt)
                if m:
                    teacher = m.group(1).strip()
            if not weeks:
                m = re.search(r"\[(\d{1,2}\s*[-~]\s*\d{1,2}\s*周(?:[^\]]*)?)\]", txt)
                if m:
                    weeks = _tis_parse_weeks(m.group(1))
            if not sections:
                m = re.search(r"\[(\d{1,2}\s*[-~]\s*\d{1,2}\s*节)\]", txt)
                if m:
                    sections = _tis_parse_sections(m.group(1))
            if not weekday:
                m = re.search(r"\[(?:周|星期)([一二三四五六日天])\]", txt)
                if m:
                    weekday = _tis_parse_weekday(m.group(0))

            if not location:
                m = re.search(r"\[([^\[\]]*(?:楼|教|场|室|房|馆|地点)[^\[\]]*)\]", txt)
                if m:
                    location = m.group(1).strip()

        if not weekday or not sections or not weeks or not course_name:
            continue

        start_sec, end_sec = sections
        kind: Literal["lecture", "experiment", "other"] = "lecture"
        name_lower = str(course_name).lower()
        if "实验" in str(course_name) or "lab" in name_lower:
            kind = "experiment"

        meetings.append(
            {
                "course_id": str(d.get("RWH") or d.get("rwh") or d.get("kch") or d.get("KCH") or d.get("courseCode") or course_name),
                "course_name": str(course_name),
                "weekday": weekday,
                "start_sec": start_sec,
                "end_sec": end_sec,
                "weeks": weeks,
                "location": str(location or ""),
                "teacher": str(teacher) if teacher else None,
                "kind": kind,
            }
        )

    return meetings


def _tis_meetings_to_occurrences(meetings: list[dict[str, object]]) -> list[CourseOccurrence]:
    occs: list[CourseOccurrence] = []

    for m in meetings:
        weekday = int(m["weekday"])
        start_sec = int(m["start_sec"])
        end_sec = int(m["end_sec"])
        weeks = [int(x) for x in (m.get("weeks") or [])]

        if start_sec not in _SUSTECH_CLASS_PERIODS or end_sec not in _SUSTECH_CLASS_PERIODS:
            continue

        start_hhmm = _SUSTECH_CLASS_PERIODS[start_sec][0]
        end_hhmm = _SUSTECH_CLASS_PERIODS[end_sec][1]

        for w in weeks:
            day0 = _TIS_WEEK1_MONDAY + timedelta(days=(w - 1) * 7 + (weekday - 1))
            start_at = _tis_dt(day0, start_hhmm)
            end_at = _tis_dt(day0, end_hhmm)
            if end_at <= start_at:
                continue
            occs.append(
                CourseOccurrence(
                    course_id=str(m["course_id"]),
                    start_at=start_at,
                    end_at=end_at,
                    location=str(m.get("location") or ""),
                    kind=m.get("kind") or "lecture",
                    instructor=m.get("teacher"),
                    notes=str(m.get("course_name") or ""),
                )
            )

    occs.sort(key=lambda x: (x.start_at, x.course_id))
    return occs


_FALLBACK_CANCEL_DAYS = {
    date(2026, 2, 23),
    date(2026, 2, 24),
    date(2026, 4, 6),
    date(2026, 5, 1),
    date(2026, 5, 4),
    date(2026, 5, 5),
}

_FALLBACK_MOVE_RULES: list[tuple[date, date]] = [
    (date(2026, 2, 23), date(2026, 2, 28)),
    (date(2026, 5, 5), date(2026, 5, 9)),
]


def _filter_relevant_override_rules(
    occs: list[CourseOccurrence],
    cancel_days: set[date],
    move_rules: list[tuple[date, date]],
) -> tuple[set[date], list[tuple[date, date]]]:
    if not occs:
        return cancel_days, move_rules
    occ_days = {o.start_at.date() for o in occs}
    filtered_cancel = {d for d in cancel_days if d in occ_days}
    filtered_moves = [(src, dst) for src, dst in move_rules if src in occ_days]
    return filtered_cancel, filtered_moves


async def _load_calendar_override_rules(occs: list[CourseOccurrence]) -> tuple[set[date], list[tuple[date, date]]]:
    cancel_days = set(_FALLBACK_CANCEL_DAYS)
    move_rules = list(_FALLBACK_MOVE_RULES)

    try:
        overrides = await get_calendar_overrides()
        cancel_days.update(overrides.cancel_days)
        move_rules.extend(overrides.move_rules)
    except Exception:
        logger.exception("tis.calendar: failed to load dynamic calendar overrides, using fallback only")

    cancel_days, move_rules = _filter_relevant_override_rules(occs, cancel_days, move_rules)
    deduped_moves: list[tuple[date, date]] = []
    seen: set[tuple[date, date]] = set()
    for item in move_rules:
        if item in seen:
            continue
        seen.add(item)
        deduped_moves.append(item)
    return cancel_days, deduped_moves


def _apply_calendar_overrides(
    occs: list[CourseOccurrence],
    *,
    cancel_days: set[date],
    move_rules: list[tuple[date, date]],
) -> list[CourseOccurrence]:
    moved: list[CourseOccurrence] = []
    for src, dst in move_rules:
        delta_days = (dst - src).days
        for o in occs:
            if o.start_at.date() != src:
                continue
            moved.append(
                CourseOccurrence(
                    course_id=o.course_id,
                    start_at=o.start_at + timedelta(days=delta_days),
                    end_at=o.end_at + timedelta(days=delta_days),
                    location=o.location,
                    kind=o.kind,
                    instructor=o.instructor,
                    notes=o.notes,
                )
            )

    override_days = {dst for _, dst in move_rules}
    kept = [o for o in occs if o.start_at.date() not in cancel_days and o.start_at.date() not in override_days]
    kept.extend(moved)
    kept.sort(key=lambda x: (x.start_at, x.course_id))
    return kept


async def fetch_course_schedule(cas_account: str, cas_password: str) -> list[CourseOccurrence]:
    _ensure_file_logging()

    service_url = f"{ACADEMIC_SYSTEM_BASE}/cas"
    main_url = f"{ACADEMIC_SYSTEM_BASE}/authentication/main"

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=httpx.Timeout(20.0),
        headers=headers,
        trust_env=False,
    ) as client:
        r0 = await _request_with_retry(client, "GET", main_url, label="tis.main")
        if "cas.sustech.edu.cn" in str(r0.url):
            await _cas_login(client, cas_account, cas_password, service_url)
            r0 = await _request_with_retry(client, "GET", main_url, label="tis.main.after_login")

        if r0.status_code >= 400:
            raise ConnectionError(f"Academic system unreachable: status={r0.status_code}")

        xhr_headers = {
            "Origin": ACADEMIC_SYSTEM_BASE,
            "Referer": main_url,
            "X-Requested-With": "XMLHttpRequest",
        }

        async def _tis_post(
            path: str,
            *,
            data: dict[str, str] | None = None,
            label: str,
        ) -> httpx.Response:
            url = f"{ACADEMIC_SYSTEM_BASE}{path}"
            req_headers = {**xhr_headers, "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}

            r = await _request_with_retry(client, "POST", url, headers=req_headers, data=data or {}, label=label)
            if _tis_needs_auth_response(r):
                await _cas_login(client, cas_account, cas_password, service_url)
                r = await _request_with_retry(
                    client,
                    "POST",
                    url,
                    headers=req_headers,
                    data=data or {},
                    label=f"{label}.retry",
                )

            if _tis_needs_auth_response(r):
                raise PermissionError("TIS authentication required")

            return r

        r_term = await _tis_post("/component/querydangqianxnxq", label="tis.term")

        term_payload: object
        try:
            term_payload = r_term.json()
        except Exception:
            term_payload = r_term.text
            s = (term_payload or "").strip()
            if s.startswith("{") or s.startswith("["):
                try:
                    term_payload = json.loads(s)
                except Exception:
                    term_payload = r_term.text

        xn_xq = _tis_extract_xn_xq(term_payload)
        if not xn_xq:
            xn_xq = ("2025-2026", "2")
        xn, xq = xn_xq

        await _tis_post("/component/querysfxsbjkb", label="tis.sfxsbjkb")

        for ep, label in (
            ("/xszykb/queryxskbbz", "tis.kbbz"),
            ("/xszykb/querykbsffb", "tis.kbsffb"),
        ):
            await _tis_post(ep, data={"xn": xn, "xq": xq}, label=label)

        r_kb = await _tis_post("/xszykb/queryxszykbzong", data={"xn": xn, "xq": xq}, label="tis.kb.zong")

        try:
            kb_payload: object = r_kb.json()
        except Exception:
            kb_payload = r_kb.text
            s = (kb_payload or "").strip()
            if s.startswith("{") or s.startswith("["):
                try:
                    kb_payload = json.loads(s)
                except Exception:
                    kb_payload = r_kb.text

        meetings = _tis_extract_meetings(kb_payload)
        if not meetings:
            _tis_dump_test5(
                reason="meetings_empty",
                r_term=r_term,
                term_payload=term_payload,
                r_kb=r_kb,
                kb_payload=kb_payload,
                meetings_count=0,
            )
            if _tis_needs_auth_response(r_kb):
                raise PermissionError("TIS authentication required")
            raise RuntimeError("Academic schedule empty or unparseable")

        occs = _tis_meetings_to_occurrences(meetings)
        cancel_days, move_rules = await _load_calendar_override_rules(occs)
        return _apply_calendar_overrides(occs, cancel_days=cancel_days, move_rules=move_rules)
