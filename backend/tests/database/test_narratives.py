"""Layer 3 and 4 — narratives, evidence, relations, and snapshots."""

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models import (
    Narrative,
    NarrativeEvidence,
    NarrativeMember,
    NarrativeRelation,
    NarrativeSnapshot,
)
from tests.database import factories as f


def test_narrative_creation_and_generated_claim_hash(session: Session) -> None:
    run = f.make_run(session, f.make_topic(session))

    narrative = f.make_narrative(session, run, claim="Regulation will stifle innovation")
    session.refresh(narrative)

    assert narrative.id is not None
    assert narrative.analysis_run_id == run.id
    # claim_hash is computed by PostgreSQL, not by the application.
    assert len(narrative.claim_hash) == 64
    assert narrative.claim_hash == narrative.claim_hash.lower()


def test_claim_hash_is_stable_for_the_same_claim(session: Session) -> None:
    topic = f.make_topic(session)
    claim = "Regulation will stifle innovation"

    first = f.make_narrative(session, f.make_run(session, topic), claim=claim)
    session.refresh(first)
    second = f.make_narrative(session, f.make_run(session, topic), claim=claim)
    session.refresh(second)

    assert first.claim_hash == second.claim_hash


def test_identical_claim_is_rejected_within_one_run(session: Session) -> None:
    run = f.make_run(session, f.make_topic(session))
    f.make_narrative(session, run, claim="Same claim")

    session.add(
        Narrative(
            analysis_run_id=run.id,
            claim="Same claim",
            description="Duplicate",
            model_name="test-llm",
            prompt_version="narr-v1",
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_narrative_requires_run_provenance(session: Session) -> None:
    run = f.make_run(session, f.make_topic(session))

    session.add(
        Narrative(
            analysis_run_id=run.id,
            claim="A claim",
            description="A description",
            model_name="test-llm",
            prompt_version="",
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_narrative_confidence_range_is_enforced(session: Session) -> None:
    run = f.make_run(session, f.make_topic(session))

    session.add(
        Narrative(
            analysis_run_id=run.id,
            claim="A claim",
            description="A description",
            confidence=2.0,
            model_name="test-llm",
            prompt_version="narr-v1",
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_narrative_cannot_reference_a_cluster_from_another_run(session: Session) -> None:
    topic = f.make_topic(session)
    run_a = f.make_run(session, topic)
    run_b = f.make_run(session, topic)
    cluster_a = f.make_cluster(session, run_a)

    session.add(
        Narrative(
            analysis_run_id=run_b.id,
            cluster_id=cluster_a.id,
            claim="A claim",
            description="A description",
            model_name="test-llm",
            prompt_version="narr-v1",
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_narrative_members_and_evidence_are_distinct_relations(session: Session) -> None:
    source = f.make_source(session)
    community = f.make_community(session, source)
    first = f.make_discussion(session, source, community, external_id="d1")
    second = f.make_discussion(session, source, community, external_id="d2")
    narrative = f.make_narrative(session, f.make_run(session, f.make_topic(session)))

    member = f.make_narrative_member(session, narrative, first)
    evidence = f.make_evidence(session, narrative, second)

    assert member.narrative_id == narrative.id
    assert evidence.narrative_id == narrative.id
    assert member.discussion_id != evidence.discussion_id


def test_membership_and_evidence_are_unique_per_pair(session: Session) -> None:
    source = f.make_source(session)
    community = f.make_community(session, source)
    discussion = f.make_discussion(session, source, community)
    narrative = f.make_narrative(session, f.make_run(session, f.make_topic(session)))
    f.make_narrative_member(session, narrative, discussion)
    f.make_evidence(session, narrative, discussion)

    session.add(NarrativeMember(narrative_id=narrative.id, discussion_id=discussion.id))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()

    session.add(NarrativeEvidence(narrative_id=narrative.id, discussion_id=discussion.id))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_relation_creation_and_edge_uniqueness(session: Session) -> None:
    topic = f.make_topic(session)
    run = f.make_run(session, topic)
    first = f.make_narrative(session, run, claim="Claim A")
    second = f.make_narrative(session, run, claim="Claim B")

    relation = f.make_relation(session, first, second, relation_type="contradicts")
    assert relation.id is not None

    session.add(
        NarrativeRelation(
            from_narrative_id=first.id,
            to_narrative_id=second.id,
            relation_type="contradicts",
            inferred_by="llm",
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_relation_type_and_provenance_are_constrained(session: Session) -> None:
    run = f.make_run(session, f.make_topic(session))
    first = f.make_narrative(session, run, claim="Claim A")
    second = f.make_narrative(session, run, claim="Claim B")

    session.add(
        NarrativeRelation(
            from_narrative_id=first.id,
            to_narrative_id=second.id,
            relation_type="causes",
            inferred_by="llm",
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()

    session.add(
        NarrativeRelation(
            from_narrative_id=first.id,
            to_narrative_id=second.id,
            relation_type="supports",
            inferred_by="vibes",
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_narrative_cannot_relate_to_itself(session: Session) -> None:
    narrative = f.make_narrative(session, f.make_run(session, f.make_topic(session)))

    session.add(
        NarrativeRelation(
            from_narrative_id=narrative.id,
            to_narrative_id=narrative.id,
            relation_type="supports",
            inferred_by="llm",
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_snapshot_creation(session: Session) -> None:
    narrative = f.make_narrative(session, f.make_run(session, f.make_topic(session)))

    snapshot = f.make_snapshot(session, narrative, member_count=3, evidence_count=2, share=0.4)

    assert snapshot.id is not None
    assert snapshot.narrative_id == narrative.id
    assert snapshot.analysis_run_id == narrative.analysis_run_id
    assert snapshot.member_count == 3
    assert snapshot.direction == "rising"


def test_snapshot_is_unique_per_narrative_and_run(session: Session) -> None:
    narrative = f.make_narrative(session, f.make_run(session, f.make_topic(session)))
    f.make_snapshot(session, narrative)

    session.add(
        NarrativeSnapshot(
            narrative_id=narrative.id,
            analysis_run_id=narrative.analysis_run_id,
            as_of=f.EPOCH,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_snapshot_values_are_constrained(session: Session) -> None:
    narrative = f.make_narrative(session, f.make_run(session, f.make_topic(session)))

    session.add(
        NarrativeSnapshot(
            narrative_id=narrative.id,
            analysis_run_id=narrative.analysis_run_id,
            as_of=f.EPOCH,
            share=1.5,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()

    session.add(
        NarrativeSnapshot(
            narrative_id=narrative.id,
            analysis_run_id=narrative.analysis_run_id,
            as_of=f.EPOCH,
            direction="exploding",
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_snapshot_cannot_reference_another_runs_narrative(session: Session) -> None:
    """The composite foreign key keeps a snapshot and its narrative in the same run."""
    topic = f.make_topic(session)
    run_a = f.make_run(session, topic)
    run_b = f.make_run(session, topic)
    narrative_a = f.make_narrative(session, run_a, claim="Claim A")

    session.add(
        NarrativeSnapshot(narrative_id=narrative_a.id, analysis_run_id=run_b.id, as_of=f.EPOCH)
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_deleting_a_narrative_cascades_to_its_derived_rows(session: Session) -> None:
    source = f.make_source(session)
    community = f.make_community(session, source)
    discussion = f.make_discussion(session, source, community)
    run = f.make_run(session, f.make_topic(session))
    first = f.make_narrative(session, run, claim="Claim A")
    second = f.make_narrative(session, run, claim="Claim B")
    f.make_narrative_member(session, first, discussion)
    f.make_evidence(session, first, discussion)
    f.make_relation(session, first, second)
    f.make_snapshot(session, first)

    session.execute(delete(Narrative).where(Narrative.__table__.c.id == first.id))
    session.flush()

    assert f.scalar_count(session, Narrative) == 1
    assert f.scalar_count(session, NarrativeMember) == 0
    assert f.scalar_count(session, NarrativeEvidence) == 0
    assert f.scalar_count(session, NarrativeRelation) == 0
    assert f.scalar_count(session, NarrativeSnapshot) == 0
