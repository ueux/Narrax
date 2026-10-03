"""Controlled vocabularies for columns stored as text with a CHECK constraint.

PostgreSQL native `ENUM` types are deliberately avoided: adding a value requires
`ALTER TYPE`, which is awkward inside transactional migrations and cannot be reordered,
whereas a text column plus a CHECK constraint is replaced by dropping and re-adding one
constraint. See docs/database.md, "Why text + CHECK instead of native enums".
"""

from enum import StrEnum


class DiscussionKind(StrEnum):
    """A discussion is either a top-level post or a reply."""

    POST = "post"
    COMMENT = "comment"


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"
    CANCELLED = "cancelled"


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class Stage(StrEnum):
    """Pipeline stages, in execution order.

    Constrained by a CHECK so a typo cannot create a phantom stage. Renaming or adding a stage
    is therefore a deliberate, visible schema change rather than an accidental one.
    """

    INGEST = "ingest"
    NORMALIZE = "normalize"
    EMBED = "embed"
    CLUSTER = "cluster"
    SENTIMENT_STANCE = "sentiment_stance"
    NARRATIVES = "narratives"
    RELATIONS = "relations"
    SNAPSHOT = "snapshot"


class SentimentLabel(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class StanceLabel(StrEnum):
    """Stance is always relative to the topic of the owning analysis run."""

    SUPPORT = "support"
    OPPOSE = "oppose"
    NEUTRAL = "neutral"
    UNCLEAR = "unclear"


class RelationType(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    REFINES = "refines"
    CO_OCCURS_WITH = "co_occurs_with"


class InferredBy(StrEnum):
    """How a narrative relation was inferred (kept explicit for provenance)."""

    ML_SIMILARITY = "ml_similarity"
    LLM = "llm"
    HUMAN = "human"


class TrendDirection(StrEnum):
    RISING = "rising"
    STABLE = "stable"
    FADING = "fading"
    UNKNOWN = "unknown"


class ExclusionReason(StrEnum):
    """Why a collected item is not part of the analysable corpus.

    Lives here, with every other controlled vocabulary, because the database CHECK constraint and
    the cleaning stage must share one definition: "every exclusion is recorded, and its reason is
    one of these" only holds if both sides read the same list (docs/ingestion.md §5).
    """

    MISSING_SOURCE_TEXT = "missing_source_text"
    """The platform served no body field at all."""

    DELETED_CONTENT = "deleted_content"
    """The author deleted it."""

    REMOVED_CONTENT = "removed_content"
    """A moderator or the platform removed it."""

    EMPTY_CONTENT = "empty_content"
    """Blank, whitespace-only, or reduced to nothing once formatting was stripped."""

    TOO_SHORT = "too_short"
    """Below the minimum length — not enough language to analyse."""

    EXCESSIVE_NOISE = "excessive_noise"
    """Mostly symbols, emoji, or a single repeated character rather than language."""

    REPETITIVE_CONTENT = "repetitive_content"
    """The same token, line, or phrase repeated rather than composed."""

    LINK_DOMINATED = "link_dominated"
    """Mostly a URL; carries little analysable text of its own."""

    DUPLICATE_CONTENT = "duplicate_content"
    """The same text was already collected elsewhere in the corpus.

    Assigned at corpus level rather than per item — deciding whether a text is a duplicate requires
    seeing the rest of the corpus, which a single-item pass cannot do.
    """

    NON_ENGLISH = "non_english"
    """Confidently not English, which is outside the MVP's scope."""

    LOW_INFORMATION = "low_information"
    """Grammatical but contentless — only function words, no distinct terms."""


def sql_in(column: str, vocabulary: type[StrEnum]) -> str:
    """Render `column IN ('a', 'b')` for use inside a CHECK constraint.

    Values come from a `StrEnum` defined in this module, never from user input, so the
    interpolation cannot be influenced externally.
    """
    allowed = ", ".join(f"'{member.value}'" for member in vocabulary)
    return f"{column} IN ({allowed})"
