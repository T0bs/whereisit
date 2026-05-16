"""Helpers for the M13 \"Uncategorized\" inbox container.

The inbox is a single top-level node with kind=inbox that bulk-add and
suggest-categories use as the holding pen for uncategorized items. It's
created lazily on first use so empty DBs stay empty.
"""

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Kind, Node


INBOX_KIND_SLUG = "inbox"
INBOX_NODE_NAME = "Uncategorized"


def find_inbox(db: Session) -> Optional[Node]:
    """Return the root inbox node, or None if it hasn't been created yet."""
    return db.execute(
        select(Node)
        .join(Node.kind)
        .where(Kind.slug == INBOX_KIND_SLUG, Node.parent_id.is_(None))
        .order_by(Node.id)
        .limit(1)
    ).scalar_one_or_none()


def get_or_create_inbox(db: Session) -> Node:
    """Return the root inbox node, creating it on first use."""
    inbox = find_inbox(db)
    if inbox is not None:
        return inbox

    inbox_kind = db.execute(
        select(Kind).where(Kind.slug == INBOX_KIND_SLUG)
    ).scalar_one_or_none()
    if inbox_kind is None:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"kind {INBOX_KIND_SLUG!r} missing — run alembic upgrade head",
        )

    inbox = Node(
        name=INBOX_NODE_NAME,
        kind_id=inbox_kind.id,
        parent_id=None,
        can_contain=True,
    )
    db.add(inbox)
    db.commit()
    db.refresh(inbox)
    return inbox


def is_inbox_kind(node: Node) -> bool:
    """True iff the node is an inbox container (system-managed)."""
    return node.kind is not None and node.kind.slug == INBOX_KIND_SLUG
