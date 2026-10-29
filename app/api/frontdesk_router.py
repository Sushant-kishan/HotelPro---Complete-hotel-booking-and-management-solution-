"""
HotelPro Front-Desk Operations API Router
PRD Section 4.4: Sub-60-second check-in/out, room allocations, instant key generation.
"""
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Depends, Query

from app.services.frontdesk_service import frontdesk_service
from app.security.auth import get_current_user, require_permission
from app.security.rbac import Permission

router = APIRouter(prefix="/frontdesk", tags=["Front Desk Operations"])

class CheckInRequest(BaseModel):
    reservation_id: str
    room_id: str
    card_token: Optional[str] = "tok_pci_visa_frontdesk_token"
    incidental_deposit_amount: float = 100.0

class CheckOutRequest(BaseModel):
    reservation_id: str

@router.get("/arrivals")
def get_arrivals(
    property_id: str = Query(...),
    date: Optional[str] = Query(None),
    current_user: dict = Depends(require_permission(Permission.CHECK_IN_GUEST))
):
    """Lists arriving guests for expedited front-desk processing."""
    return frontdesk_service.find_arrivals(property_id, date)

@router.get("/departures")
def get_departures(
    property_id: str = Query(...),
    date: Optional[str] = Query(None),
    current_user: dict = Depends(require_permission(Permission.CHECK_OUT_GUEST))
):
    """Lists departing guests for expedited checkout and folio settlement."""
    return frontdesk_service.find_departures(property_id, date)

@router.get("/assignable-rooms")
def get_assignable_rooms(
    property_id: str = Query(...),
    room_type_id: str = Query(...),
    current_user: dict = Depends(require_permission(Permission.ALLOCATE_ROOM))
):
    """Returns inspected/clean rooms available for assignment."""
    return frontdesk_service.get_assignable_rooms(property_id, room_type_id)

@router.post("/check-in")
def expedited_check_in(
    req: CheckInRequest,
    current_user: dict = Depends(require_permission(Permission.CHECK_IN_GUEST))
):
    """Executes sub-60s check-in: room assignment, pre-auth hold, and keycard generation."""
    try:
        return frontdesk_service.expedited_check_in(
            reservation_id=req.reservation_id,
            room_id=req.room_id,
            card_token=req.card_token or "tok_pci_visa_demo",
            incidental_deposit_amount=req.incidental_deposit_amount,
            staff_user_id=current_user["id"]
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/check-out")
def expedited_check_out(
    req: CheckOutRequest,
    current_user: dict = Depends(require_permission(Permission.CHECK_OUT_GUEST))
):
    """Executes sub-60s check-out: settles folios, deactivates keycard, and updates Housekeeping to DIRTY."""
    try:
        return frontdesk_service.expedited_check_out(
            reservation_id=req.reservation_id,
            staff_user_id=current_user["id"]
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

