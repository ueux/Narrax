"""Small factory helpers so database tests read as scenarios, not boilerplate.

Each helper only fills the columns required by the schema; tests override what they care about.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.database.models import (
    AnalysisRun,
    Author,
    Cluster,
    ClusterMember,
    Community,
    Discussion,
    DiscussionAnalysis,
    Embedding,
    Narrative,
    NarrativeEvidence,
    NarrativeMember,
    NarrativeRelation,
    NarrativeSnapshot,
    Source,
    Topic,
    User,
)

EPOCH = datetime(2024, 1, 1, tzinfo=UTC)


def make_user(session: Session, email: str = "analyst@example.com") -> User:
    user = User(email=email, display_name="Analyst")
    session.add(user)
    session.flush()
    return user


def make_source(session: Session, key: str = "reddit") -> Source:
    source = Source(key=key, name=key.title())
    session.add(source)
    session.flush()
    return source


def make_community(session: Session, source: Source, external_id: str = "technology") -> Community:
    community = Community(source_id=source.id, external_id=external_id, name=external_id.title())
    session.add(community)
    session.flush()
    return community


def make_author(session: Session, source: Source, external_id: str = "u1") -> Author:
    author = Author(source_id=source.id, external_id=external_id)
    session.add(author)
    session.flush()
    return author


def make_discussion(
    session: Session,
    source: Source,
    community: Community,
    *,
    external_id: str = "d1",
    kind: str = "post",
    title: str | None = "A post",
    body: str = "Some text",
    parent: Discussion | None = None,
    author: Author | None = None,
) -> Discussion:
    discussion = Discussion(
        source_id=source.id,
        community_id=community.id,
        author_id=author.id if author else None,
        parent_discussion_id=parent.id if parent else None,
        external_id=external_id,
        kind=kind,
        title=title,
        body=body,
        source_created_at=EPOCH,
    )
    session.add(discussion)
    session.flush()
    return discussion


def make_topic(session: Session, name: str = "AI regulation", user: User | None = None) -> Topic:
    topic = Topic(name=name, created_by_user_id=user.id if user else None, query_terms=["ai"])
    session.add(topic)
    session.flush()
    return topic


def make_run(session: Session, topic: Topic, user: User | None = None) -> AnalysisRun:
    run = AnalysisRun(
        topic_id=topic.id,
        triggered_by_user_id=user.id if user else None,
        status="running",
    )
    session.add(run)
    session.flush()
    return run


def make_analysis(session: Session, run: AnalysisRun, discussion: Discussion) -> DiscussionAnalysis:
    analysis = DiscussionAnalysis(analysis_run_id=run.id, discussion_id=discussion.id)
    session.add(analysis)
    session.flush()
    return analysis


def make_embedding(
    session: Session,
    discussion: Discussion,
    *,
    model_name: str = "all-MiniLM-L6-v2",
    model_version: str = "1.0",
    vector: list[float] | None = None,
) -> Embedding:
    embedding = Embedding(
        discussion_id=discussion.id,
        model_name=model_name,
        model_version=model_version,
        dimensions=384,
        embedding=vector if vector is not None else [0.0] * 384,
    )
    session.add(embedding)
    session.flush()
    return embedding


def make_cluster(
    session: Session, run: AnalysisRun, *, cluster_key: str = "0", label: str = "Group A"
) -> Cluster:
    cluster = Cluster(
        analysis_run_id=run.id,
        cluster_key=cluster_key,
        label=label,
        algorithm="hdbscan",
    )
    session.add(cluster)
    session.flush()
    return cluster


def make_cluster_member(
    session: Session,
    run: AnalysisRun,
    discussion: Discussion,
    *,
    cluster: Cluster | None = None,
    is_noise: bool | None = None,
) -> ClusterMember:
    noise = cluster is None if is_noise is None else is_noise
    member = ClusterMember(
        analysis_run_id=run.id,
        cluster_id=cluster.id if cluster else None,
        discussion_id=discussion.id,
        is_noise=noise,
        distance=0.1,
    )
    session.add(member)
    session.flush()
    return member


def make_narrative(
    session: Session,
    run: AnalysisRun,
    *,
    cluster: Cluster | None = None,
    claim: str = "Regulation will stifle innovation",
    description: str = "A recurring argument in the corpus.",
) -> Narrative:
    narrative = Narrative(
        analysis_run_id=run.id,
        cluster_id=cluster.id if cluster else None,
        claim=claim,
        description=description,
        confidence=0.7,
        model_name="test-llm",
        model_version="1",
        prompt_version="narr-v1",
    )
    session.add(narrative)
    session.flush()
    return narrative


def make_evidence(
    session: Session, narrative: Narrative, discussion: Discussion, *, relevance: float = 0.9
) -> NarrativeEvidence:
    evidence = NarrativeEvidence(
        narrative_id=narrative.id,
        discussion_id=discussion.id,
        relevance=relevance,
        rationale="Directly states the claim.",
    )
    session.add(evidence)
    session.flush()
    return evidence


def make_narrative_member(
    session: Session, narrative: Narrative, discussion: Discussion
) -> NarrativeMember:
    member = NarrativeMember(narrative_id=narrative.id, discussion_id=discussion.id, relevance=0.5)
    session.add(member)
    session.flush()
    return member


def make_relation(
    session: Session,
    from_narrative: Narrative,
    to_narrative: Narrative,
    *,
    relation_type: str = "contradicts",
    inferred_by: str = "llm",
) -> NarrativeRelation:
    relation = NarrativeRelation(
        from_narrative_id=from_narrative.id,
        to_narrative_id=to_narrative.id,
        relation_type=relation_type,
        inferred_by=inferred_by,
        confidence=0.6,
    )
    session.add(relation)
    session.flush()
    return relation


def make_snapshot(
    session: Session,
    narrative: Narrative,
    *,
    as_of: datetime = EPOCH,
    member_count: int = 1,
    evidence_count: int = 1,
    share: float = 0.25,
    direction: str = "rising",
) -> NarrativeSnapshot:
    snapshot = NarrativeSnapshot(
        narrative_id=narrative.id,
        analysis_run_id=narrative.analysis_run_id,
        as_of=as_of,
        member_count=member_count,
        evidence_count=evidence_count,
        share=share,
        direction=direction,
    )
    session.add(snapshot)
    session.flush()
    return snapshot


def scalar_count(session: Session, model: type) -> int:
    """Count rows of a model — used by cascade assertions."""
    from sqlalchemy import func, select

    return session.execute(select(func.count()).select_from(model)).scalar_one()


def as_uuid(value: object) -> UUID:
    """Narrow a value the ORM types loosely."""
    assert isinstance(value, UUID)
    return value
