"""The cleaning pipeline: realistic text in, one deterministic verdict out.

Every exclusion the pipeline can produce is exercised with a realistic example, because the value
of this stage is that corpus size is always explainable. Examples are written the way Reddit
actually renders them — markdown, escaped characters, links, `u/` mentions, sentinel strings.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.database.models.enums import ExclusionReason
from app.ingestion.cleaning import (
    DEFAULT_CLEANING_RULES,
    CleaningRules,
    DuplicateCandidate,
    clean_text,
    duplicate_key,
    find_duplicate_indices,
    strip_formatting,
)
from app.ingestion.normalized import ContentState

USABLE_COMMENT = (
    "The audit requirement only applies above the compute threshold, which is set high enough "
    "that volunteer projects are unaffected."
)
BASE_TIME = datetime(2024, 1, 1, tzinfo=UTC)


def clean(text: str | None, state: ContentState = ContentState.PRESENT, **kwargs: object):
    return clean_text(text, content_state=state, **kwargs)  # type: ignore[arg-type]


# --- structural exclusions ----------------------------------------------------------------


def test_deleted_content_is_excluded_with_its_own_reason() -> None:
    result = clean("[deleted]", ContentState.DELETED)

    assert result.is_usable is False
    assert result.reason is ExclusionReason.DELETED_CONTENT


def test_removed_content_is_excluded_with_its_own_reason() -> None:
    result = clean("[removed]", ContentState.REMOVED)

    assert result.reason is ExclusionReason.REMOVED_CONTENT


def test_missing_body_is_distinguished_from_empty_body() -> None:
    assert clean(None).reason is ExclusionReason.MISSING_SOURCE_TEXT
    assert clean("   \n\t ").reason is ExclusionReason.EMPTY_CONTENT


# --- formatting ---------------------------------------------------------------------------


def test_markdown_is_stripped_but_the_writing_survives() -> None:
    body = (
        "**The real question** is who pays for the audit.\n\n"
        "> Voluntary commitments have no enforcement mechanism.\n\n"
        "```\naudit_cost = time * specialists\n```\n\n"
        "See [the write-up](https://example.com/writeup) for the details of the proposal."
    )

    result = clean(body)

    assert result.is_usable is True
    assert "**" not in result.cleaned_text
    assert "```" not in result.cleaned_text
    assert "https://example.com/writeup" not in result.cleaned_text
    assert "The real question is who pays for the audit." in result.cleaned_text
    assert "the write-up" in result.cleaned_text
    assert result.formatting_artifact_count > 0


def test_helper_markdown_survives_without_an_http_looking_url() -> None:
    """A bare URL inside a markdown link must not defeat the link parser.

    Regression guard: stripping URLs before resolving links leaves `[label](` behind.
    """
    text, url_count, _ = strip_formatting("See [the summary](https://example.gov/bill) now.")

    assert text.strip() == "See the summary now."
    assert url_count == 1


def test_html_entities_and_escapes_are_decoded() -> None:
    result = clean("Fish &amp; chips &gt; everything, and \\*not\\* a footnote here at all.")

    assert "&amp;" not in result.cleaned_text
    assert "&" in result.cleaned_text
    assert "\\*" not in result.cleaned_text


def test_platform_mentions_are_removed() -> None:
    result = clean("As u/legalthrowaway explained in r/legaladvice, the provision is ambiguous.")

    assert "u/legalthrowaway" not in result.cleaned_text
    assert "r/legaladvice" not in result.cleaned_text
    assert "the provision is ambiguous" in result.cleaned_text


def test_whitespace_is_collapsed_but_paragraphs_survive() -> None:
    result = clean("First   line.\n\n\n\n\nSecond\t\tline.   ")

    assert result.cleaned_text == "First line.\n\nSecond line."


def test_underscores_are_preserved_for_identifiers() -> None:
    """Stripping `_` would merge snake_case identifiers; only markup characters are removed."""
    result = clean("Calling read_model_snapshot twice is safe because the function is idempotent.")

    assert "read_model_snapshot" in result.cleaned_text


# --- content quality ----------------------------------------------------------------------


def test_url_only_content_is_excluded() -> None:
    result = clean("https://example.com/some/very/long/path/that/keeps/going/and/going/forever")

    assert result.is_usable is False
    assert result.reason in {ExclusionReason.EMPTY_CONTENT, ExclusionReason.LINK_DOMINATED}


def test_text_that_is_mostly_a_link_is_excluded() -> None:
    result = clean(
        "Here https://example.com/a/very/long/analysis/of/the/audit/provisions/and/more/text"
    )

    assert result.is_usable is False
    assert result.reason is ExclusionReason.LINK_DOMINATED


def test_repeated_slang_is_excluded_as_repetitive() -> None:
    result = clean("lol lol lol lol lol lol lol lol")

    assert result.reason is ExclusionReason.REPETITIVE_CONTENT


def test_a_repeated_single_character_is_excluded_as_noise() -> None:
    result = clean("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")

    assert result.is_usable is False
    assert result.reason in {ExclusionReason.EXCESSIVE_NOISE, ExclusionReason.REPETITIVE_CONTENT}


def test_emoji_wall_is_excluded_as_noise() -> None:
    result = clean("🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉")

    assert result.reason is ExclusionReason.EXCESSIVE_NOISE


def test_very_short_content_is_excluded_as_too_short() -> None:
    assert clean("This.").reason is ExclusionReason.TOO_SHORT
    assert clean("ok").reason is ExclusionReason.TOO_SHORT


def test_grammatical_but_contentless_text_is_low_information() -> None:
    result = clean("it is what it is and that is that for you and me")

    assert result.reason is ExclusionReason.LOW_INFORMATION


def test_non_english_content_is_excluded() -> None:
    result = clean(
        "Dieser Vorschlag würde kleine Unternehmen stark belasten, weil die Kosten für "
        "unabhängige Audits sehr hoch sind."
    )

    assert result.reason is ExclusionReason.NON_ENGLISH


# --- ordering -----------------------------------------------------------------------------


def test_reason_order_prefers_the_most_specific_applicable_rule() -> None:
    """Non-Latin text is reported as `non_english`, not as merely short.

    Scripts that do not separate words with spaces tokenise to a single "word", so a length check
    placed before the language check would mislabel all of them.
    """
    result = clean("这是一个很长的中文句子,用来测试语言检测是否能够正确识别非英语的文本内容。")

    assert result.reason is ExclusionReason.NON_ENGLISH


def test_repeated_english_slang_is_not_mistaken_for_a_foreign_language() -> None:
    """Repetition is checked before language so the function-word heuristic cannot misfire."""
    result = clean("lol lol lol lol lol lol lol lol")

    assert result.reason is ExclusionReason.REPETITIVE_CONTENT


def test_a_post_title_alone_is_enough_to_be_analysable() -> None:
    """A post whose body was removed still contributes its title."""
    result = clean(
        "Auditors say they cannot evaluate frontier models without access to training data"
    )

    assert result.is_usable is True
    assert result.word_count >= 3


# --- determinism and versioning -----------------------------------------------------------


def test_cleaning_is_deterministic() -> None:
    first = clean(USABLE_COMMENT)
    second = clean(USABLE_COMMENT)

    assert first == second


def test_rules_fingerprint_is_stable_and_sensitive() -> None:
    baseline = CleaningRules()
    stricter = CleaningRules(min_words=8)

    assert baseline.version() == CleaningRules().version()
    assert baseline.version() != stricter.version()
    assert len(baseline.version()) == 12


def test_tightening_a_threshold_changes_the_verdict() -> None:
    text = "Audit costs are the whole argument here."

    assert clean(text).is_usable is True
    assert clean(text, rules=CleaningRules(min_words=10)).is_usable is False


def test_language_filter_is_governed_by_its_confidence_threshold() -> None:
    """The heuristic names English positively and reports everything else as `und` with a
    confidence, so the filter is a threshold rather than a language list.

    `allowed_languages` states the English-only MVP restriction explicitly and is ready for a
    detector that can name other languages; today the threshold is what decides.
    """
    german = "Dieser Vorschlag würde kleine Unternehmen stark belasten, weil die Kosten hoch sind."

    assert clean(german).reason is ExclusionReason.NON_ENGLISH
    relaxed = CleaningRules(min_non_english_confidence=0.99)
    assert clean(german, rules=relaxed).is_usable is True


def test_permissive_language_rules_keep_english_text() -> None:
    """Widening `allowed_languages` must never start rejecting English."""
    widened = CleaningRules(allowed_languages=("en", "de", "fr"))

    assert clean(USABLE_COMMENT, rules=widened).is_usable is True


def test_metrics_are_reported_for_usable_content() -> None:
    result = clean(USABLE_COMMENT)

    assert result.character_count == len(result.cleaned_text)
    assert result.word_count > 0
    assert result.content_hash
    assert result.language == "en"


def test_excluded_items_still_explain_themselves() -> None:
    result = clean("This.")

    assert result.detail is not None
    assert "characters" in result.detail or "words" in result.detail


# --- duplicate detection ------------------------------------------------------------------


def test_duplicate_key_ignores_case_and_spacing() -> None:
    assert duplicate_key("This is wrong") == duplicate_key("this   is wrong")


def test_duplicate_key_distinguishes_different_text() -> None:
    assert duplicate_key("This is wrong") != duplicate_key("This is right")


def test_first_occurrence_in_time_order_is_the_keeper() -> None:
    candidates = [
        DuplicateCandidate(0, "hash-a", BASE_TIME + timedelta(hours=2), "t1_late"),
        DuplicateCandidate(1, "hash-a", BASE_TIME, "t1_early"),
    ]

    duplicates = find_duplicate_indices(candidates)

    assert duplicates == {0: "hash-a"}


def test_ties_are_broken_by_external_id_so_the_result_is_stable() -> None:
    candidates = [
        DuplicateCandidate(0, "hash-a", BASE_TIME, "t1_z"),
        DuplicateCandidate(1, "hash-a", BASE_TIME, "t1_a"),
    ]

    duplicates = find_duplicate_indices(candidates)

    # `t1_a` sorts first and is therefore the keeper, so the duplicate is index 0.
    assert duplicates == {0: "hash-a"}
    # Reversing the input must not change the verdict: index travels with the candidate, so the
    # keeper is chosen by content and time, never by arrival order.
    assert find_duplicate_indices(list(reversed(candidates))) == {0: "hash-a"}


def test_hashes_already_recorded_make_an_item_a_duplicate() -> None:
    candidates = [DuplicateCandidate(0, "hash-a", BASE_TIME, "t1_a")]

    assert find_duplicate_indices(candidates, seen_hashes={"hash-a"}) == {0: "hash-a"}
    assert find_duplicate_indices(candidates, seen_hashes={"hash-b"}) == {}


def test_items_without_a_hash_are_never_duplicates() -> None:
    candidates = [
        DuplicateCandidate(0, "", BASE_TIME, "t1_a"),
        DuplicateCandidate(1, "", BASE_TIME, "t1_b"),
    ]

    assert find_duplicate_indices(candidates) == {}


@pytest.mark.parametrize(
    ("text", "expected_usable"),
    [
        (USABLE_COMMENT, True),
        ("Short but real.", False),
        ("The threshold is set above what volunteer projects can reach.", True),
    ],
)
def test_usable_verdicts_are_stable_across_representative_inputs(
    text: str, expected_usable: bool
) -> None:
    assert clean(text).is_usable is expected_usable


def test_default_rules_are_used_when_none_are_given() -> None:
    assert clean(USABLE_COMMENT) == clean(USABLE_COMMENT, rules=DEFAULT_CLEANING_RULES)
