"""
HotelPro Booking & Reservation API Router
PRD Section 4.3: Flexible Reservation Management, Multi-Channel Lifecycles,
Rate Engine, and Automated Folio Initialization.
"""
from typing import Optional, List
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Depends

from app.services.booking_service import booking_service
from app.services.folio_service import folio_service
from app.database import get_db
from app.security.crypto import pii_service

router = APIRouter(prefix="/reservations", tags=["Bookings & Reservations"])

class ReservationCreateRequest(BaseModel):
    property_id: str
    room_type_id: str
    check_in_date: str
    check_out_date: str
    first_name: str
    last_name: str
    email: str
    phone: str
    adult_count: int = 1
    child_count: int = 0
    channel: str = "DIRECT_WEB"
    discount_code: Optional[str] = None
    special_requests: Optional[str] = None
    corporate_account: Optional[str] = None
    card_token: Optional[str] = None

class CancelRequest(BaseModel):
    booking_reference: str
    reason: Optional[str] = "Guest requested cancellation"

@router.post("/book")
def book_reservation(req: ReservationCreateRequest):
    """
    Creates a new reservation under distributed concurrency lock.
    Verifies availability, computes dynamic pricing, manages guest CRM profile,
    and initializes split folios.
    """
    try:
        with get_db() as db:
            prop = db.execute("SELECT tenant_id FROM properties WHERE id = ?", (req.property_id,)).fetchone()
            tenant_id = prop["tenant_id"] if prop else "tenant-horizon-global"

        result = booking_service.create_reservation(
            tenant_id=tenant_id,
            property_id=req.property_id,
            room_type_id=req.room_type_id,
            check_in_date=req.check_in_date,
            check_out_date=req.check_out_date,
            first_name=req.first_name,
            last_name=req.last_name,
            email=req.email,
            phone=req.phone,
            adult_count=req.adult_count,
            child_count=req.child_count,
            channel=req.channel,
            discount_code=req.discount_code,
            special_requests=req.special_requests,
            corporate_account=req.corporate_account,
            card_token=req.card_token
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except TimeoutError as e:
        raise HTTPException(status_code=409, detail=str(e))

@router.get("/lookup/{booking_reference}")
def lookup_reservation(booking_reference: str):
    """Retrieves reservation details, guest information, room status, and folios."""
    with get_db() as db:
        res = db.execute(
            """
            SELECT r.*, rt.name as room_type_name, p.name as property_name, p.currency,
                   g.encrypted_first_name, g.encrypted_last_name, g.encrypted_email, g.encrypted_phone,
                   rm.room_number
            FROM reservations r
            JOIN room_types rt ON r.room_type_id = rt.id
            JOIN properties p ON r.property_id = p.id
            JOIN guests g ON r.guest_id = g.id
            LEFT JOIN rooms rm ON r.assigned_room_id = rm.id
            WHERE r.booking_reference = ?
            """,
            (booking_reference,)
        ).fetchone()

        if not res:
            raise HTTPException(status_code=404, detail="Reservation reference not found.")

        r_dict = dict(res)
        # Decrypt PII
        r_dict["guest_first_name"] = pii_service.decrypt(r_dict["encrypted_first_name"])
        r_dict["guest_last_name"] = pii_service.decrypt(r_dict["encrypted_last_name"])
        r_dict["guest_email"] = pii_service.decrypt(r_dict["encrypted_email"])
        r_dict["guest_phone"] = pii_service.decrypt(r_dict["encrypted_phone"])

        # Fetch folios
        r_dict["folios"] = folio_service.get_reservation_folios(r_dict["id"])
        return r_dict

@router.post("/cancel")
def cancel_reservation(req: CancelRequest):
    """Cancels a confirmed reservation and releases any allocated inventory."""
    try:
        return booking_service.cancel_reservation(req.booking_reference, req.reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
