"""Unit tests for punct_normalize — punctuation cleanup rules.

Cases are taken from real GigaAM dictation errors (recovery notes / logs):
duplicate commas, dots mid-question, mechanical commas after pause words,
missing spaces before colons, trailing junk.
"""

import pytest

import punct_normalize as pn


# ── R1: duplicate / mixed punctuation ──────────────────────────────────────

def test_duplicate_comma_collapse():
    assert pn.normalize("давай ,, посмотрим") == "Давай посмотрим"


def test_duplicate_dots_collapse():
    # ".." -> sentence break: dot stays, next word is capitalised
    assert pn.normalize("слово .. слово") == "Слово. Слово"


def test_duplicate_exclamation_collapse():
    assert pn.normalize("привет!!!") == "Привет!"


def test_ellipsis_becomes_dot():
    assert pn.normalize("подожди ...") == "Подожди."


def test_mixed_run_comma_dot():
    # ",." -> sentence break; the "так" marker needs a plain comma, not ",."
    assert pn.normalize("так ,. пойдём") == "Так. Пойдём"


def test_marker_after_comma_space_comma():
    assert pn.normalize("так , пойдём") == "Так пойдём"


def test_comma_space_comma():
    assert pn.normalize("ну , , ладно") == "Ну ладно"


# ── R2: spacing around punctuation ─────────────────────────────────────────

def test_missing_space_before_text_after_colon():
    assert pn.normalize("Так:я хочу") == "Так: я хочу"


def test_no_space_before_comma():
    assert pn.normalize("слово ,слово") == "Слово, слово"


def test_decimal_comma_untouched():
    assert pn.normalize("3,5 литра") == "3,5 литра"


# ── R3: trailing junk ──────────────────────────────────────────────────────

def test_trailing_comma_removed():
    assert pn.normalize("Добли нету ,") == "Добли нету"


def test_trailing_colon_removed():
    assert pn.normalize("итак вывод:") == "Итак вывод"


def test_trailing_dash_removed():
    assert pn.normalize("слова -") == "Слова"


# ── R4: question words mid-phrase ──────────────────────────────────────────

def test_qword_dot_mid_phrase():
    assert pn.normalize("о чём. подумаем?") == "О чём подумаем?"


def test_qword_comma_mid_phrase():
    assert pn.normalize("зачем, ты пришёл?") == "Зачем ты пришёл?"


def test_qword_kak():
    assert pn.normalize("как. дела?") == "Как дела?"


# ── R5: pause markers ──────────────────────────────────────────────────────

def test_marker_devay():
    assert pn.normalize("давай, посмотрим") == "Давай посмотрим"


def test_marker_nu():
    assert pn.normalize("ну, понял?") == "Ну понял?"


def test_marker_shortphrase_mid():
    assert pn.normalize("он потом, сказал") == "Он потом сказал"


def test_marker_zdes():
    assert pn.normalize("смотри, вот тут") == "Смотри вот тут"


# ── R6: capitalization ─────────────────────────────────────────────────────

def test_first_letter_capitalized():
    assert pn.normalize("привет мир") == "Привет мир"


def test_capital_after_sentence_end():
    assert pn.normalize("всё. идём") == "Всё. Идём"


def test_capital_after_question():
    assert pn.normalize("правда? да") == "Правда? Да"


def test_allcaps_word_untouched():
    assert pn.normalize("я ЗНАЮ. что это") == "Я ЗНАЮ. Что это"


# ── R7: quotes and dashes ──────────────────────────────────────────────────

def test_quotes_become_guillemets():
    assert pn.normalize('он сказал "привет" и ушёл') == "Он сказал «привет» и ушёл"


def test_double_dash_becomes_em_dash():
    assert pn.normalize("а -- б") == "А — б"


# ── Modes ──────────────────────────────────────────────────────────────────

def test_light_mode_keeps_markers():
    assert pn.normalize("давай, посмотрим", mode="light") == "Давай, посмотрим"


def test_light_still_structural():
    assert pn.normalize("давай ,, посмотрим", mode="light") == "Давай, посмотрим"


def test_light_keeps_straight_quotes():
    # light mode does not convert quotes (R7 is full-only)
    assert '"' in pn.normalize('сказал "да" и пошёл', mode="light")


# ── Edge cases ─────────────────────────────────────────────────────────────

def test_empty_string():
    assert pn.normalize("") == ""


def test_whitespace_only():
    assert pn.normalize("   ") == ""


def test_no_punct_text_unchanged_content():
    assert pn.normalize("добли нету") == "Добли нету"


def test_invalid_type_raises():
    with pytest.raises(TypeError):
        pn.normalize(12345)


def test_existing_sentence_punctuation_preserved():
    # a comma that is grammatical must not be eaten
    assert pn.normalize("иди, пожалуйста") == "Иди, пожалуйста"