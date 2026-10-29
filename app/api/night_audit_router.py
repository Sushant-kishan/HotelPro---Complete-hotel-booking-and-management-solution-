"""
HotelPro Night Audit & ERP Financial Reconciliation Router
PRD Section 4.4, 6: Single-click night-audit reconciliation, automated room charge & tax posting,
and ERP accounting export.
"""
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Depends, Query, Response

from app.services.night_audit_service import night_audit_service
from app.services.erp_sync import erp_bridge
from app.security.auth import get_current_user, require_permission
from app.security.rbac import Permission

router = APIRouter(prefix="/night-audit", tags=["Night Audit & Financials"])

class ExecuteAuditRequest(BaseModel):
    property_id: str

@router.get("/checklist")
def get_pre_audit_checklist(
    property_id: str = Query(...),
    current_user: dict = Depends(require_permission(Permission.EXECUTE_NIGHT_AUDIT))
):
    """Returns diagnostics and pre-audit validation counts before running EOD."""
    return night_audit_service.get_pre_audit_checklist(property_id)

@router.post("/execute")
def execute_night_audit(
    req: ExecuteAuditRequest,
    current_user: dict = Depends(require_permission(Permission.EXECUTE_NIGHT_AUDIT))
):
    """Executes single-click night audit roll-over."""
    try:
        return night_audit_service.execute_night_audit(
            property_id=req.property_id,
            auditor_user_id=current_user["id"]
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/export/netsuite/{audit_record_id}")
def export_netsuite_csv(
    audit_record_id: str,
    current_user: dict = Depends(require_permission(Permission.SYNC_ERP_JOURNAL))
):
    """Generates and downloads NetSuite CSV general ledger journal."""
    try:
        csv_data = erp_bridge.export_journal_netsuite(audit_record_id)
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=netsuite_journal_{audit_record_id[:8]}.csv"}
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/export/quickbooks/{audit_record_id}")
def export_quickbooks_iif(
    audit_record_id: str,
    current_user: dict = Depends(require_permission(Permission.SYNC_ERP_JOURNAL))
):
    """Generates and downloads QuickBooks IIF formatted journal."""
    try:
        iif_data = erp_bridge.export_journal_quickbooks(audit_record_id)
        return Response(
            content=iif_data,
            media_type="text/plain",
            headers={"Content-Disposition": f"attachment; filename=qb_journal_{audit_record_id[:8]}.iif"}
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

