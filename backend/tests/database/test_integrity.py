"""Cross-layer integrity: foreign keys, lifecycle cascades, epistemic separation, and the
index contract.
"""

from uuid import uuid4

import pytest
from sqlalchemy import delete, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models import (
    AnalysisRun,
    Cluster,
    ClusterMember,
    Discussion,
    DiscussionAnalysis,
    Embedding,
    Narrative,
    NarrativeEvidence,
    NarrativeRelation,
    NarrativeSnapshot,
    Source,
    Topic,
)
from tests.database import factories as f

EXPECTED_INDEXES = {
    "ix_analysis_runs_topic_id",
    "ix_cluster_members_cluster_id",
    "ix_cluster_members_discussion_id",
    "ix_discussion_analysis_discussion_id",
    "ix_discussions_community_created_at",
    "ix_discussions_parent_discussion_id",
    "ix_discussions_source_created_at",
    "ix_embeddings_embedding_hnsw",
    "ix_narrative_evidence_discussion_id",
    "ix_narrative_members_discussion_id",
    "ix_narrative_relations_to_narrative_id",
}


def test_derived_rows_require_existing_source_items(session: Session) -> None:
    run = f.make_run(session, f.make_topic(session))

    session.add(DiscussionAnalysis(analysis_run_id=run.id, discussion_id=uuid4()))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_cluster_requires_an_existing_run(session: Session) -> None:
    session.add(Cluster(analysis_run_id=uuid4(), cluster_key="0", algorithm="hdbscan"))

    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_deleting_a_run_removes_every_derived_layer(session: Session) -> None:
    """Layer 2–4 rows belong to a run, so removing the run removes them all."""
    source = f.make_source(session)
    community = f.make_community(session, source)
    discussion = f.make_discussion(session, source, community)
    run = f.make_run(session, f.make_topic(session))
    f.make_analysis(session, run, discussion)
    f.make_embedding(session, discussion)
    cluster = f.make_cluster(session, run)
    f.make_cluster_member(session, run, discussion, cluster=cluster)
    narrative = f.make_narrative(session, run, cluster=cluster)
    f.make_narrative_member(session, narrative, discussion)
    f.make_evidence(session, narrative, discussion)
    f.make_snapshot(session, narrative)

    session.execute(delete(AnalysisRun).where(AnalysisRun.__table__.c.id == run.id))
    session.flush()

    assert f.scalar_count(session, DiscussionAnalysis) == 0
    assert f.scalar_count(session, Cluster) == 0
    assert f.scalar_count(session, ClusterMember) == 0
    assert f.scalar_count(session, Narrative) == 0
    assert f.scalar_count(session, NarrativeEvidence) == 0
    assert f.scalar_count(session, NarrativeSnapshot) == 0
    # Source truth is untouched by derived-data cleanup.
    assert f.scalar_count(session, Discussion) == 1


def test_topic_deletion_preserves_source_truth_and_text_observations(session: Session) -> None:
    """Interpretations belong to a topic; the text they were derived from does not."""
    source = f.make_source(session)
    community = f.make_community(session, source)
    discussion = f.make_discussion(session, source, community)
    topic = f.make_topic(session)
    run = f.make_run(session, topic)
    narrative = f.make_narrative(session, run)
    f.make_snapshot(session, narrative)
    f.make_embedding(session, discussion)

    session.execute(delete(Topic).where(Topic.__table__.c.id == topic.id))
    session.flush()
    session.expire_all()

    assert f.scalar_count(session, Narrative) == 0
    assert f.scalar_count(session, NarrativeSnapshot) == 0
    assert f.scalar_count(session, Discussion) == 1
    # An embedding is a property of the text and the model, so it outlives the topic, with its
    # run provenance cleared rather than cascading the row away.
    assert f.scalar_count(session, Embedding) == 1
    assert session.execute(text("SELECT created_by_run_id FROM embeddings")).scalar() is None


def test_deleting_a_source_cascades_to_its_communities_and_discussions(session: Session) -> None:
    source = f.make_source(session)
    community = f.make_community(session, source)
    f.make_discussion(session, source, community)

    session.execute(delete(Source).where(Source.__table__.c.id == source.id))
    session.flush()

    assert f.scalar_count(session, Discussion) == 0


def test_relation_cascade_removes_edges_pointing_at_a_deleted_narrative(session: Session) -> None:
    run = f.make_run(session, f.make_topic(session))
    first = f.make_narrative(session, run, claim="Claim A")
    second = f.make_narrative(session, run, claim="Claim B")
    f.make_relation(session, first, second)
    f.make_relation(session, second, first, relation_type="refines")

    session.execute(delete(Narrative).where(Narrative.__table__.c.id == second.id))
    session.flush()

    assert f.scalar_count(session, NarrativeRelation) == 0
    assert f.scalar_count(session, Narrative) == 1


def test_discussions_carry_timezone_aware_timestamps(session: Session) -> None:
    source = f.make_source(session)
    community = f.make_community(session, source)
    discussion = f.make_discussion(session, source, community)
    session.refresh(discussion)

    assert discussion.created_at.tzinfo is not None
    assert discussion.collected_at.tzinfo is not None


def test_expected_performance_indexes_exist(session: Session) -> None:
    """The index set is a reviewed contract, not an accident — so it is asserted."""
    rows = (
        session.execute(text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'"))
        .scalars()
        .all()
    )

    missing = EXPECTED_INDEXES - set(rows)
    assert not missing, f"missing indexes: {sorted(missing)}"


def test_embedding_index_uses_hnsw(session: Session) -> None:
    access_method = session.execute(
        text(
            "SELECT am.amname FROM pg_class c "
            "JOIN pg_index i ON i.indexrelid = c.oid "
            "JOIN pg_am am ON am.oid = c.relam "
            "WHERE c.relname = 'ix_embeddings_embedding_hnsw'"
        )
    ).scalar()

    assert access_method == "hnsw"
