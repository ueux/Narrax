"""Language detection — deterministic, dependency-free, and honest about its limits.

The MVP is English-only, so the pipeline needs one answer: *is this plausibly English?* It must
be **deterministic** (so cleaning is reproducible) and must not require a model download (so
tests are hermetic and CI is fast).

The detector therefore reports two *asymmetric* confidences rather than a single language label:

* `english_confidence` — evidence that the text is English;
* `non_english_confidence` — evidence that it is **not**.

The asymmetry is intentional. Dropping a genuine English comment from the corpus is worse than
keeping some foreign text, which the embedding and clustering stages tolerate. So the cleaner
only excludes when `non_english_confidence` is high, and passes short or ambiguous text through
as undetermined.

This is a **coarse filter, not a language identifier**: it reliably separates non-Latin scripts
and clearly-foreign Latin text from English, and makes no claim beyond that. A model-based
detector can replace it by implementing `LanguageDetector` — nothing else changes.

References: docs/ingestion.md §5
"""

import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

# Scripts that cannot be English. Presence of one, at scale, is conclusive.
NON_LATIN_SCRIPTS = frozenset(
    {
        "arabic",
        "armenian",
        "bengali",
        "cyrillic",
        "devanagari",
        "ethiopic",
        "georgian",
        "greek",
        "gujarati",
        "gurmukhi",
        "han",
        "hangul",
        "hebrew",
        "kana",
        "khmer",
        "lao",
        "malayalam",
        "myanmar",
        "sinhala",
        "tamil",
        "telugu",
        "thai",
    }
)

# The highest-frequency English function words. Content words vary by topic; function words do
# not, which is what makes them a stable signal.
ENGLISH_FUNCTION_WORDS = frozenset(
    [
        "a",
        "about",
        "above",
        "after",
        "again",
        "against",
        "all",
        "am",
        "an",
        "and",
        "any",
        "are",
        "aren't",
        "as",
        "at",
        "be",
        "because",
        "been",
        "before",
        "being",
        "below",
        "between",
        "both",
        "but",
        "by",
        "can",
        "can't",
        "cannot",
        "could",
        "couldn't",
        "did",
        "didn't",
        "do",
        "does",
        "doesn't",
        "doing",
        "don't",
        "down",
        "during",
        "each",
        "few",
        "for",
        "from",
        "further",
        "had",
        "hadn't",
        "has",
        "hasn't",
        "have",
        "haven't",
        "having",
        "he",
        "he'd",
        "he'll",
        "he's",
        "her",
        "here",
        "here's",
        "hers",
        "herself",
        "him",
        "himself",
        "his",
        "how",
        "how's",
        "i",
        "i'd",
        "i'll",
        "i'm",
        "i've",
        "if",
        "in",
        "into",
        "is",
        "isn't",
        "it",
        "it's",
        "its",
        "itself",
        "let's",
        "me",
        "more",
        "most",
        "mustn't",
        "my",
        "myself",
        "no",
        "nor",
        "not",
        "of",
        "off",
        "on",
        "once",
        "only",
        "or",
        "other",
        "ought",
        "our",
        "ours",
        "ourselves",
        "out",
        "over",
        "own",
        "same",
        "shan't",
        "she",
        "she'd",
        "she'll",
        "she's",
        "should",
        "shouldn't",
        "so",
        "some",
        "such",
        "than",
        "that",
        "that's",
        "the",
        "their",
        "theirs",
        "them",
        "themselves",
        "then",
        "there",
        "there's",
        "these",
        "they",
        "they'd",
        "they'll",
        "they're",
        "they've",
        "this",
        "those",
        "through",
        "to",
        "too",
        "under",
        "until",
        "up",
        "very",
        "was",
        "wasn't",
        "we",
        "we'd",
        "we'll",
        "we're",
        "we've",
        "were",
        "weren't",
        "what",
        "what's",
        "when",
        "when's",
        "where",
        "where's",
        "which",
        "while",
        "who",
        "who's",
        "whom",
        "why",
        "why's",
        "with",
        "won't",
        "would",
        "wouldn't",
        "you",
        "you'd",
        "you'll",
        "you're",
        "you've",
        "your",
        "yours",
        "yourself",
        "yourselves",
    ]
)

# Characters that separate words but carry no language signal of their own.
_WORD_SPLIT_EXTRAS = "—–…“”‘’«»"


@dataclass(frozen=True, slots=True)
class LanguageGuess:
    """What the detector concluded about one piece of text."""

    language: str
    """Best guess as an ISO 639-1 code, or `"und"` when the evidence is too weak to name one."""

    english_confidence: float
    """0–1. How strongly the text looks English."""

    non_english_confidence: float
    """0–1. How strongly the text looks *not* English. The cleaner's exclusion signal."""

    script: str
    """Dominant writing system of the letters: `"latin"`, `"cyrillic"`, `"han"`, `"none"`, ..."""

    @property
    def is_english(self) -> bool:
        return self.language == "en"


@runtime_checkable
class LanguageDetector(Protocol):
    """Replaceable language detection."""

    def detect(self, text: str) -> LanguageGuess:
        """Classify `text`. Must be deterministic for identical input."""
        ...


def dominant_script(text: str) -> tuple[str, int]:
    """Return the most common writing system among the letters, and how many letters there were."""
    counts: Counter[str] = Counter()
    for character in text:
        if not character.isalpha():
            continue
        counts[_script_of(character)] += 1

    if not counts:
        return "none", 0
    return counts.most_common(1)[0][0], sum(counts.values())


def _script_of(character: str) -> str:
    """Map a single letter to a coarse script name."""
    name = unicodedata.name(character, "")
    if not name:
        return "other"
    first = name.split(" ", 1)[0]
    if first == "LATIN":
        return "latin"
    if first in {"CJK", "IDEOGRAPHIC"}:
        return "han"
    if first in {"HIRAGANA", "KATAKANA"}:
        return "kana"
    lowered = first.lower()
    return lowered if lowered in NON_LATIN_SCRIPTS else "other"


def tokenize_for_language(text: str) -> list[str]:
    """Split text into comparable word tokens.

    Lowered, and stripped of surrounding punctuation — enough for function-word matching without
    pulling in a tokenizer dependency.
    """
    tokens: list[str] = []
    for raw in text.split():
        token = raw.strip(_WORD_SPLIT_EXTRAS + ".,;:!?()[]{}<>\"'`*_~|/\\-+=#@&^%$")
        if token:
            tokens.append(token.lower())
    return tokens


class HeuristicLanguageDetector:
    """Script analysis plus English function-word frequency.

    Deterministic, fast, and dependency-free. See the module docstring for what it does and does
    not claim.
    """

    # Below this many tokens, function-word frequency is noise rather than signal.
    min_tokens_for_frequency = 5
    # A non-Latin script must cover at least this share of letters to be conclusive.
    min_non_latin_share = 0.5
    # Function-word ratio at or above this reads as English.
    english_ratio = 0.08
    # Ratio at or below this, with enough tokens, reads as not-English.
    foreign_ratio = 0.02

    def detect(self, text: str) -> LanguageGuess:
        script, letter_count = dominant_script(text)
        tokens = tokenize_for_language(text)
        token_count = len(tokens)

        if letter_count == 0:
            return LanguageGuess("und", 0.0, 0.0, "none")

        # A predominantly non-Latin script is conclusive: English is written in Latin letters.
        if script != "latin":
            latin_share = self._latin_share(text, letter_count)
            if 1.0 - latin_share >= self.min_non_latin_share:
                return LanguageGuess("und", 0.0, 0.9, script)

        if token_count < self.min_tokens_for_frequency:
            # Too little text to judge. Reported as undetermined, which the cleaner keeps.
            return LanguageGuess("und", 0.2, 0.0, script)

        hits = sum(1 for token in tokens if token in ENGLISH_FUNCTION_WORDS)
        ratio = hits / token_count

        if ratio >= self.english_ratio:
            # Scale within the English band so confidence is monotonic in the evidence.
            confidence = min(0.97, 0.6 + (ratio - self.english_ratio) * 2.0)
            return LanguageGuess("en", round(confidence, 3), 0.0, script)

        if ratio <= self.foreign_ratio:
            return LanguageGuess("und", 0.0, 0.6, script)

        return LanguageGuess("und", round(ratio / self.english_ratio * 0.5, 3), 0.0, script)

    @staticmethod
    def _latin_share(text: str, letter_count: int) -> float:
        latin = sum(
            1 for character in text if character.isalpha() and _script_of(character) == "latin"
        )
        return latin / letter_count if letter_count else 0.0


DEFAULT_LANGUAGE_DETECTOR: LanguageDetector = HeuristicLanguageDetector()
