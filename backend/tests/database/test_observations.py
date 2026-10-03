"""Layer 2 — ML observations: analysis records, embeddings, clusters, membership."""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.database.models import ClusterMember, DiscussionAnalysis, Embedding
from tests.database import factories as f

DIM = 384


def _unit_vector(index: int) -> list[float]:
    """A one-hot unit vector, so cosine distances are exactly 0 or 1."""
    vector = [0.0] * DIM
    vector[index] = 1.0
    return vector


def test_analysis_record_creation(session: Session) -> None:
    source = f.make_source(session)
    community = f.make_community(session, source)
    discussion = f.make_discussion(session, source, community)
    run = f.make_run(session, f.make_topic(session))

    analysis = f.make_analysis(session, run, discussion)

    assert analysis.id is not None
    # Language is not stored here: it belongs to `text_preparation`, being a property of the text
    # rather than of a run.
    assert not hasattr(analysis, "language")
    assert analysis.sentiment_label is None


def test_analysis_record_is_unique_per_run_and_discussion(session: Session) -> None:
    source = f.make_source(session)
    community = f.make_community(session, source)
    discussion = f.make_discussion(session, source, community)
    run = f.make_run(session, f.make_topic(session))
    f.make_analysis(session, run, discussion)

    session.add(DiscussionAnalysis(analysis_run_id=run.id, discussion_id=discussion.id))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_analysis_labels_are_constrained(session: Session) -> None:
    source = f.make_source(session)
    community = f.make_community(session, source)
    discussion = f.make_discussion(session, source, community)
    run = f.make_run(session, f.make_topic(session))

    session.add(
        DiscussionAnalysis(
            analysis_run_id=run.id, discussion_id=discussion.id, sentiment_label="elated"
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_stance_label_and_confidence_are_constrained(session: Session) -> None:
    source = f.make_source(session)
    community = f.make_community(session, source)
    discussion = f.make_discussion(session, source, community)
    run = f.make_run(session, f.make_topic(session))

    session.add(
        DiscussionAnalysis(
            analysis_run_id=run.id,
            discussion_id=discussion.id,
            stance_label="support",
            stance_confidence=1.5,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_sentiment_score_range_is_enforced(session: Session) -> None:
    source = f.make_source(session)
    community = f.make_community(session, source)
    discussion = f.make_discussion(session, source, community)
    run = f.make_run(session, f.make_topic(session))

    session.add(
        DiscussionAnalysis(
            analysis_run_id=run.id, discussion_id=discussion.id, sentiment_score=-2.0
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_embedding_creation_and_version_uniqueness(session: Session) -> None:
    source = f.make_source(session)
    community = f.make_community(session, source)
    discussion = f.make_discussion(session, source, community)

    embedding = f.make_embedding(session, discussion, model_name="m1", model_version="1")
    assert embedding.id is not None
    assert len(embedding.embedding) == DIM

    # A different model version for the same discussion is a new observation, not a conflict.
    f.make_embedding(session, discussion, model_name="m1", model_version="2")

    # The same (discussion, model, version) is a duplicate.
    session.add(
        Embedding(
            discussion_id=discussion.id,
            model_name="m1",
            model_version="1",
            dimensions=DIM,
            embedding=[0.0] * DIM,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_embedding_dimension_metadata_is_enforced(session: Session) -> None:
    source = f.make_source(session)
    community = f.make_community(session, source)
    discussion = f.make_discussion(session, source, community)

    session.add(
        Embedding(
            discussion_id=discussion.id,
            model_name="m1",
            model_version="1",
            dimensions=768,
            embedding=[0.0] * DIM,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_embedding_vector_dimension_is_enforced_by_pgvector(session: Session) -> None:
    source = f.make_source(session)
    community = f.make_community(session, source)
    discussion = f.make_discussion(session, source, community)

    session.add(
        Embedding(
            discussion_id=discussion.id,
            model_name="m1",
            model_version="1",
            dimensions=DIM,
            embedding=[0.0, 1.0, 2.0],
        )
    )
    with pytest.raises(DBAPIError):
        session.flush()
    session.rollback()


def test_embedding_similarity_ordering(session: Session) -> None:
    """Vector similarity search works and orders by cosine distance."""
    source = f.make_source(session)
    community = f.make_community(session, source)
    first = f.make_discussion(session, source, community, external_id="d1")
    second = f.make_discussion(session, source, community, external_id="d2")
    f.make_embedding(session, first, vector=_unit_vector(0))
    f.make_embedding(session, second, vector=_unit_vector(1))

    distance = Embedding.embedding.cosine_distance(_unit_vector(0)).label("distance")
    rows = session.execute(select(Embedding.discussion_id, distance).order_by(distance)).all()

    assert [row[0] for row in rows] == [first.id, second.id]
    assert rows[0][1] == pytest.approx(0.0, abs=1e-6)
    assert rows[1][1] == pytest.approx(1.0, abs=1e-6)


def test_cluster_creation_and_key_uniqueness_per_run(session: Session) -> None:
    topic = f.make_topic(session)
    run = f.make_run(session, topic)
    f.make_cluster(session, run, cluster_key="0")

    # The same key in another run is fine.
    f.make_cluster(session, f.make_run(session, topic), cluster_key="0")

    from app.database.models import Cluster

    session.add(Cluster(analysis_run_id=run.id, cluster_key="0", algorithm="hdbscan"))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_cluster_membership_links_a_discussion_to_a_cluster(session: Session) -> None:
    source = f.make_source(session)
    community = f.make_community(session, source)
    discussion = f.make_discussion(session, source, community)
    run = f.make_run(session, f.make_topic(session))
    cluster = f.make_cluster(session, run)

    member = f.make_cluster_member(session, run, discussion, cluster=cluster)

    assert member.cluster_id == cluster.id
    assert member.is_noise is False


def test_noise_membership_has_no_cluster(session: Session) -> None:
    source = f.make_source(session)
    community = f.make_community(session, source)
    discussion = f.make_discussion(session, source, community)
    run = f.make_run(session, f.make_topic(session))

    noise = f.make_cluster_member(session, run, discussion, cluster=None)

    assert noise.cluster_id is None
    assert noise.is_noise is True


def test_noise_flag_and_cluster_must_agree(session: Session) -> None:
    source = f.make_source(session)
    community = f.make_community(session, source)
    discussion = f.make_discussion(session, source, community)
    run = f.make_run(session, f.make_topic(session))
    cluster = f.make_cluster(session, run)

    session.add(
        ClusterMember(
            analysis_run_id=run.id,
            cluster_id=cluster.id,
            discussion_id=discussion.id,
            is_noise=True,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_discussion_belongs_to_at_most_one_group_per_run(session: Session) -> None:
    source = f.make_source(session)
    community = f.make_community(session, source)
    discussion = f.make_discussion(session, source, community)
    run = f.make_run(session, f.make_topic(session))
    first = f.make_cluster(session, run, cluster_key="0")
    second = f.make_cluster(session, run, cluster_key="1")
    f.make_cluster_member(session, run, discussion, cluster=first)

    session.add(
        ClusterMember(analysis_run_id=run.id, cluster_id=second.id, discussion_id=discussion.id)
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_membership_cannot_reference_a_cluster_from_another_run(session: Session) -> None:
    """The composite foreign key keeps a membership and its cluster in the same run."""
    source = f.make_source(session)
    community = f.make_community(session, source)
    discussion = f.make_discussion(session, source, community)
    topic = f.make_topic(session)
    run_a = f.make_run(session, topic)
    run_b = f.make_run(session, topic)
    cluster_a = f.make_cluster(session, run_a)

    session.add(
        ClusterMember(
            analysis_run_id=run_b.id, cluster_id=cluster_a.id, discussion_id=discussion.id
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()
