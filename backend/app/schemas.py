from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class ItemBase(BaseModel):
    name: str = Field(..., max_length=255)
    description: Optional[str] = None
    tags: Optional[List[str]] = None


class ItemCreate(ItemBase):
    pass


class ItemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None


class ItemOut(ItemBase):
    id: int

    class Config:
        orm_mode = True


class ContainerBase(BaseModel):
    name: str = Field(..., max_length=255)
    width: Optional[float] = None
    height: Optional[float] = None
    depth: Optional[float] = None
    gps_lat: Optional[float] = None
    gps_lng: Optional[float] = None
    parent_id: Optional[int] = None
    view_id: Optional[int] = None


class ContainerCreate(ContainerBase):
    pass


class ContainerUpdate(BaseModel):
    name: Optional[str] = None
    width: Optional[float] = None
    height: Optional[float] = None
    depth: Optional[float] = None
    gps_lat: Optional[float] = None
    gps_lng: Optional[float] = None
    parent_id: Optional[int] = None


class ContainerOut(ContainerBase):
    id: int

    class Config:
        orm_mode = True


class PlacementBase(BaseModel):
    item_id: int
    container_id: int
    quantity: Optional[int] = 1


class PlacementCreate(PlacementBase):
    pass


class PlacementOut(PlacementBase):
    id: int
    placed_at: Optional[datetime] = None

    class Config:
        orm_mode = True



class TagBase(BaseModel):
    name: str


class TagCreate(TagBase):
    pass


class Tag(TagBase):
    id: int

    class Config:
        orm_mode = True


class ViewBase(BaseModel):
    name: str


class ViewCreate(ViewBase):
    pass


class ViewOut(ViewBase):
    id: int

    class Config:
        orm_mode = True
