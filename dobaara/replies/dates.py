"""Resolve date expressions in a reply to a calendar date, relative to when the reply was sent.

Only expressions that pin down a single day resolve. "next week" or "salary aane pe" do not: the
recovery policy falls back to the payday model for those instead of guessing.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

NUM_WORDS = {
    "ek": 1, "do": 2, "teen": 3, "tin": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "paach": 5,
    "chhe": 6, "che": 6, "saat": 7, "aath": 8, "nau": 9, "das": 10,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "ten": 10,
}
WEEKDAYS = {
    0: ("monday", "mon", "somvar", "somwar", "सोमवार"),
    1: ("tuesday", "tue", "mangalvar", "mangalwar", "मंगलवार"),
    2: ("wednesday", "wed", "budhvar", "budhwar", "बुधवार"),
    3: ("thursday", "thu", "guruvar", "guruwar", "brihaspativar", "गुरुवार"),
    4: ("friday", "fri", "shukravar", "shukrawar", "शुक्रवार"),
    5: ("saturday", "sat", "shanivar", "shaniwar", "शनिवार"),
    6: ("sunday", "sun", "ravivar", "raviwar", "रविवार"),
}
MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m} | {
    m.lower(): i for i, m in enumerate(calendar.month_name) if m}

_DOM_MARKERS = r"(?:st|nd|rd|th)?\s*(?:tarik|tarikh|tareekh|taarikh|tareek|tak|ko|date|तारीख|तक|को)"
_RE_DOM = re.compile(r"(?<!\d)([0-3]?\d)\s*" + _DOM_MARKERS)
_RE_ORD = re.compile(r"(?<!\d)([0-3]?\d)(?:st|nd|rd|th)\b")
_RE_DMY = re.compile(r"(?<!\d)([0-3]?\d)\s*[/\-.]\s*(1[0-2]|0?[1-9])(?!\d)")
_RE_D_MON = re.compile(r"(?<!\d)([0-3]?\d)\s*(?:st|nd|rd|th)?\s+([a-z]{3,9})\b")
_RE_MON_D = re.compile(r"\b([a-z]{3,9})\s+([0-3]?\d)(?:st|nd|rd|th)?\b")
_RE_IN_DAYS = re.compile(
    r"(?:(\d{1,2})|(" + "|".join(NUM_WORDS) + r"))(?:\s*[-/]\s*(?:(\d{1,2})|(" + "|".join(NUM_WORDS) + r")))?"
    r"\s*(?:din|days?|दिन)\b"
)


def _next_dom(today: date, dom: int) -> date | None:
    if not 1 <= dom <= 31:
        return None
    y, m = today.year, today.month
    for _ in range(2):
        last = calendar.monthrange(y, m)[1]
        if dom <= last:
            cand = date(y, m, dom)
            if cand >= today:
                return cand
        m = m % 12 + 1
        y += 1 if m == 1 else 0
    return None


def _month_end(today: date) -> date:
    return date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])


def _num(digits: str | None, word: str | None) -> int | None:
    if digits:
        return int(digits)
    if word:
        return NUM_WORDS[word]
    return None


def resolve(text: str, sent: date) -> date | None:
    """Return the single day a reply commits to, or None if it does not name one."""
    t = text.lower()

    # "2-3 din" is a span of days, not 2 March: check day counts before d/m dates.
    m = _RE_IN_DAYS.search(t)
    if m:
        lo = _num(m.group(1), m.group(2))
        hi = _num(m.group(3), m.group(4))
        n = hi if hi is not None else lo
        if n is not None and 0 < n <= 31:
            return sent + timedelta(days=n)

    m = _RE_DMY.search(t)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        try:
            cand = date(sent.year, mo, d)
            return cand if cand >= sent else date(sent.year + 1, mo, d)
        except ValueError:
            pass
    for rx, order in ((_RE_D_MON, "dm"), (_RE_MON_D, "md")):
        for m in rx.finditer(t):
            d_s, mon_s = (m.group(1), m.group(2)) if order == "dm" else (m.group(2), m.group(1))
            mo = MONTHS.get(mon_s[:3]) if mon_s[:3] in MONTHS else None
            if mo:
                try:
                    cand = date(sent.year, mo, int(d_s))
                    return cand if cand >= sent else date(sent.year + 1, mo, int(d_s))
                except ValueError:
                    pass

    m = _RE_DOM.search(t) or _RE_ORD.search(t)
    if m:
        return _next_dom(sent, int(m.group(1)))

    if re.search(r"month\s*end|end of (?:the )?month|mahine? ke (?:end|aakhir|akhir)|mahina khatam|महीने के (?:अंत|आखिर)", t):
        return _month_end(sent)
    if re.search(r"\bparso\b|\bparson\b|day after tomorrow|परसों", t):
        return sent + timedelta(days=2)
    if re.search(r"\bkal\b|\bkl\b|\btomorrow\b|\btmrw\b|\btmr\b|कल", t):
        return sent + timedelta(days=1)
    if re.search(r"\baaj\b|\btoday\b|\babhi\b|\bright now\b|आज|अभी", t):
        return sent

    for wd, names in WEEKDAYS.items():
        if any(re.search(rf"(?<![a-z]){re.escape(n)}(?![a-z])", t) for n in names if len(n) > 3 or n.isascii() is False):
            ahead = (wd - sent.weekday()) % 7 or 7
            return sent + timedelta(days=ahead)
    return None
