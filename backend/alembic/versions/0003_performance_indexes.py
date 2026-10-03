"""Performance baseline indexes.

Every index here answers a **named** query pattern or protects a delete cascade; nothing is
indexed speculatively. The full rationale, including the indexes that were deliberately *not*
created, is in docs/database.md ("Index rationale").

PostgreSQL does not index foreign keys automatically, so the cascade indexes below are not
redundant bookkeeping — without them a delete scans the whole child table.

Revision ID: 0003_performance_indexes
Revises: 0002_core_schema
Create Date: 2026-10-03

"""

from alembic import op

revision = "0003_performance_indexes"
down_revision = "0002_core_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # "Runs for a topic" (the topic page), and the topic-delete cascade.
    op.create_index("ix_analysis_runs_topic_id", "analysis_runs", ["topic_id"])

    # "Discussions by community" plus chronological order within that community.
    op.create_index(
        "ix_discussions_community_created_at",
        "discussions",
        ["community_id", "source_created_at"],
    )
    # Chronological listing, and the run window filter (source_created_at BETWEEN ...).
    op.create_index("ix_discussions_source_created_at", "discussions", ["source_created_at"])
    # Thread reconstruction (a post's replies) and the self-referencing FK cascade.
    op.create_index("ix_discussions_parent_discussion_id", "discussions", ["parent_discussion_id"])

    # A discussion's analysis rows across runs, and the discussion-delete cascade.
    op.create_index(
        "ix_discussion_analysis_discussion_id", "discussion_analysis", ["discussion_id"]
    )

    # Members of a cluster (cluster detail view) and the cluster-delete cascade.
    op.create_index("ix_cluster_members_cluster_id", "cluster_members", ["cluster_id"])
    # Which groups a discussion belongs to across runs, and the discussion-delete cascade.
    op.create_index("ix_cluster_members_discussion_id", "cluster_members", ["discussion_id"])

    # Which narratives a discussion supports, and the discussion-delete cascade.
    op.create_index("ix_narrative_members_discussion_id", "narrative_members", ["discussion_id"])
    # Where else a discussion is cited, and the discussion-delete cascade.
    op.create_index("ix_narrative_evidence_discussion_id", "narrative_evidence", ["discussion_id"])
    # Inbound relation edges, and the narrative-delete cascade. The outbound direction is
    # already covered by the leading column of uq_narrative_relations_edge.
    op.create_index(
        "ix_narrative_relations_to_narrative_id", "narrative_relations", ["to_narrative_id"]
    )

    # Vector similarity: approximate nearest neighbour over embeddings using cosine distance.
    # Created with SQL rather than op.create_index so the HNSW access method and operator class
    # are explicit.
    op.execute(
        "CREATE INDEX ix_embeddings_embedding_hnsw ON embeddings "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_embeddings_embedding_hnsw")
    op.drop_index("ix_narrative_relations_to_narrative_id", table_name="narrative_relations")
    op.drop_index("ix_narrative_evidence_discussion_id", table_name="narrative_evidence")
    op.drop_index("ix_narrative_members_discussion_id", table_name="narrative_members")
    op.drop_index("ix_cluster_members_discussion_id", table_name="cluster_members")
    op.drop_index("ix_cluster_members_cluster_id", table_name="cluster_members")
    op.drop_index("ix_discussion_analysis_discussion_id", table_name="discussion_analysis")
    op.drop_index("ix_discussions_parent_discussion_id", table_name="discussions")
    op.drop_index("ix_discussions_source_created_at", table_name="discussions")
    op.drop_index("ix_discussions_community_created_at", table_name="discussions")
    op.drop_index("ix_analysis_runs_topic_id", table_name="analysis_runs")
