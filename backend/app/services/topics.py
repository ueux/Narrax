"""Topic use-cases.

A topic is the root of the conceptual hierarchy: the selection criteria that scope collection
(docs/glossary.md). These are the operations the collection pipeline and the CLI need; richer topic
management arrives with the API in a later phase.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.database.models import Topic


def get_topic_by_name(session: Session, name: str) -> Topic | None:
    """Look a topic up by its (unique) human name."""
    return session.execute(select(Topic).where(Topic.name == name)).scalar_one_or_none()


def ensure_topic(
    session: Session,
    name: str,
    *,
    description: str | None = None,
    query_terms: tuple[str, ...] = (),
    window_start: datetime | None = None,
    window_end: datetime | None = None,
    created_by_user_id: UUID | None = None,
) -> Topic:
    """Return the topic called `name`, creating it if it does not exist.

    Idempotent by design: a developer re-running collection should not accumulate near-duplicate
    topics. Existing selection criteria are **not** overwritten — a topic's scope is a deliberate
    decision, and silently widening it would change what past runs meant.
    """
    existing = get_topic_by_name(session, name)
    if existing is not None:
        return existing

    statement = (
        pg_insert(Topic)
        .values(
            name=name,
            description=description,
            query_terms=list(query_terms),
            window_start=window_start,
            window_end=window_end,
            created_by_user_id=created_by_user_id,
        )
        # Another writer may have created it between the lookup and the insert.
        .on_conflict_do_update(index_elements=["name"], set_={"updated_at": func.now()})
        .returning(Topic.id)
    )
    topic_id = session.execute(statement).scalar_one()
    session.flush()
    topic = session.get(Topic, topic_id)
    if topic is None:  # pragma: no cover - defensive
        raise RuntimeError(f"topic {name!r} vanished immediately after being upserted")
    return topic
