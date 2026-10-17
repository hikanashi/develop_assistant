import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from app import services
from app.db import get_session
from app.schemas import RecordIn, RecordUpdateIn, RecordWithRevisions, RevisionIn, RevisionOut

router = APIRouter(prefix="/records", tags=["record"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.post("", response_model=RecordWithRevisions, status_code=status.HTTP_201_CREATED)
def create_record(session: SessionDep, body: RecordIn):
    """レコードと最初のリビジョンを作成する。content_json は JSON Schema で検証される。"""
    return services.create_record(session, body)


@router.get("/{record_id}", response_model=RecordWithRevisions)
def get_record(session: SessionDep, record_id: uuid.UUID):
    return services.get_record(session, record_id)


@router.put("/{record_id}", response_model=RecordWithRevisions)
def update_record(session: SessionDep, record_id: uuid.UUID, body: RecordUpdateIn):
    """レコード属性を更新し、新しいリビジョンを追加する。両方とも同時にコミットする。"""
    return services.update_record(session, record_id, body)


@router.post(
    "/{record_id}/revisions", response_model=RevisionOut, status_code=status.HTTP_201_CREATED
)
def add_revision(session: SessionDep, record_id: uuid.UUID, body: RevisionIn):
    """新しいリビジョンを追加する。content_json は JSON Schema で検証される。"""
    return services.add_revision(session, record_id, body)
