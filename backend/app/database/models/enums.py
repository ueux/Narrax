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


def sql_in(column: str, vocabulary: type[StrEnum]) -> str:
    """Render `column IN ('a', 'b')` for use inside a CHECK constraint.

    Values come from a `StrEnum` defined in this module, never from user input, so the
    interpolation cannot be influenced externally.
    """
    allowed = ", ".join(f"'{member.value}'" for member in vocabulary)
    return f"{column} IN ({allowed})"
