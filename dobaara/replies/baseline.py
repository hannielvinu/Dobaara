"""Keyword / regex reply parser — the baseline the LLM has to beat.

Written from a general Hinglish lexicon *before* the labelled reply set existed. Free, instant,
and fully explainable; if the LLM is not clearly better on held-out data, this is what ships.
"""

from __future__ import annotations

import re
from datetime import date

from ..models import Intent, ParsedReply
from .dates import resolve

LEXICON: dict[Intent, list[str]] = {
    Intent.WRONG_PERSON: [
        r"wrong (?:number|person)", r"galat (?:number|no\.?|insaan|banda)", r"not my (?:number|account)",
        r"mera (?:number|account) nahi", r"main (?:wo|woh|vo) nahi", r"i am not", r"गलत नंबर",
        r"wrong no\b", r"galat diya", r"account nahi chalata", r"(?:koi )?subscription nahi (?:leta|leti|liya)",
        r"(?:beta|bhai|papa|wife) use karta", r"customer nahi hu", r"नंबर गलत",
    ],
    Intent.DISPUTE: [
        r"fraud", r"scam", r"not authori[sz]ed", r"unauthori[sz]ed", r"never (?:subscribed|signed|took)",
        r"kabhi (?:liya|subscribe|kiya) (?:hi )?nahi", r"maine (?:ye |yeh |koi )?(?:subscription |plan )?(?:liya|kiya) (?:hi )?nahi",
        r"galat (?:charge|paisa|kata|cut)", r"wrong(?:ly)? charged", r"dispute", r"complaint", r"consumer court",
        r"authori[sz]e hi nahi", r"bataya hi nahi", r"kyu kata", r"bina (?:bataye|permission)", r"charged twice",
        r"double kata", r"refund do",
        r"धोखा", r"फ्रॉड",
    ],
    Intent.ALREADY_PAID: [
        r"already (?:paid|done|pay)", r"paid already", r"(?:kar|kr|de|bhej) (?:diya|di|chuka|chuki)",
        r"(?:payment|pay) (?:ho gaya|ho gya|done|kar diya|kr diya)", r"i (?:have )?paid", r"paid (?:it|yesterday|today|just now)",
        r"ho gaya payment", r"bhar diya", r"payment done",
        r"जमा कर दिया", r"भेज दिया", r"कर दिया", r"दे दिया",
    ],
    Intent.CANCEL: [
        r"cancel", r"unsubscribe", r"band (?:kar|kr|karo|kro|krdo|kardo)", r"nahi chahiye", r"nhi chahiye",
        r"(?:don'?t|do not|dont) want", r"\bstop\b", r"mat bhejo", r"(?:nahi|nhi) (?:dunga|dungi|karunga|karungi|bharunga)",
        r"won'?t pay", r"will not pay", r"बंद कर", r"नहीं चाहिए", r"continue nahi", r"(?:don'?t|dont) message",
        r"message mat", r"बंद करो",
    ],
    Intent.PROMISE_TO_PAY: [
        r"(?:kar|kr|de|bhej|bhar|pay kar|pay kr)\s?(?:dunga|dungi|denge|doonga|doongi|deta|deti|dete)",
        r"(?:karunga|karungi|bharunga|bharungi|chuka dunga)", r"will (?:pay|do|clear|make)", r"i'?ll (?:pay|do|clear)",
        r"going to pay", r"paying (?:by|on|tomorrow|today)", r"salary", r"tankha", r"\bpay\b.*\b(?:by|on|tak)\b",
        r"\bpakka\b", r"\bsure\b", r"\bretry\b", r"try kar", r"\bsending\b", r"kar raha", r"karta hu",
        r"(?:bhar|kar) deta", r"\badjust\b", r"bata dunga", r"भर देता",
        r"करूंगा|करूँगा|करूंगी|दूंगा|दूँगा|दूंगी|भर दूंगा|सैलरी",
    ],
    Intent.HARDSHIP: [
        r"job (?:chali|gayi|gone|lost)|lost (?:my )?job|naukri (?:chali|gayi|nahi)", r"medical|hospital|emergency",
        r"(?:can'?t|cannot|can not) afford|afford nahi", r"bahut (?:mushkil|tight)", r"income nahi", r"business band",
        r"नौकरी|अस्पताल", r"surgery", r"unemployed", r"kamai nahi", r"dukaan band", r"nahi bhar sakta",
    ],
}

# Phrases that cancel a match, e.g. "cancel mat karo" means *don't* cancel.
NEGATIONS: dict[Intent, list[str]] = {
    Intent.CANCEL: [r"cancel (?:mat|na|nahi|nhi)", r"(?:don'?t|do not|dont) cancel", r"band mat", r"band (?:na|nahi) kar"],
    Intent.ALREADY_PAID: [r"(?:nahi|nhi) (?:kar|kr|de|bhej) (?:diya|di)"],
}

PRIORITY = [
    Intent.WRONG_PERSON, Intent.DISPUTE, Intent.ALREADY_PAID, Intent.PROMISE_TO_PAY, Intent.HARDSHIP, Intent.CANCEL,
]

_COMPILED = {i: [re.compile(p) for p in pats] for i, pats in LEXICON.items()}
_NEG = {i: [re.compile(p) for p in pats] for i, pats in NEGATIONS.items()}
_AMOUNT = re.compile(r"(?:₹|rs\.?|inr)\s*(\d[\d,]*)|(\d[\d,]*)\s*(?:rs|rupees|rupaye|rupay|₹)")


def matched_intents(text: str) -> list[Intent]:
    t = text.lower()
    hits = []
    for intent in PRIORITY:
        if any(rx.search(t) for rx in _COMPILED[intent]) and not any(rx.search(t) for rx in _NEG.get(intent, [])):
            hits.append(intent)
    return hits


def parse(text: str, sent: date) -> ParsedReply:
    hits = matched_intents(text)
    intent = hits[0] if hits else Intent.OTHER
    if intent is Intent.OTHER and resolve(text, sent) is not None and "?" not in text:
        intent = Intent.PROMISE_TO_PAY  # a bare day ("6 ko", "thursday") answering a dunning message
    promised = resolve(text, sent) if intent is Intent.PROMISE_TO_PAY else None
    m = _AMOUNT.search(text.lower())
    amount = float((m.group(1) or m.group(2)).replace(",", "")) if m else None
    return ParsedReply(intent, promised, amount, True, "baseline")
