"""Layer 1 — source truth: uniqueness, constraints, and the discussion tree."""

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models import Author, Community, Discussion, Source
from tests.database import factories as f


def test_source_creation_and_defaults(session: Session) -> None:
    source = f.make_source(session, "reddit")

    assert source.id is not None
    assert source.key == "reddit"
    assert source.is_active is True
    assert source.created_at is not None


def test_source_key_is_unique(session: Session) -> None:
    f.make_source(session, "reddit")

    session.add(Source(key="reddit", name="Duplicate"))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_source_key_must_be_lowercase(session: Session) -> None:
    session.add(Source(key="Reddit", name="Reddit"))

    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_community_external_id_is_unique_per_source(session: Session) -> None:
    reddit = f.make_source(session, "reddit")
    other = f.make_source(session, "hackernews")

    f.make_community(session, reddit, "technology")
    # The same external id under a different source is legitimate.
    f.make_community(session, other, "technology")

    session.add(Community(source_id=reddit.id, external_id="technology", name="Duplicate"))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_author_external_id_is_unique_per_source(session: Session) -> None:
    source = f.make_source(session)
    f.make_author(session, source, "u1")

    session.add(Author(source_id=source.id, external_id="u1"))
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_community_requires_an_existing_source(session: Session) -> None:
    """A foreign key must reject a reference to a source that does not exist."""
    from uuid import uuid4

    session.add(Community(source_id=uuid4(), external_id="ghost", name="Ghost"))

    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_discussion_creation_post_and_comment(session: Session) -> None:
    source = f.make_source(session)
    community = f.make_community(session, source)

    post = f.make_discussion(session, source, community, external_id="p1", kind="post")
    comment = f.make_discussion(
        session,
        source,
        community,
        external_id="c1",
        kind="comment",
        title=None,
        parent=post,
    )

    assert post.parent_discussion_id is None
    assert comment.parent_discussion_id == post.id
    # The self-referencing relationship resolves both directions.
    assert comment.parent is not None and comment.parent.id == post.id
    assert [child.id for child in post.children] == [comment.id]


def test_discussion_external_id_is_unique_per_source(session: Session) -> None:
    source = f.make_source(session)
    community = f.make_community(session, source)
    f.make_discussion(session, source, community, external_id="p1")

    session.add(
        Discussion(
            source_id=source.id,
            community_id=community.id,
            external_id="p1",
            kind="post",
            title="Duplicate",
            body="",
            source_created_at=f.EPOCH,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_discussion_kind_is_constrained(session: Session) -> None:
    source = f.make_source(session)
    community = f.make_community(session, source)

    session.add(
        Discussion(
            source_id=source.id,
            community_id=community.id,
            external_id="x1",
            kind="direct_message",
            title="Not a post or comment",
            body="",
            source_created_at=f.EPOCH,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_post_requires_a_title(session: Session) -> None:
    source = f.make_source(session)
    community = f.make_community(session, source)

    with pytest.raises(IntegrityError):
        f.make_discussion(session, source, community, external_id="p1", kind="post", title=None)
    session.rollback()


def test_post_cannot_have_a_parent(session: Session) -> None:
    """A post is a thread root; only comments may point at a parent."""
    source = f.make_source(session)
    community = f.make_community(session, source)
    post = f.make_discussion(session, source, community, external_id="p1", kind="post")

    with pytest.raises(IntegrityError):
        f.make_discussion(
            session, source, community, external_id="p2", kind="post", title="T", parent=post
        )
    session.rollback()


def test_discussion_cannot_be_its_own_parent(session: Session) -> None:
    source = f.make_source(session)
    community = f.make_community(session, source)
    post = f.make_discussion(session, source, community, external_id="p1", kind="post")

    # A Core UPDATE executes immediately, so the violation surfaces here rather than at flush.
    with pytest.raises(IntegrityError):
        session.execute(
            Discussion.__table__.update()
            .where(Discussion.__table__.c.id == post.id)
            .values(parent_discussion_id=post.id)
        )
    session.rollback()


def test_deleting_a_parent_cascades_to_children_in_the_database(session: Session) -> None:
    """The cascade is a database constraint, so it must hold for a Core delete too."""
    source = f.make_source(session)
    community = f.make_community(session, source)
    post = f.make_discussion(session, source, community, external_id="p1", kind="post")
    f.make_discussion(
        session, source, community, external_id="c1", kind="comment", title=None, parent=post
    )
    f.make_discussion(
        session, source, community, external_id="c2", kind="comment", title=None, parent=post
    )
    assert f.scalar_count(session, Discussion) == 3

    session.execute(delete(Discussion).where(Discussion.__table__.c.id == post.id))
    session.flush()

    assert f.scalar_count(session, Discussion) == 0


def test_orphaned_comment_is_allowed(session: Session) -> None:
    """A comment whose parent was never collected keeps a NULL parent rather than failing."""
    source = f.make_source(session)
    community = f.make_community(session, source)

    comment = f.make_discussion(
        session, source, community, external_id="c1", kind="comment", title=None
    )

    assert comment.parent_discussion_id is None


def test_deleting_an_author_nullifies_discussions_rather_than_deleting_them(
    session: Session,
) -> None:
    source = f.make_source(session)
    community = f.make_community(session, source)
    author = f.make_author(session, source, "u1")
    discussion = f.make_discussion(session, source, community, external_id="p1", author=author)

    session.execute(delete(Author).where(Author.__table__.c.id == author.id))
    session.flush()
    session.expire_all()

    assert f.scalar_count(session, Discussion) == 1
    refreshed = session.get(Discussion, discussion.id)
    assert refreshed is not None and refreshed.author_id is None
