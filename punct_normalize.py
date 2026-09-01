"""Post-processing of ASR text: punctuation cleanup and short-marker rules.

Applied to raw GigaAM output right after transcription. GigaAM v3 emits
punctuation unreliably (duplicate commas, dots mid-question, mechanical
commas after pause words), so here we fix the most common failure modes
with pure regex rules — no external dependencies.

Modes:
    "light" — structural cleanup only (always safe):
        R1 collapse duplicate punctuation runs ("давай ,," -> "давай,");
        R2 spacing around punctuation ("Так:я" -> "Так: я");
        R3 drop trailing junk (visiting comma/colon/dash at phrase end);
        R6 capitalise sentence starts.
    "full"  — light + conversational marker rules (default):
        R4 remove misplaced '.'/',' right after question words mid-phrase
           ("о чём. подумаем?" -> "о чём подумаем?");
        R5 remove mechanical comma after short pause-markers
           ("давай, посмотрим" -> "давай посмотрим");
        R7 straight quotes -> «», "--" -> " — ", dangling '-' removed.
"""

import re

__all__ = ["normalize"]

# ── R5 pause markers ─────────────────────────────────────────────────────────
# A comma right after these mid-speech words is almost always mechanical (the
# model inserts it after a pause). "например/конечно/хорошо" are excluded on
# purpose — a comma after them is usually grammatical ("например, яблоки").
_MARKERS = (
    r"давай|ну|вот|так|значит|кстати|короче|слушай|смотри|вообще|просто|"
    r"опять|сейчас|потом|ладно|тут|там|здесь"
)

# ── R4 question words ────────────────────────────────────────────────────────
# A '.' or ',' right after these mid-phrase is a false sentence break / a
# mechanical pause, not a real boundary ("о чём. подумаем?").
_Q_WORDS = r"о чём|о чем|как|что|зачем|почему|когда|где|куда|откуда|кто|который"

_RE_MARKER_COMMA = re.compile(rf"\b({_MARKERS})\s*,\s+")
_RE_QWORD_PUNCT = re.compile(rf"\b({_Q_WORDS})[.,]\s+(?=[а-яё])")

_LETTER_LOW = "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"


def _collapse_spaces(s: str) -> str:
    return re.sub(r"\s+", " ", s)


def _collapse_punct(s: str) -> str:
    """R1 — duplicate and mixed punctuation runs -> one strong sign."""
    # "comma space comma" and friends -> single comma before the dup pass
    s = re.sub(r"([.,!?;:])\s+([.,!?;:])", r"\1", s)
    # repeated identical sign: ,,  ..  !!  ??  ;;
    s = re.sub(r"([.,!?;:])\1+", r"\1", s)
    # mixed runs keep the strongest trailing sign: ,.?  -> ?,  ,!  -> !,  ,.  -> .
    s = re.sub(r"[.,;:!]*\?+", "?", s)
    s = re.sub(r"[.,;:]*\!+", "!", s)
    s = re.sub(r"[.,;:]{2,}", ".", s)
    return s


def _fix_spacing(s: str) -> str:
    """R2 — no space before punctuation, exactly one space after."""
    # no space before closing signs / quotes.
    # NOTE: '"' and '\'' are NOT in the closing class — a straight double
    # quote may open a citation; R7 converts quotes later.
    s = re.sub(r"\s+([.,!?;:»')])", r"\1", s)
    # one space after sentence signs
    s = re.sub(r"([.!?;:])(?=\S)", r"\1 ", s)
    # one space after a comma, unless it is a decimal comma (3,5)
    s = re.sub(r"(?<=\D)(,)(?=\S)", r"\1 ", s)
    # normalise runs of spaces after punctuation to one
    s = re.sub(r"([.,!?;:])\s+", r"\1 ", s)
    # exactly one space before opening quote/bracket
    s = re.sub(r"\s*([«(\[])", r" \1", s)
    return s


def _strip_trailing_junk(s: str) -> str:
    """R3 — drop a dangling comma/colon/semicolon/hyphen at phrase end."""
    s = re.sub(r"\s*[,;:]+\s*$", "", s)
    s = re.sub(r"\s+-\s*$", "", s)
    return s


def _capitalize(s: str) -> str:
    """R6 — capitalise the first letter and any letter after . ! ? … boundary."""
    chars = list(s)
    n = len(chars)
    up = True  # start of string -> expect a capital
    for i in range(n):
        ch = chars[i]
        if up and ch in _LETTER_LOW:
            chars[i] = ch.upper()
            up = False
            continue
        if ch in ".!?…":
            # sentence boundary only when followed by space or end of text
            up = (i + 1 >= n or chars[i + 1] == " ")
        elif ch.isalnum() or ch in "»\"":
            up = False
        # spaces, «, (, [ — leave the pending capital for the next letter
    return "".join(chars)


def _fix_quotes_dashes(s: str) -> str:
    """R7 — straight quotes -> «», "--" -> " — ", dangling hyphen removed."""
    s = re.sub(r'"([^"]*)"', r"«\1»", s)
    # spacing around « »
    s = re.sub(r"«\s+", "«", s)
    s = re.sub(r"\s+»", "»", s)
    s = re.sub(r"\s+«", " «", s)
    s = re.sub(r"»\s+", "» ", s)
    # "--" / "---" -> em dash with spaces
    s = re.sub(r"\s*-{2,}\s*", " — ", s)
    return s


def _normalize_light(text: str) -> str:
    s = _collapse_spaces(text)
    s = _collapse_punct(s)
    s = _fix_spacing(s)
    s = _strip_trailing_junk(s)
    s = _capitalize(s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _normalize_full(text: str) -> str:
    s = _collapse_spaces(text)
    s = _collapse_punct(s)
    s = _fix_spacing(s)
    # R5 — remove mechanical comma after pause markers
    s = _RE_MARKER_COMMA.sub(r"\1 ", s)
    # R4 — remove false sentence break / pause after question words
    s = _RE_QWORD_PUNCT.sub(r"\1 ", s)
    s = _fix_quotes_dashes(s)
    s = _strip_trailing_junk(s)
    s = _capitalize(s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def normalize(text: str, mode: str = "full") -> str:
    """Normalise punctuation in an ASR text.

    Args:
        text: raw transcription output.
        mode: "light" (structural cleanup only) or "full" (also marker
            rules). Anything else falls back to "full".

    Returns:
        The cleaned text. Empty input returns it unchanged.
    """
    if not text:
        return text
    if not isinstance(text, str):
        raise TypeError("normalize() expects a str, got %s" % type(text).__name__)
    if (mode or "full").lower() == "light":
        return _normalize_light(text)
    return _normalize_full(text)