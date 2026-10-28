"""rag router — stub para Sprint 0."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_rag():
    return {"module": "rag", "status": "not implemented yet"}
