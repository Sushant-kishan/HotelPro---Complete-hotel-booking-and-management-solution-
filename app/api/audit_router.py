"""
HotelPro Audit Ledger & GDPR Compliance Router
PRD Section 4.1: Immutable append-only audit logging with SHA-256 hash chaining,
GDPR/CCPA data export and right-to-erasure compliance.
"""
from typing import Optional, List
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Depends, Query

from app.security.audit import audit_service
from app.security.auth import get_current_user, require_permission
from app.security.rbac import Permission
from app.security.crypto import pii_service
from app.database import get_db

router = APIRouter(prefix="/compliance", tags=["Audit & GDPR Compliance"])

class AnonymizeRequest(BaseModel):
    guest_id: str
    reason: Optional[str] = "GDPR Article 17 Right-to-Erasure Request"

@router.get("/audit-ledger")
def get_audit_ledger(
    limit: int = Query(50, le=500),
    current_user: dict = Depends(require_permission(Permission.VIEW_AUDIT_LOGS))
):
    """Retrieves immutable audit ledger blocks."""
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

@router.get("/audit-ledger/verify-integrity")
def verify_ledger_integrity(
    current_user: dict = Depends(require_permission(Permission.VIEW_AUDIT_LOGS))
):
    """
    Verifies that the entire cryptographic SHA-256 hash chain is intact.
    Detects any tampering, alteration, or deletions in the audit logs.
    """
    return audit_service.verify_integrity()

@router.get("/gdpr/export/{guest_id}")
def export_guest_gdpr_data(
    guest_id: str,
    current_user: dict = Depends(require_permission(Permission.EXPORT_GDPR))
):
    """Exports complete portable GDPR guest profile dossier."""
    with get_db() as db:
        guest = db.execute("SELECT * FROM guests WHERE id = ?", (guest_id,)).fetchone()
        if not guest:
            raise HTTPException(status_code=404, detail="Guest record not found.")

        # Stays & reservations
        reservations = db.execute("SELECT * FROM reservations WHERE guest_id = ?", (guest_id,)).fetchall()
        
        # Audit log access
        audit_service.log_event(
            tenant_id=guest["tenant_id"],
            property_id=None,
            user_id=current_user["id"],
            user_role=current_user["role"],
            action="GDPR_DATA_EXPORT",
            entity_type="Guest",
            entity_id=guest_id,
            payload={"action": "Article 20 Data Portability Export"}
        )

        return {
            "guest_id": guest["id"],
            "personal_data": {
                "first_name": pii_service.decrypt(guest["encrypted_first_name"]),
                "last_name": pii_service.decrypt(guest["encrypted_last_name"]),
                "email": pii_service.decrypt(guest["encrypted_email"]),
                "phone": pii_service.decrypt(guest["encrypted_phone"]),
                "vip_tier": guest["vip_tier"],
                "preferences": guest["preferences"]
            },
            "stay_history": [dict(r) for r in reservations]
        }

@router.post("/gdpr/erase")
def erase_guest_pii(
    req: AnonymizeRequest,
    current_user: dict = Depends(require_permission(Permission.ERASE_GDPR))
):
    """
    Executes GDPR Right-to-Erasure (cryptographic shredding & pseudonymization).
    Replaces encrypted PII with pseudonymized tokens while maintaining financial folio integrity.
    """
    with get_db() as db:
        guest = db.execute("SELECT * FROM guests WHERE id = ?", (req.guest_id,)).fetchone()
        if not guest:
            raise HTTPException(status_code=404, detail="Guest record not found.")

        # Cryptographically shred PII by encrypting empty/shredded marker
        shredded_marker = pii_service.encrypt("GDPR_FORGOTTEN")
        db.execute(
            """
            UPDATE guests
            SET encrypted_first_name = ?,
                encrypted_last_name = ?,
                encrypted_email = ?,
                encrypted_phone = ?,
                email_blind_index = 'ANONYMIZED',
                phone_blind_index = 'ANONYMIZED',
                preferences = '[]',
                anonymized = 1
            WHERE id = ?
            """,
            (shredded_marker, shredded_marker, shredded_marker, shredded_marker, req.guest_id)
        )

    audit_service.log_event(
        tenant_id=guest["tenant_id"],
        property_id=None,
        user_id=current_user["id"],
        user_role=current_user["role"],
        action="GDPR_RIGHT_TO_ERASURE",
        entity_type="Guest",
        entity_id=req.guest_id,
        payload={"reason": req.reason}
    )

    return {
        "success": True,
        "guest_id": req.guest_id,
        "message": "PII cryptographically erased and shredded in accordance with GDPR Article 17."
    }

