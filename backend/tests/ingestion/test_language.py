"""Language detection is deterministic and reports asymmetric confidences."""

from app.ingestion.language import (
    DEFAULT_LANGUAGE_DETECTOR,
    ENGLISH_FUNCTION_WORDS,
    HeuristicLanguageDetector,
    dominant_script,
    tokenize_for_language,
)

ENGLISH = (
    "The proposed audit requirement would apply to any model trained above the compute "
    "threshold, and that is the part of the bill that people are actually arguing about."
)
GERMAN = (
    "Dieser Vorschlag würde kleine Unternehmen stark belasten, weil die Kosten für "
    "unabhängige Audits sehr hoch sind und niemand sie tragen will."
)
RUSSIAN = "Это предложение сильно ударит по небольшим компаниям, потому что аудит дорогой."
CHINESE = "这是一个很长的中文句子,用来测试语言检测是否能够正确识别非英语的文本内容。"
EMOJI = "🎉🎉🎉🎉🎉🎉🎉🎉"


def test_english_text_is_detected() -> None:
    guess = DEFAULT_LANGUAGE_DETECTOR.detect(ENGLISH)

    assert guess.language == "en"
    assert guess.english_confidence > 0.6
    assert guess.non_english_confidence == 0.0
    assert guess.script == "latin"


def test_german_is_flagged_as_not_english() -> None:
    guess = DEFAULT_LANGUAGE_DETECTOR.detect(GERMAN)

    assert guess.language != "en"
    assert guess.non_english_confidence >= 0.6


def test_non_latin_scripts_are_conclusive() -> None:
    for text, script in ((RUSSIAN, "cyrillic"), (CHINESE, "han")):
        guess = DEFAULT_LANGUAGE_DETECTOR.detect(text)
        assert guess.language != "en", text
        assert guess.non_english_confidence >= 0.9, text
        assert guess.script == script, text


def test_short_text_is_undetermined_rather_than_wrong() -> None:
    """Too little evidence must not be reported as a confident foreign-language verdict."""
    guess = DEFAULT_LANGUAGE_DETECTOR.detect("Yes exactly")

    assert guess.language == "und"
    assert guess.non_english_confidence == 0.0


def test_text_without_letters_is_handled() -> None:
    guess = DEFAULT_LANGUAGE_DETECTOR.detect(EMOJI)

    assert guess.language == "und"
    assert guess.script == "none"
    assert guess.english_confidence == 0.0
    assert guess.non_english_confidence == 0.0


def test_detection_is_deterministic() -> None:
    detector = HeuristicLanguageDetector()

    first = detector.detect(GERMAN)
    second = detector.detect(GERMAN)

    assert first == second


def test_dominant_script_counts_letters_only() -> None:
    script, letters = dominant_script("abc 123 !!! абв")

    # Latin appears three times, Cyrillic three times; the tie resolves to the first seen.
    assert letters == 6
    assert script in {"latin", "cyrillic"}


def test_tokenizer_strips_surrounding_punctuation() -> None:
    assert tokenize_for_language("Hello, world! (really?)") == ["hello", "world", "really"]


def test_function_word_list_has_no_duplicates_and_is_lowercase() -> None:
    assert len(ENGLISH_FUNCTION_WORDS) == len(set(ENGLISH_FUNCTION_WORDS))
    assert all(word.islower() for word in ENGLISH_FUNCTION_WORDS)
