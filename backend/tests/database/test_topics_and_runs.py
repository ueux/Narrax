"""Operator identity, topics, analysis runs, and run stages."""

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models import AnalysisRun, RunStage, Topic, User
from tests.database import factories as f


def test_user_creation(session: Session) -> None:
    user = f.make_user(session, "analyst@example.com")

    assert user.id is not None
    assert user.email == "analyst@example.com"
    assert user.is_active is True


def test_user_email_is_unique(session: Session) -> None:
    f.make_user(session, "analyst@example.com")

    session.add(User(email="analyst@example.com", display_name="Impostor"))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_user_email_must_be_lowercase(session: Session) -> None:
    session.add(User(email="Analyst@Example.com", display_name="Analyst"))

    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_user_email_must_look_like_an_email(session: Session) -> None:
    session.add(User(email="not-an-email", display_name="Analyst"))

    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_topic_creation_with_owner(session: Session) -> None:
    user = f.make_user(session)
    topic = f.make_topic(session, "AI regulation", user=user)

    assert topic.id is not None
    assert topic.name == "AI regulation"
    assert topic.query_terms == ["ai"]
    assert topic.created_by_user_id == user.id


def test_topic_name_is_unique(session: Session) -> None:
    f.make_topic(session, "AI regulation")

    session.add(Topic(name="AI regulation"))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_topic_window_must_be_ordered(session: Session) -> None:
    session.add(
        Topic(
            name="Backwards window",
            window_start=f.datetime(2024, 6, 1, tzinfo=f.UTC),
            window_end=f.datetime(2024, 1, 1, tzinfo=f.UTC),
        )
    )

    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_analysis_run_creation(session: Session) -> None:
    user = f.make_user(session)
    topic = f.make_topic(session, user=user)
    run = f.make_run(session, topic, user=user)

    assert run.id is not None
    assert run.topic_id == topic.id
    assert run.status == "running"
    assert run.config == {}


def test_analysis_run_requires_a_topic(session: Session) -> None:
    from uuid import uuid4

    session.add(AnalysisRun(topic_id=uuid4(), status="pending"))

    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_analysis_run_status_is_constrained(session: Session) -> None:
    topic = f.make_topic(session)

    session.add(AnalysisRun(topic_id=topic.id, status="finished"))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_run_stage_is_unique_per_run(session: Session) -> None:
    run = f.make_run(session, f.make_topic(session))
    session.add(RunStage(analysis_run_id=run.id, stage="embed", status="succeeded"))
    session.flush()

    session.add(RunStage(analysis_run_id=run.id, stage="embed", status="failed"))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_run_stage_name_is_constrained(session: Session) -> None:
    run = f.make_run(session, f.make_topic(session))

    session.add(RunStage(analysis_run_id=run.id, stage="summarise_everything", status="pending"))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_run_stage_counts_must_be_consistent(session: Session) -> None:
    run = f.make_run(session, f.make_topic(session))

    session.add(
        RunStage(
            analysis_run_id=run.id,
            stage="ingest",
            status="succeeded",
            items_in=10,
            items_out=10,
            items_dropped=5,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_deleting_a_topic_cascades_to_runs_and_stages(session: Session) -> None:
    topic = f.make_topic(session)
    run = f.make_run(session, topic)
    session.add(RunStage(analysis_run_id=run.id, stage="ingest", status="succeeded"))
    session.flush()

    session.execute(delete(Topic).where(Topic.__table__.c.id == topic.id))
    session.flush()

    assert f.scalar_count(session, AnalysisRun) == 0
    assert f.scalar_count(session, RunStage) == 0


def test_deleting_an_operator_keeps_the_topic(session: Session) -> None:
    user = f.make_user(session)
    topic = f.make_topic(session, user=user)

    session.execute(delete(User).where(User.__table__.c.id == user.id))
    session.flush()
    session.expire_all()

    refreshed = session.get(Topic, topic.id)
    assert refreshed is not None
    assert refreshed.created_by_user_id is None
