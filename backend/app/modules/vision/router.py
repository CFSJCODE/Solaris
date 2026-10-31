"""vision router — stub para Sprint 0."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_vision():
    return {"module": "vision", "status": "not implemented yet"}
