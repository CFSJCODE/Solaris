"""projects router — stub para Sprint 0."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_projects():
    return {"module": "projects", "status": "not implemented yet"}
