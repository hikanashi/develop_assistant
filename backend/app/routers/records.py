import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from app import services
from app.db import get_session
from app.schemas import RecordIn, RecordWithRevisions, RevisionIn, RevisionOut

# operation_id は OPENAPI_FILE の operationId、MCP のツール名と一致させる (ENV-046)
router = APIRouter(prefix="/v1/records", tags=["record"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.post(
    "",
    response_model=RecordWithRevisions,
    status_code=status.HTTP_201_CREATED,
    operation_id="createRecord",
)
def create_record(session: SessionDep, body: RecordIn):
    """レコードと最初のリビジョンを作成する。contentJson は JSON Schema で検証される。"""
    return services.create_record(session, body)


@router.get("/{recordId}", response_model=RecordWithRevisions, operation_id="getRecord")
def get_record(session: SessionDep, recordId: uuid.UUID):
    return services.get_record(session, recordId)


@router.post(
    "/{recordId}/revisions",
    response_model=RevisionOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="createRevision",
)
def create_revision(session: SessionDep, recordId: uuid.UUID, body: RevisionIn):
    """新しいリビジョンを追加する。contentJson は JSON Schema で検証される。"""
    return services.add_revision(session, recordId, body)
