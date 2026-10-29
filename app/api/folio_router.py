"""
HotelPro Folio & Financial Settlement API Router
PRD Section 4.4, 4.5: Multi-payer folio splitting, automated posting for food/beverage/minibar
incidentals, PCI-DSS tokenized payment capture, and balance settlement.
"""
from typing import Optional, List
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Depends

from app.services.folio_service import folio_service
from app.security.auth import get_current_user, require_permission
from app.security.rbac import Permission

router = APIRouter(prefix="/folios", tags=["Folios & Billing"])

class PostChargeRequest(BaseModel):
    folio_id: str
    category: str # ROOM_CHARGE, TAX, RESTAURANT, MINIBAR, ROOM_SERVICE, SPA, PARKING
    description: str
    amount: float
    tax_rate: float = 0.10

class SplitItemRequest(BaseModel):
    item_id: str
    target_folio_id: str

class ProcessPaymentRequest(BaseModel):
    folio_id: str
    amount: float
    card_token: str = "tok_pci_visa_split_settlement"
    card_brand: str = "Visa"
    card_last4: str = "4242"
    transaction_type: str = "CAPTURE"

@router.get("/reservation/{reservation_id}")
def get_reservation_folios(
    reservation_id: str,
    current_user: dict = Depends(require_permission(Permission.VIEW_FOLIO))
):
    """Fetches split folios (Master and Incidental), line items, payments, and balances."""
    return folio_service.get_reservation_folios(reservation_id)

@router.post("/post-charge")
def post_incidental_charge(
    req: PostChargeRequest,
    current_user: dict = Depends(require_permission(Permission.POST_INCIDENTAL))
):
    """Posts an incidental charge (e.g. F&B, minibar, spa) to a guest or corporate folio."""
    try:
        return folio_service.post_charge(
            folio_id=req.folio_id,
            category=req.category,
            description=req.description,
            amount=req.amount,
            tax_rate=req.tax_rate,
            posted_by_user_id=current_user["id"]
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/split-item")
def split_folio_item(
    req: SplitItemRequest,
    current_user: dict = Depends(require_permission(Permission.SPLIT_FOLIO))
):
    """Reallocates a charge line item between Master and Incidental folios."""
    try:
        return folio_service.split_item_to_folio(
            item_id=req.item_id,
            target_folio_id=req.target_folio_id,
            user_id=current_user["id"]
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/pay")
def process_payment(
    req: ProcessPaymentRequest,
    current_user: dict = Depends(require_permission(Permission.PROCESS_PAYMENT))
):
    """Executes PCI-tokenized payment capture or pre-authorization hold against folio balance."""
    try:
        return folio_service.process_payment(
            folio_id=req.folio_id,
            amount=req.amount,
            card_token=req.card_token,
            card_brand=req.card_brand,
            card_last4=req.card_last4,
            transaction_type=req.transaction_type,
            user_id=current_user["id"]
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

