"""chat router — stub para Sprint 0."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/")
async def list_chat():
    return {"module": "chat", "status": "not implemented yet"}
