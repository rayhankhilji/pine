from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from pine.api.schemas.document import Job
from pine.db import get_session
from pine.errors import AppError
from pine.models.job import Job as JobModel

router = APIRouter(tags=["jobs"])


@router.get("/jobs/{job_id}")
def get_job(
    job_id: str, session: Annotated[Session, Depends(get_session)]
) -> Job:
    job = session.get(JobModel, job_id)
    if job is None:
        raise AppError("NOT_FOUND", "Job not found", status=404)
    return Job.model_validate(job)
