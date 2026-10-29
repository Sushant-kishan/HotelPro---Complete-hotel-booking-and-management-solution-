"""
HotelPro Single-Click Night Audit & EOD Reconciliation Service
PRD Section 4.4, 6: Automated posting of daily room charges & taxes, single-click night-audit
reconciliation, ERP revenue journal generation (QuickBooks, NetSuite, SAP), and business date roll.
"""
import uuid
import json
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional

from app.database import get_db
from app.services.folio_service import folio_service
from app.security.audit import audit_service

class NightAuditService:
    @classmethod
    def get_pre_audit_checklist(cls, property_id: str) -> Dict[str, Any]:
        """Runs pre-audit diagnostics before night audit roll-over."""
        with get_db() as db:
            prop = db.execute("SELECT current_business_date FROM properties WHERE id = ?", (property_id,)).fetchone()
            current_date = prop["current_business_date"] if prop else datetime.now().date().isoformat()

            # Pending arrivals
            pending_arrivals = db.execute(
                "SELECT COUNT(*) as count FROM reservations WHERE property_id = ? AND check_in_date <= ? AND status = 'CONFIRMED'",
                (property_id, current_date)
            ).fetchone()["count"]

            # Active in-house stays
            in_house = db.execute(
                "SELECT COUNT(*) as count FROM reservations WHERE property_id = ? AND status = 'CHECKED_IN'",
                (property_id,)
            ).fetchone()["count"]

            # Overdue departures
            overdue_departures = db.execute(
                "SELECT COUNT(*) as count FROM reservations WHERE property_id = ? AND check_out_date < ? AND status = 'CHECKED_IN'",
                (property_id, current_date)
            ).fetchone()["count"]

            return {
                "property_id": property_id,
                "current_business_date": current_date,
                "pending_arrivals_count": pending_arrivals,
                "in_house_reservations_count": in_house,
                "overdue_departures_count": overdue_departures,
                "ready_for_audit": True
            }

    @classmethod
    def execute_night_audit(
        cls,
        property_id: str,
        auditor_user_id: str
    ) -> Dict[str, Any]:
        """
        Executes single-click end-of-day night audit:
        1. Automatically posts nightly room rate & tax for all in-house guests to their Master Folio.
        2. Aggregates daily financial revenue & ledger reconciliations.
        3. Formats ERP journal payload for accounting sync.
        4. Advances the property's current_business_date to tomorrow.
        """
        with get_db() as db:
            prop = db.execute("SELECT * FROM properties WHERE id = ?", (property_id,)).fetchone()
            if not prop:
                raise ValueError("Property not found.")

            current_date = prop["current_business_date"]
            
            # 1. Fetch in-house reservations
            in_house = db.execute(
                """
                SELECT r.*, rt.name as room_type_name
                FROM reservations r
                JOIN room_types rt ON r.room_type_id = rt.id
                WHERE r.property_id = ? AND r.status = 'CHECKED_IN'
                """,
                (property_id,)
            ).fetchall()

            total_rooms_occupied = len(in_house)
            total_room_revenue = 0.0
            total_tax_revenue = 0.0

            # Post daily room charges to Master Folios
            for res in in_house:
                folios = db.execute(
                    "SELECT id FROM folios WHERE reservation_id = ? AND folio_type = 'MASTER'",
                    (res["id"],)
                ).fetchall()
                master_folio_id = folios[0]["id"] if folios else None
                if master_folio_id:
                    charge_result = folio_service.post_charge(
                        folio_id=master_folio_id,
                        category="ROOM_CHARGE",
                        description=f"Room Charge ({res['room_type_name']}) - {current_date}",
                        amount=res["nightly_rate"],
                        tax_rate=0.10, # 10% hospitality lodging tax
                        posted_by_user_id=auditor_user_id
                    )
                    total_room_revenue += charge_result["amount"]
                    total_tax_revenue += charge_result["tax_amount"]

            # 2. Total physical rooms
            total_rooms_row = db.execute(
                "SELECT COUNT(*) as count FROM rooms WHERE property_id = ?",
                (property_id,)
            ).fetchone()
            total_physical_rooms = total_rooms_row["count"] if total_rooms_row else 1
            occupancy_rate = round((total_rooms_occupied / total_physical_rooms) * 100, 2)

            # 3. Sum daily incidental revenue posted on this business date
            incidental_row = db.execute(
                """
                SELECT COALESCE(SUM(fi.amount), 0.0) as inc_rev
                FROM folio_items fi
                JOIN folios f ON fi.folio_id = f.id
                JOIN reservations r ON f.reservation_id = r.id
                WHERE r.property_id = ? AND fi.category != 'ROOM_CHARGE' AND DATE(fi.posted_at) = DATE(?)
                """,
                (property_id, current_date)
            ).fetchone()
            total_incidental_revenue = round(incidental_row["inc_rev"] if incidental_row else 0.0, 2)

            # 4. Sum daily payments collected
            pay_row = db.execute(
                """
                SELECT COALESCE(SUM(pt.amount), 0.0) as payments
                FROM payment_transactions pt
                JOIN folios f ON pt.folio_id = f.id
                JOIN reservations r ON f.reservation_id = r.id
                WHERE r.property_id = ? AND pt.status = 'SUCCESS' AND pt.transaction_type = 'CAPTURE'
                  AND DATE(pt.created_at) = DATE(?)
                """,
                (property_id, current_date)
            ).fetchone()
            total_payments = round(pay_row["payments"] if pay_row else 0.0, 2)

            # 5. Format ERP Journal payload (Debit/Credit structure for NetSuite / QuickBooks / SAP)
            erp_journal = {
                "journal_id": f"JRNL-{current_date.replace('-', '')}-{prop['code']}",
                "property_code": prop["code"],
                "business_date": current_date,
                "currency": prop["currency"],
                "entries": [
                    {"account": "1000 - Cash & Merchant Clearing", "type": "DEBIT", "amount": total_payments},
                    {"account": "1100 - Guest Ledger Accounts Receivable", "type": "DEBIT", "amount": round((total_room_revenue + total_tax_revenue + total_incidental_revenue) - total_payments, 2)},
                    {"account": "4000 - Room Revenue", "type": "CREDIT", "amount": total_room_revenue},
                    {"account": "4100 - F&B & Incidental Revenue", "type": "CREDIT", "amount": total_incidental_revenue},
                    {"account": "2200 - Lodging Taxes Payable", "type": "CREDIT", "amount": total_tax_revenue}
                ]
            }

            # 6. Save Night Audit Record
            audit_record_id = str(uuid.uuid4())
            db.execute(
                """
                INSERT INTO night_audit_records (
                    id, property_id, business_date, auditor_user_id, total_rooms_occupied,
                    occupancy_rate, total_room_revenue, total_tax_revenue, total_incidental_revenue,
                    total_payments_collected, erp_sync_status, erp_journal_payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'GENERATED', ?)
                """,
                (
                    audit_record_id, property_id, current_date, auditor_user_id,
                    total_rooms_occupied, occupancy_rate, total_room_revenue, total_tax_revenue,
                    total_incidental_revenue, total_payments, json.dumps(erp_journal)
                )
            )

            # 7. Advance Business Date to Tomorrow
            curr_dt = datetime.strptime(current_date, "%Y-%m-%d").date()
            next_date = (curr_dt + timedelta(days=1)).isoformat()
            db.execute(
                "UPDATE properties SET current_business_date = ? WHERE id = ?",
                (next_date, property_id)
            )

        audit_service.log_event(
            tenant_id=prop["tenant_id"],
            property_id=property_id,
            user_id=auditor_user_id,
            user_role="Auditor",
            action="EXECUTE_NIGHT_AUDIT",
            entity_type="NightAuditRecord",
            entity_id=audit_record_id,
            payload={
                "closed_date": current_date,
                "new_date": next_date,
                "total_room_revenue": total_room_revenue,
                "occupancy_rate": occupancy_rate
            }
        )

        return {
            "success": True,
            "audit_record_id": audit_record_id,
            "closed_business_date": current_date,
            "new_business_date": next_date,
            "total_rooms_occupied": total_rooms_occupied,
            "occupancy_rate": occupancy_rate,
            "total_room_revenue": round(total_room_revenue, 2),
            "total_tax_revenue": round(total_tax_revenue, 2),
            "total_incidental_revenue": total_incidental_revenue,
            "total_payments_collected": total_payments,
            "erp_journal": erp_journal,
            "message": f"Night Audit completed for {current_date}. All room charges posted. Date advanced to {next_date}."
        }

night_audit_service = NightAuditService()

