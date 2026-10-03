"""The normalized discussion model — NarraX's source-neutral Layer 1 representation.

This is the **contract between ingestion and everything else**. Adapters convert platform
payloads into these types; the intelligence pipeline, services and API consume them and never
import a platform-specific shape (PROMPT 14). Two consequences follow:

- swapping or adding a platform changes only the adapter;
- platform quirks are resolved *here*, once, instead of leaking into analysis code.

The model is deliberately close to the `discussions` table it becomes, with no derived fields:
no embeddings, no sentiment, no cleaning decisions. Those belong to later layers.

References: docs/ingestion.md · docs/database.md · docs/adr/0009-epistemic-layer-separation.md
"""

from datetime import datetime
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DiscussionKind(StrEnum):
    """A top-level post, or a reply to something."""

    POST = "post"
    COMMENT = "comment"


class ContentState(StrEnum):
    """Whether the platform still serves the body of an item.

    Platforms express this with sentinel strings (`[deleted]`, `[removed]`) or by omitting the
    body entirely. Translating that into a vocabulary is a normalization win: the cleaning
    stage acts on `ContentState.REMOVED` instead of pattern-matching `"[removed]"`, and a
    platform that expresses removal differently needs no change above the adapter.
    """

    PRESENT = "present"
    DELETED = "deleted"
    REMOVED = "removed"
    UNAVAILABLE = "unavailable"


class NormalizedEngagement(BaseModel):
    """Public engagement counts, as observed at retrieval time.

    Explicitly *not* an analytic signal: these numbers are mutable at the source and are kept
    for provenance, ranking sanity checks, and representativeness assessment only.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    score: int | None = None
    comment_count: int | None = None
    upvote_ratio: float | None = None


class NormalizedDiscussion(BaseModel):
    """One collected post or comment, platform-agnostic.

    Invariants enforced here (and mirrored by database CHECK constraints) so that bad data fails
    at the adapter boundary rather than during a database insert:

    * all timestamps are timezone-aware;
    * identifiers and communities are non-blank;
    * a post has a title; a comment does not need one;
    * an item whose body the platform no longer serves must say so via `content_state`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # --- identity -------------------------------------------------------------------
    source_key: str
    """Platform key, e.g. `"reddit"`. Becomes `sources.key`."""

    external_id: str
    """The platform's own stable identifier for this item (globally unique within the source)."""

    kind: DiscussionKind

    parent_external_id: str | None = None
    """`external_id` of the item this one replies to; `None` for posts and orphaned comments."""

    # --- placement ------------------------------------------------------------------
    community_external_id: str
    """The platform's identifier for the community, e.g. a subreddit name. Normalized to
    lower case, since platforms treat community names case-insensitively."""

    community_name: str
    """Display name for the community."""

    author_external_id: str | None = None
    """Pseudonymous handle. `None` when the platform no longer attributes the item (a deleted
    account). Never enriched — see docs/data-safety.md."""

    # --- content --------------------------------------------------------------------
    title: str | None = None
    body: str = ""
    """Source text, **unmodified**. Cleaning happens downstream and never rewrites this."""

    url: str | None = None
    """Canonical public URL for the item."""

    source_created_at: datetime
    """When the platform says the item was written."""

    collected_at: datetime
    """When NarraX retrieved it."""

    content_state: ContentState = ContentState.PRESENT

    # --- metadata -------------------------------------------------------------------
    engagement: NormalizedEngagement = Field(default_factory=NormalizedEngagement)
    """Public engagement counts as observed."""

    metadata: dict[str, Any] = Field(default_factory=dict)
    """Source-specific extras worth keeping verbatim (flair, flags, moderation state). Stored as
    JSONB, so it stays open-ended without forcing a schema change per platform field."""

    @field_validator("source_key", "external_id", "community_external_id", "community_name")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value

    @field_validator("source_created_at", "collected_at")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ValueError("timestamps must be timezone-aware")
        return value

    @field_validator("community_external_id")
    @classmethod
    def _lowercase_community(cls, value: str) -> str:
        return value.lower()

    @field_validator("parent_external_id")
    @classmethod
    def _parent_optional(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("parent_external_id must be null or non-blank")
        return value

    @model_validator(mode="after")
    def _kind_consistency(self) -> Self:
        if self.kind is DiscussionKind.POST:
            if not (self.title or "").strip():
                raise ValueError("a post must have a non-blank title")
            if self.parent_external_id is not None:
                raise ValueError("a post is a thread root and cannot have a parent")
        elif self.kind is DiscussionKind.COMMENT and self.parent_external_id == self.external_id:
            raise ValueError("a comment cannot be its own parent")
        return self

    @property
    def is_post(self) -> bool:
        return self.kind is DiscussionKind.POST

    @property
    def is_comment(self) -> bool:
        return self.kind is DiscussionKind.COMMENT

    @property
    def has_readable_body(self) -> bool:
        """Whether the platform still serves text for this item."""
        return self.content_state is ContentState.PRESENT and bool(self.body.strip())

    def analysis_input(self) -> tuple[str | None, ContentState]:
        """The text to clean, and the content state to clean it under.

        The two fields are returned together because neither is meaningful alone:

        * A post's **title survives moderation even when its body does not**, so a post with a
          removed body still has analysable text. Treating it as removed would discard a real
          contribution the author made.
        * A comment has no such second field — once its body is gone, the item is gone.
        """
        if self.is_post:
            parts = [self.title or ""]
            if self.content_state is ContentState.PRESENT:
                parts.append(self.body)
            text = "\n".join(part for part in parts if part.strip())
            if text.strip():
                return text, ContentState.PRESENT
            return None, self.content_state

        if self.content_state is not ContentState.PRESENT:
            return None, self.content_state
        return self.body, ContentState.PRESENT
