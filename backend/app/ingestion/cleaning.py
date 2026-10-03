"""Deterministic text cleaning — turning collected source text into analysable text.

Cleaning answers two questions per item:

1. **Is this usable?** If not, *why not* — recorded as a reason, never dropped silently.
2. **What is the analysable text?** With platform formatting, links and markup removed, and
   meaningful language preserved.

Design rules
------------
* **Deterministic.** The same input always yields the same result, including the exclusion
  reason. No randomness, no model inference in this stage.
* **Versioned.** `CleaningRules.version()` fingerprints the configuration; every result is
  stored against it, so changing a threshold produces new records rather than silently
  redefining old ones.
* **Ordered.** Reasons are evaluated in a fixed order — `structural → empty → noise →
  repetition → language → link-dominated → length → low-information` — so a given input has
  exactly one reason, chosen by the *most specific applicable* rule. The order is not arbitrary:
  language precedes the length gate (scripts without word spacing would otherwise look "short"),
  repetition precedes language (repeated English slang must not read as foreign), and
  link-dominated precedes length (a bare link is a link problem, not a brevity problem).
* **Conservative.** The stage removes formatting, not meaning. It never rewrites the stored
  source text — that stays untouched in `discussions` — and it keeps ambiguous content rather
  than guessing.

Raw text is never modified: this produces a **separate derived record**.

References: docs/ingestion.md §5 · docs/data-flow.md §3 (S2)
"""

import hashlib
import html
import json
import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import datetime

from app.database.models.enums import ExclusionReason
from app.ingestion.language import (
    DEFAULT_LANGUAGE_DETECTOR,
    ENGLISH_FUNCTION_WORDS,
    LanguageDetector,
    LanguageGuess,
    tokenize_for_language,
)
from app.ingestion.normalized import ContentState

__all__ = [
    "CleaningResult",
    "CleaningRules",
    "DEFAULT_CLEANING_RULES",
    "DuplicateCandidate",
    "ExclusionReason",
    "clean_text",
    "duplicate_key",
    "find_duplicate_indices",
    "normalize_whitespace",
    "rules_version",
    "strip_formatting",
]


@dataclass(frozen=True, slots=True)
class CleaningRules:
    """Thresholds for the cleaning stage.

    Frozen and hashable, so a fingerprint of exactly these values can version every result.
    """

    min_characters: int = 16
    min_words: int = 3
    min_letter_share: float = 0.5
    max_char_run_share: float = 0.5
    max_token_dominance: float = 0.6
    min_tokens_for_repetition: int = 6
    max_url_share: float = 0.5
    allowed_languages: tuple[str, ...] = ("en",)
    min_non_english_confidence: float = 0.6

    def version(self) -> str:
        """Stable fingerprint of these rules — the `pipeline_version` stored with results."""
        canonical = json.dumps(asdict(self), sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


DEFAULT_CLEANING_RULES = CleaningRules()

_DEFAULT_RULES_VERSION = DEFAULT_CLEANING_RULES.version()


@dataclass(frozen=True, slots=True)
class CleaningResult:
    """The outcome of cleaning one item."""

    is_usable: bool
    reason: ExclusionReason | None
    cleaned_text: str
    content_hash: str
    language: str
    language_confidence: float
    script: str
    character_count: int
    word_count: int
    url_count: int
    formatting_artifact_count: int
    detail: str | None = None

    def describe(self) -> str:
        """One-line summary, useful in run reports."""
        if self.is_usable:
            return f"usable ({self.word_count} words, {self.language})"
        return (
            f"excluded: {self.reason} ({self.detail})"
            if self.detail
            else f"excluded: {self.reason}"
        )


# --- transformations -------------------------------------------------------------------

_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\((?:[^()]|\([^()]*\))*\)")
_LINK_RE = re.compile(r"\[([^\]]*)\]\((?:[^()]|\([^()]*\))*\)")
_MENTION_RE = re.compile(r"(?<![\w/])(?:u|r)/[A-Za-z0-9_\-]{2,}", re.IGNORECASE)
_HTML_TAG_RE = re.compile(
    r"</?(?:a|b|blockquote|br|code|div|em|hr|i|img|li|ol|p|pre|span|strong|sub|sup|table|td|th|tr|ul)\b[^>]*>",
    re.IGNORECASE,
)
_ESCAPE_RE = re.compile(r"\\([\\`*_{}\[\]()#+\-.!>~|])")
_FENCE_RE = re.compile(r"^```[^\n]*$", re.MULTILINE)
_RULE_LINE_RE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$", re.MULTILINE)
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
_QUOTE_RE = re.compile(r"^\s{0,3}>+\s?", re.MULTILINE)
# Emphasis markers and inline-code fences, removed outright. `_` is deliberately left alone so
# snake_case identifiers survive intact, which matters for technical corpora.
_EMPHASIS_RE = re.compile(r"[*~`]+")
_CONTROL_RE = re.compile(r"[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]")
_ZERO_WIDTH_RE = re.compile("[\u200b-\u200f\u202a-\u202e\ufeff]")
_HORIZONTAL_WS_RE = re.compile(r"[^\S\n]+")
_MANY_NEWLINES_RE = re.compile(r"\n{3,}")


def strip_formatting(text: str) -> tuple[str, int, int]:
    """Remove platform formatting, returning `(text, url_count, artifact_count)`.

    Order matters: markdown links are resolved **before** bare URLs are removed, otherwise the
    URL inside `[label](url)` is stripped first and the leftover brackets never match.
    """
    # Counted on the original text so the metric reflects what the author actually posted.
    url_count = len(_URL_RE.findall(text))
    artifacts = 0

    # An image contributes no analysable text; a link keeps its label, which a human wrote.
    text, substitutions = _IMAGE_RE.subn(" ", text)
    artifacts += substitutions
    text, substitutions = _LINK_RE.subn(r"\1", text)
    artifacts += substitutions

    # Bare URLs carry no analysable language, and a placeholder token would pollute vocabulary.
    text = _URL_RE.sub(" ", text)

    for pattern, replacement in (
        (_MENTION_RE, " "),
        (_HTML_TAG_RE, " "),
        (_ESCAPE_RE, r"\1"),
        (_FENCE_RE, ""),
        (_RULE_LINE_RE, ""),
        (_HEADING_RE, ""),
        (_QUOTE_RE, ""),
        (_EMPHASIS_RE, ""),
    ):
        text, substitutions = pattern.subn(replacement, text)
        artifacts += substitutions

    return text, url_count, artifacts


def normalize_whitespace(text: str) -> str:
    """Collapse runs of whitespace while keeping paragraph breaks readable."""
    text = _HORIZONTAL_WS_RE.sub(" ", text)
    text = _MANY_NEWLINES_RE.sub("\n\n", text)
    return "\n".join(line.strip() for line in text.split("\n")).strip()


def duplicate_key(cleaned_text: str) -> str:
    """Hash used to detect the same content posted more than once.

    Case- and spacing-insensitive, because "This is wrong" and "this is wrong" are the same
    contribution to a corpus.
    """
    normalized = _HORIZONTAL_WS_RE.sub(" ", cleaned_text.lower()).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _longest_char_run(text: str) -> int:
    longest = current = 1
    for previous, character in zip(text, text[1:], strict=False):
        current = current + 1 if character == previous else 1
        longest = max(longest, current)
    return longest if text else 0


def _looks_repetitive(text: str, tokens: Sequence[str], rules: CleaningRules) -> bool:
    """Detect padding rather than composition: a repeated character, token, or line."""
    if len(text) >= rules.min_characters and _longest_char_run(text) / len(text) >= (
        rules.max_char_run_share
    ):
        return True

    if len(tokens) >= rules.min_tokens_for_repetition:
        most_common = Counter(tokens).most_common(1)[0][1]
        if most_common / len(tokens) >= rules.max_token_dominance:
            return True

    lines = [line for line in text.split("\n") if line.strip()]
    return len(lines) > 1 and len(set(lines)) == 1


def _letter_share(text: str) -> float:
    """Share of non-space characters that are letters — low values mean emoji or symbol soup."""
    considered = [character for character in text if not character.isspace()]
    if not considered:
        return 0.0
    return sum(1 for character in considered if character.isalpha()) / len(considered)


def _has_content_word(tokens: Sequence[str]) -> bool:
    """Whether any token is a real term rather than a function word or a fragment."""
    return any(
        len(token) >= 3 and token.isalpha() and token not in ENGLISH_FUNCTION_WORDS
        for token in tokens
    )


# --- the pipeline ----------------------------------------------------------------------


def clean_text(
    text: str | None,
    *,
    content_state: ContentState = ContentState.PRESENT,
    rules: CleaningRules = DEFAULT_CLEANING_RULES,
    detector: LanguageDetector = DEFAULT_LANGUAGE_DETECTOR,
) -> CleaningResult:
    """Clean one item's text and decide whether it belongs in the analysable corpus.

    Args:
        text: the source text (a post's title and body joined, or a comment's body). May be
            `None` when the platform omitted it.
        content_state: whether the platform still serves the body.
        rules: thresholds; their fingerprint is stored alongside the result.
        detector: language detector; injectable so tests need no model and production can swap
            in something stronger.

    Returns:
        A `CleaningResult`. `is_usable=False` always carries a `reason`.
    """
    # 1. Structural: the platform itself says the content is gone.
    if content_state is ContentState.DELETED:
        return _excluded(ExclusionReason.DELETED_CONTENT, "marked deleted")
    if content_state is ContentState.REMOVED:
        return _excluded(ExclusionReason.REMOVED_CONTENT, "marked removed")
    if content_state is ContentState.UNAVAILABLE:
        return _excluded(ExclusionReason.MISSING_SOURCE_TEXT, "body not served")
    if text is None:
        return _excluded(ExclusionReason.MISSING_SOURCE_TEXT, "no body field")

    original_length = len(text)

    # 2. Normalize, then strip formatting and links.
    working = unicodedata.normalize("NFKC", text)
    working = html.unescape(working)
    working = _CONTROL_RE.sub("", working)
    working = _ZERO_WIDTH_RE.sub("", working)
    working, url_count, artifact_count = strip_formatting(working)
    working = normalize_whitespace(working)

    cleaned = _Cleaned.of(working, url_count=url_count, artifact_count=artifact_count)

    if not working:
        return cleaned.exclude(ExclusionReason.EMPTY_CONTENT, "nothing left after cleaning")

    tokens = tokenize_for_language(working)

    # 3. Symbol/emoji dominance. Checked before the length gate so an emoji wall is reported as
    # noise rather than as merely short.
    letter_share = _letter_share(working)
    if letter_share < rules.min_letter_share:
        return cleaned.exclude(
            ExclusionReason.EXCESSIVE_NOISE,
            f"only {letter_share:.0%} of characters are letters",
        )

    # 4. Padding rather than composition. Checked before language so that repeated English slang
    # ("lol lol lol ...") is not mistaken for foreign text by the function-word heuristic.
    if _looks_repetitive(working, tokens, rules):
        return cleaned.exclude(ExclusionReason.REPETITIVE_CONTENT, "heavily repeated content")

    # 5. Language. Checked before the length gate because scripts that do not separate words with
    # spaces (Chinese, Japanese) tokenise to a single "word" and would otherwise be reported as
    # merely short.
    guess = detector.detect(working)
    if (
        guess.language not in rules.allowed_languages
        and guess.non_english_confidence >= rules.min_non_english_confidence
    ):
        return cleaned.exclude(
            ExclusionReason.NON_ENGLISH,
            f"detected {guess.language} ({guess.script}), confidence "
            f"{guess.non_english_confidence:.2f}",
        )

    # 6. Mostly a link. Checked before the length gate: text that is largely a URL is better
    # reported as link-dominated than as merely short, because that is the actual problem.
    if original_length and url_count:
        url_characters = sum(len(match) for match in _URL_RE.findall(text))
        if url_characters / original_length >= rules.max_url_share:
            return cleaned.exclude(
                ExclusionReason.LINK_DOMINATED, f"{url_characters / original_length:.0%} is URL"
            )

    # 7. Length gate.
    if len(working) < rules.min_characters:
        return cleaned.exclude(
            ExclusionReason.TOO_SHORT, f"{len(working)} characters < {rules.min_characters}"
        )
    if len(tokens) < rules.min_words:
        return cleaned.exclude(
            ExclusionReason.TOO_SHORT, f"{len(tokens)} words < {rules.min_words}"
        )

    # 8. Grammatical but contentless.
    if not _has_content_word(tokens):
        return cleaned.exclude(ExclusionReason.LOW_INFORMATION, "no distinct terms")

    return cleaned.accept(guess)


@dataclass(frozen=True, slots=True)
class _Cleaned:
    """The fields every exit path shares, computed once per item."""

    cleaned_text: str
    tokens: tuple[str, ...]
    content_hash: str
    url_count: int
    formatting_artifact_count: int

    @classmethod
    def of(cls, cleaned_text: str, *, url_count: int, artifact_count: int) -> "_Cleaned":
        return cls(
            cleaned_text=cleaned_text,
            tokens=tuple(tokenize_for_language(cleaned_text)),
            content_hash=duplicate_key(cleaned_text) if cleaned_text else "",
            url_count=url_count,
            formatting_artifact_count=artifact_count,
        )

    def accept(self, guess: LanguageGuess) -> CleaningResult:
        return self._make(is_usable=True, reason=None, detail=None, guess=guess)

    def exclude(self, reason: ExclusionReason, detail: str) -> CleaningResult:
        return self._make(is_usable=False, reason=reason, detail=detail, guess=None)

    def _make(
        self,
        *,
        is_usable: bool,
        reason: ExclusionReason | None,
        detail: str | None,
        guess: LanguageGuess | None,
    ) -> CleaningResult:
        return CleaningResult(
            is_usable=is_usable,
            reason=reason,
            cleaned_text=self.cleaned_text,
            content_hash=self.content_hash,
            language=guess.language if guess else "und",
            language_confidence=guess.english_confidence if guess else 0.0,
            script=guess.script if guess else "none",
            character_count=len(self.cleaned_text),
            word_count=len(self.tokens),
            url_count=self.url_count,
            formatting_artifact_count=self.formatting_artifact_count,
            detail=detail,
        )


def _excluded(reason: ExclusionReason, detail: str) -> CleaningResult:
    """Build an exclusion result for content that never reached cleaning."""
    return CleaningResult(
        is_usable=False,
        reason=reason,
        cleaned_text="",
        content_hash="",
        language="und",
        language_confidence=0.0,
        script="none",
        character_count=0,
        word_count=0,
        url_count=0,
        formatting_artifact_count=0,
        detail=detail,
    )


# --- corpus-level duplicate detection ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class DuplicateCandidate:
    """One item's identity for duplicate detection."""

    index: int
    content_hash: str
    source_created_at: datetime
    external_id: str


def find_duplicate_indices(
    candidates: Sequence[DuplicateCandidate],
    *,
    seen_hashes: frozenset[str] | set[str] | None = None,
) -> dict[int, str]:
    """Find items whose content duplicates something else.

    The rule is deliberately simple and fully deterministic: candidates are considered in
    `(source_created_at, external_id, index)` order, and the **first occurrence of a hash wins**.
    Anything whose hash was already claimed — earlier in this batch, or already recorded for this
    cleaning version (`seen_hashes`) — is returned as a duplicate mapped to its hash.

    Consequence worth knowing: the keeper is the first occurrence *considered*, not necessarily
    the earliest ever authored. Re-ingesting an older duplicate later therefore flags the older
    item rather than re-seating the keeper. That is documented in docs/ingestion.md §5 with its
    revisit trigger; a re-evaluation pass is a later concern, not a correctness bug for the MVP.
    """
    ordered = sorted(
        candidates, key=lambda item: (item.source_created_at, item.external_id, item.index)
    )
    claimed = set(seen_hashes or ())
    duplicates: dict[int, str] = {}

    for candidate in ordered:
        if not candidate.content_hash:
            continue
        if candidate.content_hash in claimed:
            duplicates[candidate.index] = candidate.content_hash
        else:
            claimed.add(candidate.content_hash)

    return duplicates


def rules_version(rules: CleaningRules | None = None) -> str:
    """Fingerprint of the active cleaning rules."""
    return (rules or DEFAULT_CLEANING_RULES).version()
