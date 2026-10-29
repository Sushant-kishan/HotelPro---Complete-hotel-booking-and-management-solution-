"""
HotelPro Housekeeping API Router
PRD Section 4.4: Housekeeping task distribution, real-time cleanliness board,
and instant status propagation.
"""
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Depends, Query

from app.services.housekeeping_service import housekeeping_service
from app.security.auth import get_current_user, require_permission
from app.security.rbac import Permission

router = APIRouter(prefix="/housekeeping", tags=["Housekeeping Operations"])

class UpdateStatusRequest(BaseModel):
    room_id: str
    status: str # CLEAN, INSPECTED, DIRTY, IN_PROGRESS, OUT_OF_ORDER

@router.get("/board")
def get_housekeeping_board(
    property_id: str = Query(...),
    current_user: dict = Depends(require_permission(Permission.VIEW_HOUSEKEEPING))
):
    """Returns real-time cleanliness and operational status across all rooms."""
    return housekeeping_service.get_room_board(property_id)

@router.post("/update-status")
def update_room_status(
    req: UpdateStatusRequest,
    current_user: dict = Depends(require_permission(Permission.UPDATE_ROOM_CLEANLINESS))
):
    """Updates room cleanliness status and broadcasts immediate state change."""
    try:
        return housekeeping_service.update_room_status(
            room_id=req.room_id,
            new_status=req.status,
            staff_user_id=current_user["id"]
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

