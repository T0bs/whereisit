from sqlalchemy.orm import Session
from typing import List, Optional

from . import models


# Items
def create_item(db: Session, *, name: str, description: Optional[str] = None, tags: Optional[list] = None):
    item = models.Item(name=name, description=description)
    db.add(item)
    if tags:
        # attach tag objects, creating tags if necessary
        for tname in tags:
            tname = tname.strip()
            if not tname:
                continue
            tag = db.query(models.Tag).filter_by(name=tname).first()
            if not tag:
                tag = models.Tag(name=tname)
                db.add(tag)
                db.flush()
            item.tag_objs.append(tag)
    db.commit()
    db.refresh(item)
    return item


def get_item(db: Session, item_id: int):
    return db.get(models.Item, item_id)


def list_items(db: Session, skip: int = 0, limit: int = 100) -> List[models.Item]:
    return db.query(models.Item).offset(skip).limit(limit).all()


def update_item(db: Session, item: models.Item, **fields):
    tags = fields.pop('tags', None)
    for k, v in fields.items():
        if v is not None and hasattr(item, k):
            setattr(item, k, v)
    if tags is not None:
        # replace tag associations
        item.tag_objs.clear()
        for tname in tags:
            tname = tname.strip()
            if not tname:
                continue
            tag = db.query(models.Tag).filter_by(name=tname).first()
            if not tag:
                tag = models.Tag(name=tname)
                db.add(tag)
                db.flush()
            item.tag_objs.append(tag)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def delete_item(db: Session, item: models.Item):
    db.delete(item)
    db.commit()


# Containers
def create_container(db: Session, *, name: str, **kwargs):
    # If no view_id provided, default to the 'front' view
    if kwargs.get('view_id') is None:
        front = db.query(models.View).filter_by(name='front').first()
        if front:
            kwargs['view_id'] = front.id
    container = models.Container(name=name, **kwargs)
    db.add(container)
    db.commit()
    db.refresh(container)
    return container


def get_container(db: Session, container_id: int):
    return db.get(models.Container, container_id)


def list_containers(db: Session, skip: int = 0, limit: int = 100) -> List[models.Container]:
    return db.query(models.Container).offset(skip).limit(limit).all()


def update_container(db: Session, container: models.Container, **fields):
    for k, v in fields.items():
        if v is not None and hasattr(container, k):
            setattr(container, k, v)
    db.add(container)
    db.commit()
    db.refresh(container)
    return container


def delete_container(db: Session, container: models.Container):
    db.delete(container)
    db.commit()


# Placements (ItemLocation)
def create_placement(db: Session, *, item_id: int, container_id: int, quantity: int = 1):
    placement = models.ItemLocation(item_id=item_id, container_id=container_id, quantity=quantity)
    db.add(placement)
    db.commit()
    db.refresh(placement)
    return placement


def get_placement(db: Session, placement_id: int):
    return db.get(models.ItemLocation, placement_id)


def list_placements(db: Session, skip: int = 0, limit: int = 100):
    return db.query(models.ItemLocation).offset(skip).limit(limit).all()


def delete_placement(db: Session, placement: models.ItemLocation):
    db.delete(placement)
    db.commit()


def list_items_in_container(db: Session, container_id: int):
    return (
        db.query(models.Item)
        .join(models.ItemLocation, models.Item.id == models.ItemLocation.item_id)
        .filter(models.ItemLocation.container_id == container_id)
        .all()
    )


# Tags
def get_tag(db: Session, tag_id: int):
    return db.get(models.Tag, tag_id)


def get_tag_by_name(db: Session, name: str):
    return db.query(models.Tag).filter_by(name=name).first()


def get_tags(db: Session, q: Optional[str] = None, skip: int = 0, limit: int = 100):
    query = db.query(models.Tag)
    if q:
        pattern = f"%{q}%"
        query = query.filter(models.Tag.name.ilike(pattern))
    return query.offset(skip).limit(limit).all()


def create_tag(db: Session, *, name: str):
    tag = models.Tag(name=name)
    db.add(tag)
    db.commit()
    db.refresh(tag)
    return tag


def delete_tag(db: Session, tag: models.Tag):
    # remove associations first (SQLAlchemy should handle via cascade, but be explicit)
    tag.items.clear()
    db.delete(tag)
    db.commit()
